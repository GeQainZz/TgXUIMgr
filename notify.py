import httpx
import logging

import config

logger = logging.getLogger(__name__)


def notify_admins(message: str, parse_mode: str = "Markdown") -> None:
    """Send a Telegram message to all admin users via the Bot API (sync).

    Used by the Flask webapp to broadcast notifications that originate outside
    the bot's own event loop.
    """
    bot_token = config.get_bot_token()
    admin_users = config.get_admin_users()
    if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.warning("notify_admins: bot token not configured, skipping.")
        return
    if not admin_users:
        return
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    with httpx.Client(timeout=15) as client:
        for uid in admin_users:
            try:
                client.post(api_url, json={
                    "chat_id": uid,
                    "text": message,
                    "parse_mode": parse_mode,
                })
            except Exception as e:
                logger.error(f"notify_admins: failed to notify admin {uid}: {e}")
