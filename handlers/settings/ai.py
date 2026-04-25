import os
from textwrap import dedent

from telegram import InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from persistence import get_db
from telegram_extensions import Update
from utils import Keyboard

DEFAULT_AI_MODEL = "anthropic/claude-haiku-4.5"


def get_configured_ai_model() -> str:
    """Return the AI model configured via the AI_MODEL env var."""
    return os.getenv("AI_MODEL", DEFAULT_AI_MODEL)


def get_ai_settings_text(chat_id: int) -> str | None:
    settings = get_db().get_current_settings(chat_id)
    if settings is None:
        return None

    model_display = get_configured_ai_model().replace(".", "\\.").replace("-", "\\-")

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

        4️⃣ *AI Model*: {model_display}
        > The AI model is configured by the server administrator and cannot be changed from here\\.
        """
    )


def get_ai_settings_buttons() -> InlineKeyboardMarkup:
    kbd = Keyboard()
    kbd += ("1️⃣ Toggle AI Mode", "toggleAIAgent")
    kbd += ("2️⃣ Toggle Show Transcription", "toggleShowTranscription")
    kbd += ("3️⃣ Set Response Language", "setAILanguage")
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
