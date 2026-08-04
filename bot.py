import html
import logging
import re
import subprocess

from openai import OpenAI
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

import constants

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
    try:
        commit_count = subprocess.check_output(['git', 'rev-list', '--count', 'HEAD']).decode('utf-8').strip()
        return f"v0.{commit_count}a"
    except Exception:
        return "v0.0a"


def format_for_telegram(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    text = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[([^]]+)]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text, flags=re.DOTALL)
    text = re.sub(r'\*([^\n*]+)\*', r'<i>\1</i>', text)
    return text


# --- Helper Functions for Settings UI ---
async def _send_settings(target_obj, context: ContextTypes.DEFAULT_TYPE):
    config = constants.get_config()
    # Truncate prompts for display to avoid hitting Telegram's 4096 char limit
    sys_prompt_display = (config['SYSTEM_PROMPT'][:200] + "...") if len(config['SYSTEM_PROMPT']) > 200 else config[
        'SYSTEM_PROMPT']
    en_prompt_display = (config['ANALYZE_PROMPT_EN'][:200] + "...") if len(config['ANALYZE_PROMPT_EN']) > 200 else \
    config['ANALYZE_PROMPT_EN']
    ru_prompt_display = (config['ANALYZE_PROMPT_RU'][:200] + "...") if len(config['ANALYZE_PROMPT_RU']) > 200 else \
    config['ANALYZE_PROMPT_RU']

    text = (
        f"⚙️ **Bot Settings**\n\n"
        f"🤖 **Model:** `{config['MODEL_NAME']}`\n\n"
        f"📝 **System Prompt:**\n`{sys_prompt_display}`\n\n"
        f"🇬🇧 **Analyze EN:**\n`{en_prompt_display}`\n\n"
        f"🇷🇺 **Analyze RU:**\n`{ru_prompt_display}`"
    )
    keyboard = [[InlineKeyboardButton("⚙️ Configure", callback_data="configure_menu")]]

    if hasattr(target_obj, 'reply_text'):  # It's a Message
        await target_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:  # It's a CallbackQuery
        await target_obj.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_configure_menu(target_obj, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🤖 Change Model", callback_data="cfg_MODEL_NAME")],
        [InlineKeyboardButton("📝 Change System Prompt", callback_data="cfg_SYSTEM_PROMPT")],
        [InlineKeyboardButton("🇬🇧 Change Analyze EN", callback_data="cfg_ANALYZE_PROMPT_EN")],
        [InlineKeyboardButton("🇷🇺 Change Analyze RU", callback_data="cfg_ANALYZE_PROMPT_RU")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="show_settings")]
    ]
    text = "⚙️ **What do you want to change?**"
    if hasattr(target_obj, 'reply_text'):
        await target_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await target_obj.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


# --- Command Handlers ---
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
        f"Tag me `@{constants.BOT_USERNAME}` to ask a question.\n\n"
        f"Use `@{constants.BOT_USERNAME} analyze` (or `@{constants.BOT_USERNAME} анализ`) to analyze recent chat.\n"
        f"You can add number from 5 to 100 to analyze specific number of last messages in chat."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_histories.pop(user_id, None)
    await update.message.reply_text("🧹 Conversation history cleared.")


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not constants.is_admin(update.message.from_user.username or ""):
        await update.message.reply_text("🔒 Admin access required.")
        return
    await _send_settings(update.message, context)


