import logging
from datetime import datetime, timezone
from telethon import TelegramClient, events

from src.database.database import get_session, ProcessedMessage

class TelegramListener:
    """
    A class to encapsulate a Telegram client session, responsible for
    listening to specific chats and passing new messages to a callback.
    """

    def __init__(self, session_name, api_id, api_hash, target_chat_ids, message_processor_callback):
        """
        Initializes the Telegram Listener.
        """
        self.start_time = None
        self.client = TelegramClient(session_name, api_id, api_hash)
        self.target_chat_ids = target_chat_ids
        self.process_message = message_processor_callback
        self.session_name = session_name

        logging.info(f"TelegramListener initialized for session '{self.session_name}'")
        logging.info(f"Will listen to chat IDs: {self.target_chat_ids}")

        # Event handler for new messages in the target chats.
        @self.client.on(events.NewMessage(chats=self.target_chat_ids))
        async def _message_handler(event):
            # Check if the message is new (sent after the script started)
            if self.start_time and event.message.date > self.start_time:
                await self.process_message(event)
            else:
                logging.debug(f"Ignoring old message (ID: {event.message.id}) from before script start.")

    async def start(self):
        """Connects the client and runs it until disconnected."""
        self.start_time = datetime.now(timezone.utc)
        logging.info(f"Starting client for session '{self.session_name}'... Will only process messages after {self.start_time}")
        await self.client.start()
        logging.info(f"Client for session '{self.session_name}' started successfully.")
        await self.client.run_until_disconnected()


async def process_new_message(event):
    """
    This is our callback function. It receives the full event, processes it, saves it to the database.
    """
    # Get the message text. If it's empty or None, skip processing.
    message_text = event.message.text
    if not message_text:
        logging.info(f"Skipping message (ID: {event.message.id}) because it contains no text.")
        return

    # Get a new database session
    db_session = get_session()
    try:
        # Get chat and sender info
        chat = await event.get_chat()
        sender = await event.get_sender()

        # Create a new ProcessedMessage object with the data
        new_db_entry = ProcessedMessage(
            telegram_message_id=event.message.id,
            channel_id=event.chat_id,
            channel_name=getattr(chat, 'title', 'Unknown Channel'),
            sender_id=sender.id,
            sender_name=getattr(sender, 'username', None) or getattr(sender, 'first_name', 'N/A'),
            message_text=message_text,
            processed_at=datetime.now(timezone.utc)
        )
        db_session.add(new_db_entry)
        db_session.commit()

        logging.info(f"Successfully saved message {event.message.id} from channel '{new_db_entry.channel_name}' to database.")

        # TODO: Phase 3 - Send message_text to the LLM for analysis.

    except Exception as e:
        logging.error(f"Error processing message: {e}", exc_info=True)
        db_session.rollback()  # Rollback the transaction on error
    finally:
        db_session.close()  # Always close the session
