import os
import re
import json
from dotenv import load_dotenv

load_dotenv()

# Memory Limits
MAX_HISTORY = 20
MAX_GROUP_HISTORY = 200

# Environment Variables
BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
BOT_USERNAME = os.getenv("BOT_USERNAME")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "openrouter/free")

# Multiple Admins: split by comma, strip whitespace, lowercase
ADMIN_USERNAMES_RAW = os.getenv("ADMIN_USERNAMES", "")
ADMIN_USERNAMES = [u.strip().lower() for u in ADMIN_USERNAMES_RAW.split(",") if u.strip()]


def is_admin(username: str) -> bool:
    return username.lower() in ADMIN_USERNAMES


# Regex Patterns
ANALYZE_REGEX_EN = re.compile(r'\b(analyze|analyse|analiz)\s*(\d*)\b', re.IGNORECASE)
ANALYZE_REGEX_RU = re.compile(r'\b(анализ|аналез|анали[зсх])\s*(\d*)\b', re.IGNORECASE)
BOT_MENTION_REGEX = re.compile(rf'@{re.escape(BOT_USERNAME)}\s*', re.IGNORECASE)

# Dynamic Config Management
CONFIG_FILE = "config.json"


def get_config():
    if not os.path.exists(CONFIG_FILE):
        # Fallback defaults if config.json is missing
        return {
            "MODEL_NAME": os.getenv("MODEL_NAME", "openrouter/free"),
            "SYSTEM_PROMPT": "You are a helpful assistant.",
            "ANALYZE_PROMPT_EN": "Analyze these messages: {messages}",
            "ANALYZE_PROMPT_RU": "Проанализируй эти сообщения: {messages}"
        }
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
