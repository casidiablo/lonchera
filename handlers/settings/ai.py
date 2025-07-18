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

        ➊ *AI Agent*: {"🟢 ᴇɴᴀʙʟᴇᴅ" if settings.ai_agent else "🔴 ᴅɪꜱᴀʙʟᴇᴅ"}
        > When enabled, messages \\(including voice messages\\) will be processed by an AI agent\\.
        >
        > The agent is able to use the Lunch Money API to inspect transactions, accounts, and create transactions in manually\\-managed accounts\\.
        >
        > Replying to a transaction message will make the agent work on that transactions, e\\.g\\. adding notes, tags, recategorizing it, etc\\.
        """
    )


def get_ai_settings_buttons(settings: Settings) -> InlineKeyboardMarkup:
    kbd = Keyboard()
    kbd += ("➊ Toggle AI Mode", "toggleAIAgent")
    kbd += ("Back", "settingsMenu")
    return kbd.build()


async def handle_ai_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings_text = get_ai_settings_text(update.effective_chat.id)
    settings = get_db().get_current_settings(update.effective_chat.id)
    await update.callback_query.edit_message_text(
        text=settings_text, reply_markup=get_ai_settings_buttons(settings), parse_mode=ParseMode.MARKDOWN_V2
    )


async def handle_btn_toggle_ai_agent(update: Update, _: ContextTypes.DEFAULT_TYPE):
    settings = get_db().get_current_settings(update.effective_chat.id)
    get_db().update_ai_agent(update.effective_chat.id, not settings.ai_agent)

    # Get updated settings for the button display
    updated_settings = get_db().get_current_settings(update.effective_chat.id)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=get_ai_settings_text(update.effective_chat.id),
        reply_markup=get_ai_settings_buttons(updated_settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
