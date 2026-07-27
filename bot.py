import os
import logging
import html
import re
import base64
import tempfile
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest
from openai import OpenAI

# Load environment variables
load_dotenv()

# CONSTANT: Bot username (without the @)
BOT_USERNAME = "arc_pet_bot"

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = os.getenv("OPENROUTER_MODEL")

SYSTEM_PROMPT = (
    "Your answer should contain minimal required info. Less is better. "
    "It should contain less than 1200 characters. Be direct and concise. "
    "Always reply in plain text or markdown, never try to generate or return image files."
)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    timeout=45.0,
    default_headers={
        "HTTP-Referer": "https://github.com/ZZH0C/telegram-ai-bot", 
        "X-Title": "Telegram AI Bot"
    }
)

# Private chat history
user_histories = {}
MAX_HISTORY = 20

# Group chat rolling buffer (in-memory only, clears on restart)
group_histories = {}
MAX_GROUP_HISTORY = 200

def format_for_telegram(text: str) -> str:
    """Converts standard Markdown from AI to Telegram-compatible HTML."""
    text = html.escape(text)
    text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    text = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'\*([^\n*]+)\*', r'<i>\1</i>', text)
    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Hello! I'm @{BOT_USERNAME}, an AI assistant powered by OpenRouter.\n"
        f"Send me any message (or photo!) and I'll reply. History limit: {MAX_HISTORY} messages.\n"
        f"In groups, tag me (@{BOT_USERNAME}) to talk. Use '@{BOT_USERNAME} analyze [10-100]' to analyze recent chat.\n\n"
        "In case of error try same message again.\n"
        "V0.14"
    )

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_histories.pop(user_id, None)
    await update.message.reply_text("🧹 Conversation history cleared.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    chat_type = update.message.chat.type
    is_group = chat_type in ['group', 'supergroup']
    
    text = update.message.text or update.message.caption or ""
    is_mentioned = is_group and f"@{BOT_USERNAME.lower()}" in text.lower()

    # Handle Image (Download & Convert to Base64 for API)
    image_content = None
    if update.message.photo:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        with tempfile.NamedTemporaryFile(delete=True, suffix=".jpg") as tmp:
            await file.download(custom_path=tmp.name)
            with open(tmp.name, "rb") as f:
                img_base64 = base64.b64encode(f.read()).decode('utf-8')
        image_content = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}

    # Maintain Group History Buffer
    if is_group:
        if chat_id not in group_histories:
            group_histories[chat_id] = []
        
        sender_name = update.message.from_user.first_name
        if update.message.from_user.username:
            sender_name += f" (@{update.message.from_user.username})"
            
        group_histories[chat_id].append({"user": sender_name, "text": text})
        if len(group_histories[chat_id]) > MAX_GROUP_HISTORY:
            group_histories[chat_id].pop(0)

    # Routing Logic
    try:
        # --- ROUTE A: Group Analyze Command ---
        if is_group and is_mentioned and re.search(r'\banalyze\b', text, re.IGNORECASE):
            match = re.search(r'\banalyze\s+(\d+)', text, re.IGNORECASE)
            n = int(match.group(1)) if match else 50
            n = min(max(n, 10), 100)
            
            history = group_histories.get(chat_id, [])[-n:]
            if not history:
                await update.message.reply_text("⚠️ Not enough message history to analyze yet.", reply_to_message_id=update.message.message_id)
                return

            formatted_history = "\n".join([f"[{msg['user']}]: {msg['text']}" for msg in history])
            analyze_prompt = (
                "Analyze these messages. Tell me which user was right if there was some debate "
                "and give me links to proofs why he is right. Be objective, concise, and format nicely.\n\n"
                f"Messages:\n{formatted_history}"
            )
            
            messages_for_api = [{"role": "user", "content": analyze_prompt}]
            ai_reply = await call_openrouter(messages_for_api)
            
            await update.message.reply_text(
                format_for_telegram(ai_reply), 
                parse_mode="HTML", 
                reply_to_message_id=update.message.message_id
            )
            return

        # --- ROUTE B: Group Mention ---
        elif is_group and is_mentioned:
            clean_text = re.sub(rf'@{re.escape(BOT_USERNAME)}\s*', '', text, flags=re.IGNORECASE).strip()
            user_content = [{"type": "text", "text": clean_text}]
            if image_content:
                user_content.append(image_content)
                
            messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}] + [{"role": "user", "content": user_content}]
            ai_reply = await call_openrouter(messages_for_api)
            
            await update.message.reply_text(
                format_for_telegram(ai_reply), 
                parse_mode="HTML", 
                reply_to_message_id=update.message.message_id
            )
            return

        # --- ROUTE C: Private Chat ---
        elif not is_group:
            if user_id not in user_histories:
                user_histories[user_id] = []

            user_content = [{"type": "text", "text": text}]
            if image_content:
                user_content.append(image_content)

            user_histories[user_id].append({"role": "user", "content": user_content})
            if len(user_histories[user_id]) > MAX_HISTORY:
                user_histories[user_id] = user_histories[user_id][-MAX_HISTORY:]

            messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}] + user_histories[user_id]
            ai_reply = await call_openrouter(messages_for_api)
            
            user_histories[user_id].append({"role": "assistant", "content": ai_reply})
            await update.message.reply_text(format_for_telegram(ai_reply), parse_mode="HTML")
            
        else:
            return # Group chat, not mentioned, do nothing

    except BadRequest as e:
        logging.warning(f"HTML parsing failed, sending plain text: {e}")
        fallback_text = locals().get('ai_reply', "⚠️ Error formatting response.")
        await update.message.reply_text(fallback_text, reply_to_message_id=update.message.message_id if is_group else None)
        
    except Exception as e:
        logging.error(f"API Error: {e}")
        if not is_group and user_id in user_histories and user_histories[user_id]:
            user_histories[user_id].pop()
            
        error_text = html.escape(str(e))
        await update.message.reply_text(
            f"<b>⚠️ API Error:</b>\n<code>{error_text}</code>", 
            parse_mode="HTML",
            reply_to_message_id=update.message.message_id if is_group else None
        )

async def call_openrouter(messages: list) -> str:
    """Helper function with SAFE EXTRACTION to prevent NoneType errors."""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        max_tokens=1024,
        temperature=0.7
    )
    
    # 1. Check if response or choices is None (common OpenRouter free tier glitch)
    if not response or not response.choices:
        raise Exception("The AI model is currently overloaded or rate-limited. Please try again in a moment.")
    
    # 2. Safely get the first choice
    choice = response.choices[0]
    if not choice or not choice.message or not choice.message.content:
        raise Exception("The AI returned an empty response. Please try again.")
    
    return choice.message.content

def main():
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
    
    if not BOT_TOKEN or not OPENROUTER_API_KEY:
        raise ValueError("Missing tokens in .env")

    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO, handle_message))
    
    print(f"✅ Bot @{BOT_USERNAME} is running with model: {MODEL_NAME}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
