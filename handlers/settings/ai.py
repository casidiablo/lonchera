import os
from textwrap import dedent

from telegram import InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from persistence import get_db
from telegram_extensions import Update
from utils import Keyboard


def get_model_display_name(model: str | None) -> str:
    """Get user-friendly display name for AI model."""
    if not model:
        return "Gemini 2\\.5 Flash \\(Default\\)"

    # Model names with company/model format
    model_names = {
        "openai/gpt-4.1-nano": "GPT\\-4\\.1 Nano",
        "openai/gpt-4.1-mini": "GPT\\-4\\.1 Mini",
        "openai/gpt-4.1": "GPT\\-4\\.1",
        "openai/gpt-4o": "GPT\\-4o",
        "openai/gpt-4o-mini": "GPT\\-4o Mini",
        "openai/o4-mini": "o4\\-mini",
        "google/gemini-2.5-flash": "Gemini 2\\.5 Flash",
        "anthropic/claude-haiku-4.5": "Claude Haiku 4\\.5",
        # handle legacy naming
        "gpt-4.1-nano": "GPT\\-4\\.1 Nano",
        "gpt-4.1-mini": "GPT\\-4\\.1 Mini",
        "gpt-4.1": "GPT\\-4\\.1",
        "gpt-4o": "GPT\\-4o",
        "gpt-4o-mini": "GPT\\-4o Mini",
        "o4-mini": "o4\\-mini",
    }
    return model_names.get(model, f"{model}")


def get_ai_settings_text(chat_id: int) -> str | None:
    settings = get_db().get_current_settings(chat_id)
    if settings is None:
        return None

    return dedent(
        f"""
        🤖 🆂🅴🆃🆃🅸🅽🅶🆂 \\- *AI Settings*

        ➊ *AI Agent*: {"🟢 ᴏɴ" if settings.ai_agent else "🔴 ᴏꜰꜰ"}
        > When enabled, messages \\(including voice messages\\) will be processed by an AI agent\\.
        >
        > The agent is able to use the Lunch Money API to inspect transactions, accounts, and create transactions in manually\\-managed accounts\\.
        >
        > Replying to a transaction message will make the agent work on that transactions, e\\.g\\. adding notes, tags, recategorizing it, etc\\.

        2️⃣ *Show Transcription*: {"🟢 ᴏɴ" if settings.show_transcription else "🔴 ᴏꜰꜰ"}
        > When enabled, the transcription of audio messages will be shown before processing\\.

        3️⃣ *Response Language*: {settings.ai_response_language or "🌐 Auto\\-detect"}
        > Sets the language for AI agent responses\\. When set to auto\\-detect, the agent will respond in the same language as your input\\.

        4️⃣ *AI Model*: {get_model_display_name(settings.ai_model)}
        > Choose the AI model for processing your requests\\. Advanced models may provide better responses\\.
        """
    )


def get_ai_settings_buttons() -> InlineKeyboardMarkup:
    kbd = Keyboard()
    kbd += ("1️⃣ Toggle AI Mode", "toggleAIAgent")
    kbd += ("2️⃣ Toggle Show Transcription", "toggleShowTranscription")
    kbd += ("3️⃣ Set Response Language", "setAILanguage")
    kbd += ("4️⃣ Select AI Model", "setAIModel")
    kbd += ("Back", "settingsMenu")
    return kbd.build()


async def handle_ai_settings(update: Update, _: ContextTypes.DEFAULT_TYPE):
    settings_text = get_ai_settings_text(update.chat_id)
    if settings_text is None:
        return

    await update.safe_edit_message_text(
        text=settings_text, reply_markup=get_ai_settings_buttons(), parse_mode=ParseMode.MARKDOWN_V2
    )


async def handle_btn_toggle_ai_agent(update: Update, _: ContextTypes.DEFAULT_TYPE):
    settings = get_db().get_current_settings(update.chat_id)
    get_db().update_ai_agent(update.chat_id, not settings.ai_agent)

    # Get updated settings for the button display
    settings_text = get_ai_settings_text(update.chat_id)
    if settings_text is None:
        return

    await update.safe_edit_message_text(
        text=settings_text, reply_markup=get_ai_settings_buttons(), parse_mode=ParseMode.MARKDOWN_V2
    )


async def handle_btn_toggle_show_transcription(update: Update, _: ContextTypes.DEFAULT_TYPE):
    settings = get_db().get_current_settings(update.chat_id)
    get_db().update_show_transcription(update.chat_id, not settings.show_transcription)

    # Get updated settings for the button display
    settings_text = get_ai_settings_text(update.chat_id)
    if settings_text is None:
        return

    await update.safe_edit_message_text(
        text=settings_text, reply_markup=get_ai_settings_buttons(), parse_mode=ParseMode.MARKDOWN_V2
    )


