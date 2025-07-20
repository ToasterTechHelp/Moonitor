import os
import sys
import logging
import asyncio
from dotenv import load_dotenv

from database.database import create_db_and_tables
from listeners.telegram_listener import TelegramListener
from monitor.limit_monitor import check_limit_order

# Configure logger for the entire application
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def validate_env_variables():
    """Checks if all required environment variables are set."""
    required_vars = [
        'TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_SESSION_NAME',
        'TELEGRAM_TARGET_CHAT_IDS', 'TELEGRAM_HISTORY_LIMIT', 'OPENAI_API_KEY',
        'PRIVATE_KEY', 'DATABASE_FILE', 'BASE_PURCHASE_SOL',
        'BASE_TAKE_PROFIT_PCT', 'BASE_STOP_LOSS_PCT',
        'PURCHASE_INFLUENCE_FACTOR', 'TAKE_PROFIT_INCREASE_FACTOR', 'STOP_LOSS_DECREASE_FACTOR'
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logger.critical(f"CRITICAL ERROR: Missing required environment variables: {', '.join(missing_vars)}")
        logger.critical("Please check your .env file. Exiting application.")
        return False

    logger.info("All required environment variables are present.")
    return True

async def limit_order_monitor(telegram_listener):
    """Simple background task to check orders every minute."""
    while True:
        try:
            await asyncio.sleep(60)  # Wait 1 minute
            check_limit_order(telegram_listener.trader)
        except Exception as e:
            logger.error(f"Error in order monitoring: {e}")

async def main():
    """
    The main entry point of the application.
    Sets up the database and runs the listeners.
    """
    load_dotenv()

    if not validate_env_variables():
        sys.exit(1)

    create_db_and_tables()

    # ----- Load Configuration -----
    API_ID = int(os.getenv('TELEGRAM_API_ID'))
    API_HASH = os.getenv('TELEGRAM_API_HASH')
    SESSION_NAME = os.getenv('TELEGRAM_SESSION_NAME')
    TELEGRAM_HISTORY_LIMIT = int(os.getenv('TELEGRAM_HISTORY_LIMIT', '5'))
    chat_ids_str = os.getenv('TELEGRAM_TARGET_CHAT_IDS', '')
    TARGET_CHAT_IDS = [int(chat_id.strip()) for chat_id in chat_ids_str.split(',') if chat_id.strip()]

    if not TARGET_CHAT_IDS:
        raise ValueError("No TARGET_CHAT_IDS found in .env file.")

    # Create an instance of our Telegram listener
    telegram_listener = TelegramListener(
        session_name=SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
        target_chat_ids=TARGET_CHAT_IDS,
        history_limit=TELEGRAM_HISTORY_LIMIT
    )

    await asyncio.gather(
        telegram_listener.start(),
        limit_order_monitor(telegram_listener)
    )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application shutting down.")
    except Exception as e:
        logger.exception("An unexpected error occurred in the main application loop!")
