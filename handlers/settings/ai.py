from textwrap import dedent

from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from persistence import Settings, get_db
from utils import Keyboard


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
        """
    )


def get_ai_settings_buttons(settings: Settings) -> InlineKeyboardMarkup:
    kbd = Keyboard()
    kbd += ("1️⃣ Toggle AI Mode", "toggleAIAgent")
    kbd += ("2️⃣ Toggle Show Transcription", "toggleShowTranscription")
    kbd += ("3️⃣ Set Response Language", "setAILanguage")
    kbd += ("Back", "settingsMenu")
    return kbd.build()


async def handle_ai_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.callback_query:
        return

    settings_text = get_ai_settings_text(update.effective_chat.id)
    if settings_text is None:
        return

    settings = get_db().get_current_settings(update.effective_chat.id)
    await update.callback_query.edit_message_text(
        text=settings_text, reply_markup=get_ai_settings_buttons(settings), parse_mode=ParseMode.MARKDOWN_V2
    )


async def handle_btn_toggle_ai_agent(update: Update, _: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.callback_query:
        return

    settings = get_db().get_current_settings(update.effective_chat.id)
    get_db().update_ai_agent(update.effective_chat.id, not settings.ai_agent)

    # Get updated settings for the button display
    updated_settings = get_db().get_current_settings(update.effective_chat.id)
    settings_text = get_ai_settings_text(update.effective_chat.id)

    if settings_text is None:
        return

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=settings_text, reply_markup=get_ai_settings_buttons(updated_settings), parse_mode=ParseMode.MARKDOWN_V2
    )


async def handle_btn_toggle_show_transcription(update: Update, _: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.callback_query:
        return

    settings = get_db().get_current_settings(update.effective_chat.id)
    get_db().update_show_transcription(update.effective_chat.id, not settings.show_transcription)

    # Get updated settings for the button display
    updated_settings = get_db().get_current_settings(update.effective_chat.id)
    settings_text = get_ai_settings_text(update.effective_chat.id)

    if settings_text is None:
        return

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=settings_text, reply_markup=get_ai_settings_buttons(updated_settings), parse_mode=ParseMode.MARKDOWN_V2
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
    if not update.effective_chat or not update.callback_query:
        return

    await update.callback_query.edit_message_text(
        text="🌍 *Choose AI Response Language*\n\nSelect the language for AI agent responses:",
        reply_markup=get_language_selection_buttons(),
        parse_mode=ParseMode.MARKDOWN_V2
    )


async def handle_set_language(update: Update, _: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.callback_query:
        return

    # Extract language from callback data
    callback_data = update.callback_query.data
    if not callback_data or not callback_data.startswith("setLanguage_"):
        return

    language_code = callback_data.replace("setLanguage_", "")
    language = None if language_code == "none" else language_code

    get_db().update_ai_response_language(update.effective_chat.id, language)

    # Return to AI settings
    settings = get_db().get_current_settings(update.effective_chat.id)
    settings_text = get_ai_settings_text(update.effective_chat.id)

    if settings_text is None:
        return

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=settings_text, reply_markup=get_ai_settings_buttons(settings), parse_mode=ParseMode.MARKDOWN_V2
    )
