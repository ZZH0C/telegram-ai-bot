import os
import logging
import html
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("OPENROUTER_MODEL")

SYSTEM_PROMPT = "Your answer should contain minimal required info. Less is better. It should contain less than 1200 characters. Be direct and concise."


# Initialize OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    timeout=30.0,
    default_headers={
        "HTTP-Referer": "https://github.com/ZZH0C/telegram-ai-bot", 
        "X-Title": "Telegram AI Bot"
    }
)

# Simple in-memory conversation history
user_histories = {}
MAX_HISTORY = 20

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I'm an AI assistant powered by OpenRouter.\n"
        f"Send me any message and I'll reply. Conversation history limit currently is {MAX_HISTORY} messages.\n"
        "Type /clear to reset conversation."
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

    user_histories[user_id].append({"role": "user", "content": text})

    if len(user_histories[user_id]) > MAX_HISTORY:
        user_histories[user_id] = user_histories[user_id][-MAX_HISTORY:]

    # 1. Show "typing..." status
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    try:

        messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}] + user_histories[user_id]

        # 2. Call OpenRouter API
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages_for_api,
            max_tokens=1000,
            temperature=0.7
        )
        ai_reply = response.choices[0].message.content
        user_histories[user_id].append({"role": "assistant", "content": ai_reply})
        await update.message.reply_text(ai_reply)
        
    except Exception as e:
        logging.error(f"OpenRouter API error: {e}")
        
        # Remove the failed message from history so it doesn't break future context
        user_histories[user_id].pop() 
        
        # 3. Format error as monospace using HTML
        # We use html.escape to prevent breaking the formatting if the error contains < or >
        error_text = html.escape(str(e))
        await update.message.reply_text(
            f"<b>⚠️ API Error:</b>\n<code>{error_text}</code>", 
            parse_mode="HTML"
        )

def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    
    if not BOT_TOKEN or not OPENROUTER_API_KEY:
        raise ValueError("Missing tokens in .env")

    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
