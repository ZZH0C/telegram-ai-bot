import os
import re

# Bot & Admin Configuration
BOT_USERNAME = os.getenv("BOT_USERNAME", "arc_pet_bot")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").lower() # Must be set in .env

# Memory Limits
MAX_HISTORY = 20
MAX_GROUP_HISTORY = 200

# Regex for analyze command with English/Russian misspell variations
# Matches: analyze, analyse, analiz, анализ, аналих, etc.
# Group 1: command word, Group 2: optional number
ANALYZE_REGEX = re.compile(r'\b(analyze|analyse|analiz)\s*(\d*)\b', re.IGNORECASE)

# Regex to specifically detect if a Russian variation was used
RUSSIAN_ANALYZE_REGEX = re.compile(r'\b(анализ|аналез|анали[зсх])\b', re.IGNORECASE)

# Regex to cleanly strip the bot mention from the text
BOT_MENTION_REGEX = re.compile(rf'@{re.escape(BOT_USERNAME)}\s*', re.IGNORECASE)
