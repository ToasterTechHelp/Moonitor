import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from src.database.database import get_db_session, ProcessedMessage, Trade
from src.llm.openai_analyzer import analyze_with_openai
from src.trading.strategy import calculate_trade_plan, calculate_take_profit_amounts
from src.trading.trader import JupiterTrader
from src.notifications.discord_notifier import DiscordNotifier


logger = logging.getLogger(__name__)


class MessageProcessor:
    """
    Shared message processing logic for different listeners (Telegram, Discord, etc.)
    """
    
    def __init__(self):
        self.trader = JupiterTrader()
        self.discord = DiscordNotifier()
        self.sell_token = os.getenv("SELL_TOKEN")
    
    async def process_message(
        self,
        message_id: int,
        channel_id: int,
        channel_name: str,
        sender_id: int,
        sender_name: str,
        message_text: str,
        history_for_llm: list,
        platform: str
    ) -> Optional[Dict[str, Any]]:
        """
        Process a new message: save to DB, analyze with LLM, and execute trades if needed.
        
        Args:
            message_id: Unique message ID from the platform
            channel_id: Channel/chat ID
            channel_name: Name of the channel/chat
            sender_id: ID of the message sender
            sender_name: Name/username of the sender
            message_text: The actual message content
            history_for_llm: List of message history for LLM context
            platform: Platform name (telegram, discord, etc.)
            
        Returns:
            Dict with processing results or None if failed
        """
        
        if not message_text:
            logger.info(f"Skipping message (ID: {message_id}) because it contains no text.")
            return None

        try:
            with get_db_session() as db_session:
                # Create db entry for processed_messages
                new_db_entry = ProcessedMessage(
                    telegram_message_id=message_id,  # TODO: Rename this field to be platform-agnostic
                    channel_id=channel_id,
                    channel_name=channel_name,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    message_text=message_text,
                    processed_at=datetime.now(timezone.utc)
                )
                db_session.add(new_db_entry)
                db_session.flush()
                logger.info(f"Saved new message {message_id} from '{channel_name}' to DB.")

                # ----- LLM analysis -----
                analysis = analyze_with_openai(history_for_llm)

                if not analysis:
                    logger.warning(f"LLM analysis failed for message {message_id}.")
                    return None

                # Save LLM analysis to db.
                logger.info(f"LLM analysis complete for message {message_id}. Decision: {analysis['decision']}")
                new_db_entry.llm_decision = analysis.get('decision')
                new_db_entry.llm_confidence = analysis.get('confidence_score')
                new_db_entry.llm_rationale = analysis.get('rationale')
                new_db_entry.token_address = analysis.get('token_address')
                logger.info(f"Updated message {message_id} in DB with LLM analysis.")

                # Send Discord notification for LLM analysis
                self.discord.send_message(
                    f"Message: {message_text}\n\n"
                    f"LLM Decision: {analysis['decision'].upper()}\n"
                    f"Token: {analysis.get('token_address', 'N/A')}\n"
                    f"Confidence: {analysis.get('confidence_score', 0):.2%}\n"
                    f"Rationale: {analysis.get('rationale', 'N/A')}"
                )

                # ----- Strategy and Trading Step -----
                if analysis and analysis['decision'] == 'buy':
                    trade_result = await self._execute_trade(analysis, new_db_entry, db_session)
                    return {
                        'analysis': analysis,
                        'trade_result': trade_result,
                        'db_entry': new_db_entry
                    }

                return {
                    'analysis': analysis,
                    'trade_result': None,
                    'db_entry': new_db_entry
                }

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return None

    async def _execute_trade(self, analysis: Dict[str, Any], db_entry: ProcessedMessage, db_session) -> Optional[Dict[str, Any]]:
        """
        Execute a trade based on LLM analysis.
        
        Args:
            analysis: LLM analysis results
            db_entry: Database entry for the processed message
            db_session: Database session
            
        Returns:
            Dict with trade execution results or None if failed
        """
        token_address = analysis.get('token_address')
        if not token_address:
            logger.warning("LLM analysis suggested a 'buy' but provided no token address.")
            return None

        existing_trade = db_session.query(Trade).filter_by(
            token_address=token_address,
        ).first()

        if existing_trade:
            logger.info(f"Skipping trade for {token_address}. Trade history exists.")
            return None

        trade_plan = calculate_trade_plan(analysis)
        if not trade_plan:
            logger.info("Strategy module decided not to generate a trade plan.")
            return None

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
                processed_message_id=db_entry.id,
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
                    f"✅ TRADE EXECUTED: {token_address}\n"
                    f"Spent: {new_trade.amount_spent_sol:.6f} SOL\n"
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
                await self._setup_take_profit_order(new_trade, trade_plan, token_address, db_session)

            return {
                'success': success,
                'signature': signature,
                'trade': new_trade,
                'result': result
            }

        except Exception as trade_error:
            logger.error(f"Error creating trade record: {trade_error}", exc_info=True)
            return None

    async def _setup_take_profit_order(self, trade: Trade, trade_plan: Dict[str, Any], token_address: str, db_session):
        """
        Set up take profit limit order for a successful trade.
        
        Args:
            trade: Trade database record
            trade_plan: Original trade plan
            token_address: Token contract address
            db_session: Database session
        """
        try:
            # Calculate take profit amounts
            making_amount, taking_amount = calculate_take_profit_amounts(
                amount_spent_sol=trade.amount_spent_sol,
                amount_received_token=trade.amount_received_token,
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
                    trade.tp_order_sig = tp_signature
                    db_session.flush()

                    logger.info(f"Take profit limit order created successfully for trade {trade.id}")
                    logger.info(f"Signature: {tp_signature}")

                    # Send Discord notification for successful limit order
                    self.discord.send_message(
                        f"📋 TAKE PROFIT ORDER CREATED: {token_address} | "
                        f"TX: https://solscan.io/tx/{tp_signature}"
                    )
                else:
                    logger.error(f"Failed to create take profit limit order for trade {trade.id}")
                    if tp_result and 'error' in tp_result:
                        logger.error(f"Take profit order error: {tp_result['error']}")

                    # Send Discord notification for failed limit order
                    self.discord.send_message(f"⚠️ TAKE PROFIT ORDER FAILED: {token_address}")
            else:
                logger.info(f"Invalid take profit amounts calculated for trade {trade.id}")

        except Exception as e:
            logger.error(f"Error setting up limit orders for trade {trade.id}: {e}")