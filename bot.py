import html
import logging
import re
import subprocess

from openai import OpenAI
from telegram import Update, BotCommand
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

import constants
import prompts


client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=constants.OPENROUTER_API_KEY,
    timeout=45.0,
    default_headers={
        "HTTP-Referer": "https://github.com/ZZH0C/telegram-ai-bot",
        "X-Title": "Telegram AI Bot"
    }
)

# Memory Stores
user_histories = {}
group_histories = {}


def get_version() -> str:
    """Dynamically gets version based on Git commit count, with a fallback."""
    try:
        commit_count = subprocess.check_output(['git', 'rev-list', '--count', 'HEAD']).decode('utf-8').strip()
        return f"v0.{commit_count}A"
    except Exception:
        return "v0.A"  # Fallback if git is not available


def format_for_telegram(text: str) -> str:
    """Converts standard Markdown from AI to Telegram-compatible HTML."""
    text = html.escape(text)
    text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    text = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[([^]]+)]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'\*([^\n*]+)\*', r'<i>\1</i>', text)
    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👋 Hello! I'm @{constants.BOT_USERNAME}, an AI assistant powered by OpenRouter.\n"
        f"Send me any message and I'll reply. History limit: {constants.MAX_HISTORY} messages.\n\n"
        f"In groups, tag me (@{constants.BOT_USERNAME}) to talk.\n"
        f"Use '@{constants.BOT_USERNAME} analyze [5-100]' (or 'анализ [5-100]') to analyze the last N (or 50 if empty) messages in the chat. "
        f"I'll look for debates and tell you who was right with proof. No additional info required.\n\n"
        "In case of error try same message again."
    )


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    version = get_version()
    text = (
        f"🤖 **Bot Info** (Version {version})\n\n"
        f"**Commands:**\n"
        f"/start - Start the bot and see greeting\n"
        f"/info - Show this information menu\n"
        f"/clear - Clear your conversation history\n\n"
        f"**Group Shortcuts:**\n"
        f"Tag me (@{constants.BOT_USERNAME}) to ask a question.\n"
        f"Use `@{constants.BOT_USERNAME} analyze [5-100]` (or `анализ [5-100]`) to analyze recent chat."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_histories.pop(user_id, None)
    await update.message.reply_text("🧹 Conversation history cleared.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restricted command to check bot memory status."""
    user = update.message.from_user
    if user.username and user.username.lower() == constants.ADMIN_USERNAME:
        private_msgs_len = sum(len(h) for h in user_histories.values())
        group_msgs_len = sum(len(h) for h in group_histories.values())

        status_text = (
            f"📊 **Bot Status** (Version {get_version()})\n\n"
            f"👤 Active private users: {len(user_histories)}\n"
            f"💬 Private messages in memory: {private_msgs_len}\n"
            f"👥 Active groups: {len(group_histories)}\n"
            f"💬 Group messages in memory: {group_msgs_len}"
        )
        await update.message.reply_text(status_text, parse_mode="Markdown")
    else:
        await update.message.reply_text(f"📊 **Bot Status** (Version {get_version()})\n\n")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    chat_type = update.message.chat.type
    is_group = chat_type in ['group', 'supergroup']

    text = update.message.text or ""
    is_mentioned = is_group and f"@{constants.BOT_USERNAME.lower()}" in text.lower()

    # Maintain Group History Buffer
    if is_group:
        if chat_id not in group_histories:
            group_histories[chat_id] = []

        sender_name = update.message.from_user.first_name
        if update.message.from_user.username:
            sender_name += f" (@{update.message.from_user.username})"

        group_histories[chat_id].append({"user": sender_name, "text": text})
        if len(group_histories[chat_id]) > constants.MAX_GROUP_HISTORY:
            group_histories[chat_id].pop(0)

    # Routing Logic
    try:
        # --- ROUTE A: Group Analyze Command ---
        match = constants.ANALYZE_REGEX_RU.search(text)
        if is_group and is_mentioned and match:
            n_str = match.group(2)
            n = int(n_str) if n_str else 50
            n = min(max(n, 5), 100)

            is_english = bool(constants.ANALYZE_REGEX_EN.search(text))

            history = group_histories.get(chat_id, [])[-n:]
            if not history:
                await update.message.reply_text("⚠️ Not enough message history to analyze yet.",
                                                reply_to_message_id=update.message.message_id)
                return

            formatted_history = "\n".join([f"[{msg['user']}]: {msg['text']}" for msg in history])
            analyze_prompt = (prompts.ANALYZE_PROMPT_EN if is_english else prompts.ANALYZE_PROMPT_RU).format(
                messages=formatted_history)

            messages_for_api = [{"role": "user", "content": analyze_prompt}]

            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            ai_reply = await call_openrouter(messages_for_api)

            await update.message.reply_text(
                format_for_telegram(ai_reply),
                parse_mode="HTML",
                reply_to_message_id=update.message.message_id
            )
            return

        # --- ROUTE B: Group Mention ---
        elif is_group and is_mentioned:
            clean_text = constants.BOT_MENTION_REGEX.sub('', text).strip()
            messages_for_api = [{"role": "system", "content": prompts.SYSTEM_PROMPT}] + [
                {"role": "user", "content": clean_text}]

            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
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

            user_histories[user_id].append({"role": "user", "content": text})
            if len(user_histories[user_id]) > constants.MAX_HISTORY:
                user_histories[user_id] = user_histories[user_id][-constants.MAX_HISTORY:]

            messages_for_api = [{"role": "system", "content": prompts.SYSTEM_PROMPT}] + user_histories[user_id]

            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            ai_reply = await call_openrouter(messages_for_api)

            user_histories[user_id].append({"role": "assistant", "content": ai_reply})
            await update.message.reply_text(format_for_telegram(ai_reply), parse_mode="HTML")

        else:
            return  # Group chat, not mentioned, do nothing

    except BadRequest as e:
        logging.warning(f"HTML parsing failed, sending plain text: {e}")
        fallback_text = locals().get('ai_reply', "⚠️ Error formatting response.")
        await update.message.reply_text(fallback_text,
                                        reply_to_message_id=update.message.message_id if is_group else None)

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
    response = client.chat.completions.create(
        model=constants.MODEL_NAME,
        messages=messages,
        max_tokens=1024,
        temperature=0.7
    )

    if not response or not response.choices:
        raise Exception("The AI model is currently overloaded or rate-limited. Please try again in a moment.")

    choice = response.choices[0]
    if not choice or not choice.message or not choice.message.content:
        raise Exception("The AI returned an empty response. Please try again.")

    return choice.message.content


async def post_init(application: Application) -> None:
    """Sets up the Telegram Menu Commands (excluding /status)"""
    await application.bot.set_my_commands([
        BotCommand("start", "Start the bot and see greeting"),
        BotCommand("info", "Bot info, version, and commands"),
        BotCommand("clear", "Clear your conversation history")
    ])


def main():
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

    if not constants.BOT_TOKEN or not constants.OPENROUTER_API_KEY:
        raise ValueError("Missing tokens in .env")

    app = Application.builder().token(constants.BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"✅ Bot @{constants.BOT_USERNAME} is running with model: {constants.MODEL_NAME} | Version: {get_version()}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
