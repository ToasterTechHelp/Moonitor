import logging
from collections import deque
from datetime import datetime, timezone
from telethon import TelegramClient, events

from src.database.database import get_session, ProcessedMessage
from src.llm.openai_analyzer import analyze_with_openai

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

        logging.info(f"TelegramListener initialized for session '{self.session_name}'")
        logging.info(f"Will listen to chat IDs: {self.target_chat_ids}")

        # Event handler for new messages in the target chats.
        @self.client.on(events.NewMessage(chats=self.target_chat_ids))
        async def _message_handler(event):
            # Check if the message is new (sent after the script started)
            if self.start_time and event.message.date > self.start_time:
                await self._process_new_message(event)
            else:
                logging.debug(f"Ignoring old message (ID: {event.message.id}) from before script start.")

    async def _process_new_message(self, event):
        """
        Internal method to process a new message, build context, analyze, and save.
        """
        message_text = event.message.text
        if not message_text:
            logging.info(f"Skipping message (ID: {event.message.id}) because it contains no text.")
            return

        channel_id = event.chat_id
        db_session = get_session()

        try:
            chat = await event.get_chat()
            sender = await event.get_sender()

            sender_name = getattr(sender, 'username', None) or getattr(sender, 'first_name', 'N/A')
            channel_name = getattr(chat, 'title', 'Unknown Channel')

            if channel_id not in self.history_cache:
                # Only allow context of past 5 messages
                self.history_cache[channel_id] = deque(maxlen=self.history_limit)

            context = ["--- CONVERSATION HISTORY ---"]
            for past_message in self.history_cache[channel_id]:
                context.append(past_message)

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

            # Create db entry
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
            db_session.commit()
            logging.info(f"Saved new message {event.message.id} from '{channel_name}' to DB.")

            # LLM analysis
            analysis = analyze_with_openai(history_for_llm)

            # Save LLM analysis to db.
            if analysis:
                logging.info(f"LLM analysis complete for message {event.message.id}. Decision: {analysis['decision']}")
                new_db_entry.llm_decision = analysis.get('decision')
                new_db_entry.llm_confidence = analysis.get('confidence_score')
                new_db_entry.llm_rationale = analysis.get('rationale')
                new_db_entry.token_address = analysis.get('token_address')
                db_session.commit()
                logging.info(f"Updated message {event.message.id} in DB with LLM analysis.")
            else:
                logging.warning(f"LLM analysis failed for message {event.message.id}.")

        except Exception as e:
            logging.error(f"Error processing message: {e}", exc_info=True)
            if db_session: db_session.rollback()
        finally:
            if db_session: db_session.close()

    async def start(self):
        """Connects the client and runs it until disconnected."""
        self.start_time = datetime.now(timezone.utc)
        logging.info(f"Starting client for session '{self.session_name}'... Will only process messages after {self.start_time}")
        await self.client.start()
        logging.info(f"Client for session '{self.session_name}' started successfully.")
        await self.client.run_until_disconnected()