async def configure_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not constants.is_admin(update.message.from_user.username or ""):
        await update.message.reply_text("🔒 Admin access required.")
        return
    await _show_configure_menu(update.message, context)


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_config' in context.user_data:
        context.user_data.pop('awaiting_config')
        await update.message.reply_text("❌ Configuration cancelled.")
        if constants.is_admin(update.message.from_user.username or ""):
            await _send_settings(update.message, context)
    else:
        await update.message.reply_text("No active configuration to cancel.")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not constants.is_admin(query.from_user.username or ""):
        await query.edit_message_text("🔒 Admin access required.")
        return

    if query.data == "configure_menu":
        await _show_configure_menu(query, context)
    elif query.data.startswith("cfg_"):
        target = query.data.split("cfg_", 1)[1]
        context.user_data['awaiting_config'] = target
        names = {
            "MODEL_NAME": "Model Name",
            "SYSTEM_PROMPT": "System Prompt",
            "ANALYZE_PROMPT_EN": "Analyze Prompt (English)",
            "ANALYZE_PROMPT_RU": "Analyze Prompt (Russian)"
        }
        await query.edit_message_text(
            f"✏️ You are updating: **{names[target]}**\n\n"
            f"Please send the *exact* new value as your next message.\n\n"
            f"Send `/cancel` to abort.",
            parse_mode="Markdown"
        )
    elif query.data == "show_settings":
        await _send_settings(query, context)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if constants.is_admin(user.username or ""):
        config = constants.get_config()
        private_msgs_len = sum(len(h) for h in user_histories.values())
        group_msgs_len = sum(len(h) for h in group_histories.values())
        status_text = (
            f"📊 **Bot Status** (Version {get_version()})\n\n"
            f"🤖 **Current Model:** `{config['MODEL_NAME']}`\n\n"
            f"👤 Active private users: {len(user_histories)}\n"
            f"💬 Private messages in memory: {private_msgs_len}\n"
            f"👥 Active groups: {len(group_histories)}\n"
            f"💬 Group messages in memory: {group_msgs_len}"
        )
        await update.message.reply_text(status_text, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            f"📊 **Bot Status** (Version {get_version()})\n\n🔒 Admin access required for full details.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat_id = update.message.chat.id
    chat_type = update.message.chat.type
    is_group = chat_type in ['group', 'supergroup']
    text = update.message.text or ""

    # 1. Intercept admin configuration input
    if constants.is_admin(user.username or "") and context.user_data.get('awaiting_config'):
        target = context.user_data.pop('awaiting_config')
        config = constants.get_config()
        config[target] = text
        constants.save_config(config)

        await update.message.reply_text(f"✅ **{target}** updated successfully!", parse_mode="Markdown")
        await _send_settings(update.message, context)
        return

    # 2. Normal Bot Logic
    is_mentioned = is_group and f"@{constants.BOT_USERNAME.lower()}" in text.lower()

    if is_group:
        if chat_id not in group_histories:
            group_histories[chat_id] = []
        sender_name = user.first_name
        if user.username:
            sender_name += f" (@{user.username})"
        group_histories[chat_id].append({"user": sender_name, "text": text})
        if len(group_histories[chat_id]) > constants.MAX_GROUP_HISTORY:
            group_histories[chat_id].pop(0)

    try:
        match_en = constants.ANALYZE_REGEX_EN.search(text)
        match_ru = constants.ANALYZE_REGEX_RU.search(text)

        if is_group and is_mentioned and (match_en or match_ru):
            match = match_ru if match_ru else match_en
            is_russian = bool(match_ru)
            n_str = match.group(2)
            n = int(n_str) if n_str else 50
            n = min(max(n, 5), 100)

            history = group_histories.get(chat_id, [])[-n:]
            if not history:
                await update.message.reply_text("⚠️ Not enough message history to analyze yet.",
                                                reply_to_message_id=update.message.message_id)
                return

            formatted_history = "\n".join([f"[{msg['user']}]: {msg['text']}" for msg in history])
            config = constants.get_config()
            prompt_template = config["ANALYZE_PROMPT_RU"] if is_russian else config["ANALYZE_PROMPT_EN"]
            analyze_prompt = prompt_template.format(messages=formatted_history)
            messages_for_api = [{"role": "user", "content": analyze_prompt}]

            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            ai_reply = await call_openrouter(messages_for_api)
            await update.message.reply_text(format_for_telegram(ai_reply), parse_mode="HTML",
                                            reply_to_message_id=update.message.message_id)
            return

        elif is_group and is_mentioned:
            clean_text = constants.BOT_MENTION_REGEX.sub('', text).strip()
            config = constants.get_config()
            messages_for_api = [{"role": "system", "content": config["SYSTEM_PROMPT"]}] + [
                {"role": "user", "content": clean_text}]

            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            ai_reply = await call_openrouter(messages_for_api)
            await update.message.reply_text(format_for_telegram(ai_reply), parse_mode="HTML",
                                            reply_to_message_id=update.message.message_id)
            return

        elif not is_group:
            if user.id not in user_histories:
                user_histories[user.id] = []
            user_histories[user.id].append({"role": "user", "content": text})
            if len(user_histories[user.id]) > constants.MAX_HISTORY:
                user_histories[user.id] = user_histories[user.id][-constants.MAX_HISTORY:]

            config = constants.get_config()
            messages_for_api = [{"role": "system", "content": config["SYSTEM_PROMPT"]}] + user_histories[user.id]

            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            ai_reply = await call_openrouter(messages_for_api)

            user_histories[user.id].append({"role": "assistant", "content": ai_reply})
            await update.message.reply_text(format_for_telegram(ai_reply), parse_mode="HTML")
        else:
            return

    except BadRequest as e:
        logging.warning(f"HTML parsing failed, sending plain text: {e}")
        fallback_text = locals().get('ai_reply', "⚠️ Error formatting response.")
        await update.message.reply_text(fallback_text,
                                        reply_to_message_id=update.message.message_id if is_group else None)
    except Exception as e:
        logging.error(f"API Error: {e}")
        if not is_group and user.id in user_histories and user_histories[user.id]:
            user_histories[user.id].pop()
        error_text = html.escape(str(e))
        await update.message.reply_text(f"<b>⚠️ API Error:</b>\n<code>{error_text}</code>", parse_mode="HTML",
                                        reply_to_message_id=update.message.message_id if is_group else None)


async def call_openrouter(messages: list) -> str:
    config = constants.get_config()
    primary_model = config["MODEL_NAME"]
    fallback_model = constants.FALLBACK_MODEL

    async def _make_call(model: str) -> str:
        response = client.chat.completions.create(model=model, messages=messages, max_tokens=1024, temperature=0.7)
        if not response or not response.choices:
            raise Exception("The AI model returned no choices.")
        choice = response.choices[0]
        if not choice or not choice.message or not choice.message.content:
            raise Exception("The AI returned an empty response.")
        return choice.message.content

    try:
        return await _make_call(primary_model)
    except Exception as e:
        logging.warning(f"Primary model '{primary_model}' failed: {e}. Attempting fallback '{fallback_model}'...")
        try:
            return await _make_call(fallback_model)
        except Exception as fallback_e:
            logging.error(f"Fallback model also failed: {fallback_e}")
            raise Exception(f"Both models failed. Primary error: {e}")


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("info", "Bot info and commands"),
        BotCommand("clear", "Clear conversation history"),
        BotCommand("settings", "View bot configuration (Admin)"),
        BotCommand("configure", "Change bot settings (Admin)"),
        BotCommand("status", "Check bot memory (Admin)")
    ])


def main():
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
    if not constants.BOT_TOKEN or not constants.OPENROUTER_API_KEY:
        raise ValueError("Missing tokens in .env")

    app = Application.builder().token(constants.BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("configure", configure_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    config = constants.get_config()
    print(f"✅ Bot @{constants.BOT_USERNAME} is running with model: {config['MODEL_NAME']} | Version: {get_version()}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()