def get_language_selection_buttons() -> InlineKeyboardMarkup:
    kbd = Keyboard()
    kbd += ("🌐 Auto-detect", "setLanguage_none")
    kbd += ("🇺🇸 English", "setLanguage_English")
    kbd += ("🇪🇸 Español", "setLanguage_Spanish")
    kbd += ("🇨🇳 中文", "setLanguage_Chinese")
    kbd += ("🇮🇳 हिन्दी", "setLanguage_Hindi")
    kbd += ("🇸🇦 العربية", "setLanguage_Arabic")
    kbd += ("🇧🇷 Português", "setLanguage_Portuguese")
    kbd += ("🇷🇺 Русский", "setLanguage_Russian")
    kbd += ("🇫🇷 Français", "setLanguage_French")
    kbd += ("Back", "aiSettings")
    return kbd.build()


async def handle_set_ai_language(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.safe_edit_message_text(
        text="🌍 *Choose AI Response Language*\n\nSelect the language for AI agent responses:",
        reply_markup=get_language_selection_buttons(),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_set_language(update: Update, _: ContextTypes.DEFAULT_TYPE):
    # Extract language from callback data
    if not update.callback_query or not update.callback_query.data:
        return
    callback_data = update.callback_query.data
    if not callback_data.startswith("setLanguage_"):
        return

    language_code = callback_data.replace("setLanguage_", "")
    language = None if language_code == "none" else language_code

    # Update the language in the database
    get_db().update_ai_response_language(update.chat_id, language)

    # Get settings text and display updated AI settings
    settings_text = get_ai_settings_text(update.chat_id)
    await update.safe_edit_message_text(
        text=settings_text, reply_markup=get_ai_settings_buttons(), parse_mode=ParseMode.MARKDOWN_V2
    )


def get_model_selection_buttons(chat_id: int) -> InlineKeyboardMarkup:
    kbd = Keyboard()
    # Only show advanced models for authorized chat_id
    admin_user_id = os.getenv("ADMIN_USER_ID")
    if admin_user_id and chat_id == int(admin_user_id):
        kbd += ("Gemini 2.5 Flash (Default)", "setModel_none")
        kbd += ("GPT-4.1 Nano", "setModel_openai/gpt-4.1-nano")
        kbd += ("GPT-4.1 Mini", "setModel_openai/gpt-4.1-mini")
        kbd += ("GPT-4.1", "setModel_openai/gpt-4.1")
        kbd += ("GPT-4o", "setModel_openai/gpt-4o")
        kbd += ("GPT-4o Mini", "setModel_openai/gpt-4o-mini")
        kbd += ("o4-mini", "setModel_openai/o4-mini")
        kbd += ("Claude Haiku 4.5", "setModel_anthropic/claude-haiku-4.5")
    else:
        kbd += ("Gemini 2.5 Flash (Only Available)", "setModel_none")
    kbd += ("Back", "aiSettings")
    return kbd.build()


async def handle_set_ai_model(update: Update, _: ContextTypes.DEFAULT_TYPE):
    chat_id = update.chat_id
    admin_user_id = os.getenv("ADMIN_USER_ID")
    if admin_user_id and chat_id == int(admin_user_id):
        message_text = "🤖 *Choose AI Model*\n\nSelect the AI model for processing your requests:"
    else:
        message_text = "🤖 *AI Model Selection*\n\nOnly Llama model is available for your account:"

    await update.safe_edit_message_text(
        text=message_text, reply_markup=get_model_selection_buttons(chat_id), parse_mode=ParseMode.MARKDOWN_V2
    )


async def handle_set_model(update: Update, _: ContextTypes.DEFAULT_TYPE):
    # Extract model from callback data
    if not update.callback_query or not update.callback_query.data:
        return
    callback_data = update.callback_query.data
    if not callback_data.startswith("setModel_"):
        return

    model_code = callback_data.replace("setModel_", "")
    model = None if model_code == "none" else model_code

    # Update the model in the database
    get_db().update_ai_model(update.chat_id, model)

    # Get settings text and display updated AI settings
    settings_text = get_ai_settings_text(update.chat_id)
    await update.safe_edit_message_text(
        text=settings_text, reply_markup=get_ai_settings_buttons(), parse_mode=ParseMode.MARKDOWN_V2
    )
