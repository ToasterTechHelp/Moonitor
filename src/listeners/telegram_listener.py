import os
import logging
import asyncio
from collections import deque
from datetime import datetime, timezone
from telethon import TelegramClient, events

from src.database.database import get_db_session, ProcessedMessage, Trade
from src.llm.openai_analyzer import analyze_with_openai
from src.trading.strategy import calculate_trade_plan, calculate_take_profit_amounts
from src.trading.trader import JupiterTrader
from src.notifications.discord_notifier import DiscordNotifier


logger = logging.getLogger(__name__)

class TelegramListener:
    """
    A class to encapsulate a Telegram client session, responsible for
    listening to specific chats and passing new messages to a callback.
    """

    def __init__(self, session_name, api_id, api_hash, target_chat_ids, history_limit):
        """
        Initializes the Telegram Listener.
        """
        self.start_time = None
        self.client = TelegramClient(session_name, api_id, api_hash)
        self.target_chat_ids = target_chat_ids
        self.session_name = session_name
        self.history_cache = {}
        self.history_limit = history_limit
        self.trader = JupiterTrader()
        self.discord = DiscordNotifier()
        self.sell_token = os.getenv("SELL_TOKEN")

        logger.info(f"TelegramListener initialized for session '{self.session_name}'")
        logger.info(f"Will listen to chat IDs: {self.target_chat_ids}")

        # Event handler for new messages in the target chats.
        @self.client.on(events.NewMessage(chats=self.target_chat_ids))
        async def _message_handler(event):
            # Check if the message is new (sent after the script started)
            if self.start_time and event.message.date > self.start_time:
                await self._process_new_message(event)

    async def _process_new_message(self, event):
        """
        Internal method to process a new message, build context, analyze, and save.
        """
        message_text = event.message.text
        if not message_text:
            logger.info(f"Skipping message (ID: {event.message.id}) because it contains no text.")
            return

        channel_id = event.chat_id

        try:
            with get_db_session() as db_session:
                chat = await event.get_chat()
                sender = await event.get_sender()

                sender_name = getattr(sender, 'username', None) or getattr(sender, 'first_name', 'N/A')
                channel_name = getattr(chat, 'title', 'Unknown Channel')

                # ----- Prepare message history for LLM -----
                if channel_id not in self.history_cache:
                    self.history_cache[channel_id] = deque(maxlen=self.history_limit)

                reply_text = ""
                if event.message.is_reply:
                    reply_text = await event.get_reply_message()
                    if reply_text and reply_text.text:
                        reply_sender = await reply_text.get_sender()
                        reply_sender_name = getattr(reply_sender, 'username', None) or getattr(reply_sender, 'first_name', 'N/A')
                        reply_text = f"(replying to {reply_sender_name}: '{reply_text.text}')"

                new_message = f"{sender_name} {reply_text}: {message_text}"
                new_message_dict = {"role": "user", "content": new_message}

                self.history_cache[channel_id].append(new_message_dict)
                history_for_llm = list(self.history_cache[channel_id])

                print(history_for_llm)

                # Create db entry for processed_messages
                new_db_entry = ProcessedMessage(
                    telegram_message_id=event.message.id,
                    channel_id=channel_id,
                    channel_name=channel_name,
                    sender_id=sender.id,
                    sender_name=sender_name,
                    message_text=message_text,
                    processed_at=datetime.now(timezone.utc)
                )
                db_session.add(new_db_entry)
                db_session.flush()
                logger.info(f"Saved new message {event.message.id} from '{channel_name}' to DB.")

                # ----- LLM analysis -----
                analysis = analyze_with_openai(history_for_llm)

                if not analysis:
                    logger.warning(f"LLM analysis failed for message {event.message.id}.")
                    return

                # Save LLM analysis to db.
                logger.info(f"LLM analysis complete for message {event.message.id}. Decision: {analysis['decision']}")
                new_db_entry.llm_decision = analysis.get('decision')
                new_db_entry.llm_confidence = analysis.get('confidence_score')
                new_db_entry.llm_rationale = analysis.get('rationale')
                new_db_entry.token_address = analysis.get('token_address')
                logger.info(f"Updated message {event.message.id} in DB with LLM analysis.")

                # Send Discord notification for LLM analysis
                self.discord.send_message(
                    f"LLM Decision: {analysis['decision'].upper()} | "
                    f"Token: {analysis.get('token_address', 'N/A')} | "
                    f"Confidence: {analysis.get('confidence_score', 0):.2%}"
                )

                # ----- Strategy and Trading Step -----
                if analysis and analysis['decision'] == 'buy':
                    token_address = analysis.get('token_address')
                    if not token_address:
                        logger.warning("LLM analysis suggested a 'buy' but provided no token address.")
                        return

                    existing_trade = db_session.query(Trade).filter_by(
                        token_address=token_address,
                    ).first()

                    if existing_trade:
                        logger.info(f"Skipping trade for {token_address}. Trade history exists.")
                        return

                    trade_plan = calculate_trade_plan(analysis)
                    if not trade_plan:
                        logger.info("Strategy module decided not to generate a trade plan.")
                        return

                    logger.info(f"Trade plan generated for token {token_address}. Executing trade...")

                    # Execute the swap
                    success, signature, result = self.trader.market_swap(
                        input_mint=self.sell_token,
                        output_mint=trade_plan['token_address'],
                        amount=trade_plan['amount']
                    )

                    # Create Trade record in database
                    try:
                        new_trade = Trade(
                            processed_message_id=new_db_entry.id,
                            token_address=token_address,
                            status="failed" if not success else "open",
                            buy_transaction_sig=signature if success else None,
                            amount_spent_sol=None,  # Will be filled from actual execution results
                            amount_received_token=None,  # Will be filled from actual execution results
                            take_profit_percentage=trade_plan.get('take_profit_percentage'),
                            stop_loss_percentage=trade_plan.get('stop_loss_percentage'),
                        )

                        if success:
                            # Extract actual amounts from Ultra API result
                            if result:
                                # inputAmountResult = actual SOL spent (in lamports)
                                if 'inputAmountResult' in result:
                                    actual_sol_spent = float(result['inputAmountResult']) / 1_000_000_000
                                    new_trade.amount_spent_sol = actual_sol_spent

                                # outputAmountResult = actual tokens received (in token's smallest unit)
                                if 'outputAmountResult' in result:
                                    new_trade.amount_received_token = float(result['outputAmountResult'])

                                logger.info(
                                    f"Actual trade: Spent {actual_sol_spent:.6f} SOL, received {result.get('outputAmountResult', 'unknown')} tokens")

                            logger.info(f"Transaction: https://solscan.io/tx/{signature}")

                            # Send Discord notification for successful trade
                            self.discord.send_message(
                                f"✅ TRADE EXECUTED: {token_address} | "
                                f"Spent: {new_trade.amount_spent_sol:.6f} SOL | "
                                f"TX: https://solscan.io/tx/{signature}"
                            )

                        else:
                            logger.error(f"Trade failed for token {token_address}")
                            if result and 'error' in result:
                                logger.error(f"Error details: {result['error']}")

                            # Send Discord notification for failed trade
                            self.discord.send_message(f"❌ TRADE FAILED: {token_address}")

                        db_session.add(new_trade)
                        db_session.flush()

                        logger.info(f"Trade record saved to database with ID: {new_trade.id}")

                        # Set up limit orders for take profit if trade was successful
                        if success and new_trade.status == "open":
                            try:
                                # Calculate take profit amounts
                                making_amount, taking_amount = calculate_take_profit_amounts(
                                    amount_spent_sol=new_trade.amount_spent_sol,
                                    amount_received_token=new_trade.amount_received_token,
                                    take_profit_percentage=trade_plan['take_profit_percentage']
                                )

                                if making_amount > 0 and taking_amount > 0:
                                    # Create take profit limit order
                                    tp_success, tp_signature, tp_result = self.trader.create_limit_order(
                                        input_mint=token_address,  # Selling the coin
                                        output_mint=self.sell_token,  # Receiving SOL
                                        making_amount=making_amount,
                                        taking_amount=taking_amount
                                    )

                                    if tp_success:
                                        new_trade.tp_order_sig = tp_signature
                                        db_session.flush()

                                        logger.info(f"Take profit limit order created successfully for trade {new_trade.id}")
                                        logger.info(f"Signature: {tp_signature}")

                                        # Send Discord notification for successful limit order
                                        self.discord.send_message(
                                            f"📋 TAKE PROFIT ORDER CREATED: {token_address} | "
                                            f"TX: https://solscan.io/tx/{tp_signature}"
                                        )
                                    else:
                                        logger.error(f"Failed to create take profit limit order for trade {new_trade.id}")
                                        if tp_result and 'error' in tp_result:
                                            logger.error(f"Take profit order error: {tp_result['error']}")

                                        # Send Discord notification for failed limit order
                                        self.discord.send_message(f"⚠️ TAKE PROFIT ORDER FAILED: {token_address}")
                                else:
                                    logger.info(f"Invalid take profit amounts calculated for trade {new_trade.id}")

                            except Exception as e:
                                logger.error(f"Error setting up limit orders for trade {new_trade.id}: {e}")

                    except Exception as trade_error:
                        logger.error(f"Error creating trade record: {trade_error}", exc_info=True)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

    async def start(self):
        """Connects the client and runs it until disconnected."""
        self.start_time = datetime.now(timezone.utc)
        logger.info(f"Starting client for session '{self.session_name}'... Will only process messages after {self.start_time}")
        await self.client.start()
        logger.info(f"Client for session '{self.session_name}' started successfully.")
        await self.client.run_until_disconnected()