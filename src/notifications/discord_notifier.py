import os
import logging
import requests

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """Simple Discord webhook notifier."""

    def __init__(self):
        """Initialize Discord notifier with webhook URL from environment."""
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not self.webhook_url:
            logger.warning("DISCORD_WEBHOOK_URL not set - Discord notifications disabled")

    def send_message(self, message: str) -> bool:
        """
        Send a simple message to Discord via webhook.

        Args:
            message: The message to send

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.webhook_url:
            return False

        try:
            payload = {"content": message}

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()

            logger.info("Discord message sent successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return False