# config.py
import yaml
import os
from typing import Dict, Any, List

CONFIG_FILE = "config.yml"
DEFAULT_CONFIG = {
    "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "users": {
        "admin_users": [123456789],
        "normal_users": []
    },
    "panel_config": {
        "url": "",
        "username": "",
        "password": ""
    }
}

def get_config() -> Dict[str, Any]:
    """Loads the configuration from config.yml."""
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        print(f"'{CONFIG_FILE}' not found. A default config file has been created.")
        print("Please edit it with your bot token and user IDs.")
        # Exiting because the token is mandatory
        exit()
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def save_config(config_data: Dict[str, Any]):
    """Saves the configuration and reloads it into memory."""
    global config
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f, allow_unicode=True, sort_keys=False)
    config = config_data  # Update the in-memory config immediately


# Load config at import time
config = get_config()

# --- Helper functions to access config values ---

def get_bot_token() -> str:
    return config.get("bot_token", "")

def get_admin_users() -> List[int]:
    return config.get("users", {}).get("admin_users", [])

def get_normal_users() -> List[int]:
    return config.get("users", {}).get("normal_users", [])

def get_panel_config() -> Dict[str, str]:
    return config.get("panel_config", {})

def is_admin(user_id: int) -> bool:
    """Checks if a user is an admin."""
    return user_id in get_admin_users()

def is_authorized(user_id: int) -> bool:
    """Checks if a user is either an admin or a normal user."""
    return is_admin(user_id) or user_id in get_normal_users()

