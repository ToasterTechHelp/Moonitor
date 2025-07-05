import asyncio
import os
import logging
from dotenv import load_dotenv

from database.database import create_db_and_tables
from listeners.telegram_listener import TelegramListener, process_new_message


# Configure logging for the entire application
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)


async def main():
    """
    The main entry point of the application.
    Sets up the database and runs the listeners.
    """
    load_dotenv()
    create_db_and_tables()

    try:
        API_ID = int(os.getenv('TELEGRAM_API_ID'))
        API_HASH = os.getenv('TELEGRAM_API_HASH')
        SESSION_NAME = os.getenv('TELEGRAM_SESSION_NAME')
        chat_ids_str = os.getenv('TELEGRAM_TARGET_CHAT_IDS', '')

        if not all([API_ID, API_HASH, SESSION_NAME]):
            raise ValueError("Missing required Telegram environment variables")

        TARGET_CHAT_IDS = [int(chat_id.strip()) for chat_id in chat_ids_str.split(',') if chat_id.strip()]

        if not TARGET_CHAT_IDS:
            raise ValueError("No TARGET_CHAT_IDS found in .env file.")

    except (ValueError, TypeError) as e:
        logging.error(f"Error loading environment variables: {e}")
        return

    # Create an instance of our Telegram listener
    telegram_listener = TelegramListener(
        session_name=SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
        target_chat_ids=TARGET_CHAT_IDS,
        message_processor_callback=process_new_message
    )

    await telegram_listener.start()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Application shutting down.")
    except Exception as e:
        logging.exception("An unexpected error occurred in the main application loop!")
