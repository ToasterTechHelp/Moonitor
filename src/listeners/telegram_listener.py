import os
import logging
import asyncio
from collections import deque
from datetime import datetime, timezone
from telethon import TelegramClient, events

from src.listeners.message_processor import MessageProcessor


logger = logging.getLogger(__name__)

class TelegramListener:
    """
    A class to encapsulate a Telegram client session, responsible for
    listening to specific chats and passing new messages to a callback.
    """

    def __init__(self, session_name, api_id, api_hash, target_chat_ids, history_limit, message_processor):
        """
        Initializes the Telegram Listener.
        """
        self.start_time = None
        self.client = TelegramClient(session_name, api_id, api_hash)
        self.target_chat_ids = target_chat_ids
        self.session_name = session_name
        self.history_cache = {}
        self.history_limit = history_limit
        self.message_processor = MessageProcessor()

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
        Internal method to process a new message, build context, and delegate to shared processor.
        """
        message_text = event.message.text
        channel_id = event.chat_id

        try:
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

            # Process the message using the shared processor
            result = await self.message_processor.process_message(
                message_id=event.message.id,
                channel_id=channel_id,
                channel_name=channel_name,
                sender_id=sender.id,
                sender_name=sender_name,
                message_text=message_text,
                history_for_llm=history_for_llm,
                platform="telegram"
            )

            if result:
                logger.info(f"Message {event.message.id} processed successfully. Analysis: {result['analysis']['decision']}")
            else:
                logger.warning(f"Message {event.message.id} processing failed.")

        except Exception as e:
            logger.error(f"Error processing telegram message: {e}", exc_info=True)

    async def start(self):
        """Connects the client and runs it until disconnected."""
        self.start_time = datetime.now(timezone.utc)
        logger.info(f"Starting client for session '{self.session_name}'... Will only process messages after {self.start_time}")
        await self.client.start()
        logger.info(f"Client for session '{self.session_name}' started successfully.")
        await self.client.run_until_disconnected()