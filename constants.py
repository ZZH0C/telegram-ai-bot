import os
import re
from dotenv import load_dotenv


load_dotenv()

# Memory Limits
MAX_HISTORY = 20
MAX_GROUP_HISTORY = 200

# Environment Variables
BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("OPENROUTER_MODEL")
BOT_USERNAME = os.getenv("BOT_USERNAME")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").lower()


# Group 1: command word, Group 2: optional number
ANALYZE_REGEX_EN = re.compile(r'\b(analyze|analyse|analiz)\s*(\d*)\b', re.IGNORECASE)

ANALYZE_REGEX_RU = re.compile(r'\b(анализ|аналез|анали[зсх])\s*(\d*)\b', re.IGNORECASE)

BOT_MENTION_REGEX = re.compile(rf'@{re.escape(BOT_USERNAME)}\s*', re.IGNORECASE)