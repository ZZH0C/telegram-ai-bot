import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("OPENROUTER_MODEL", "tencent/hy3:free")

# Initialize OpenRouter client (OpenAI-compatible)
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    timeout=30.0
)

# Simple in-memory conversation history (per user)
user_histories = {}

# Keep max 10 message pairs per user to avoid context overflow
MAX_HISTORY = 20

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I'm an AI assistant powered by OpenRouter.\n"
        "Send me any message and I'll reply. Type /clear to reset conversation."
    )

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_histories.pop(user_id, None)
    await update.message.reply_text("🧹 Conversation history cleared.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if user_id not in user_histories:
        user_histories[user_id] = []

    # Add user message
    user_histories[user_id].append({"role": "user", "content": text})

    # Trim history if too long
    if len(user_histories[user_id]) > MAX_HISTORY:
        user_histories[user_id] = user_histories[user_id][-MAX_HISTORY:]

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=user_histories[user_id],
            max_tokens=512,
            temperature=0.7
        )
        ai_reply = response.choices[0].message.content
        user_histories[user_id].append({"role": "assistant", "content": ai_reply})
        await update.message.reply_text(ai_reply)
    except Exception as e:
        logging.error(f"OpenRouter API error: {e}")
        await update.message.reply_text("⚠️ I couldn't process your request right now. Please try again in a moment.")

def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    
    if not BOT_TOKEN or not OPENROUTER_API_KEY:
        raise ValueError("Missing TG_BOT_TOKEN or OPENROUTER_API_KEY in .env")

    # Build the bot application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
