from telegram import InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from telegram_extensions import Update
from utils import Keyboard, ensure_token


def get_general_settings_buttons() -> InlineKeyboardMarkup:
    kbd = Keyboard()
    kbd += ("🗓️ Schedule & Rendering", "scheduleRenderingSettings")
    kbd += ("💳 Transactions Handling", "transactionsHandlingSettings")
    kbd += ("🤖 AI Settings", "aiSettings")
    kbd += ("🔑 Session", "sessionSettings")
    kbd += ("Done", "doneSettings")
    return kbd.build(columns=1)


async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_token(update)

    if update.message:
        await update.message.reply_text(
            text="🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂\n\nPlease choose a settings category:",
            reply_markup=get_general_settings_buttons(),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)


async def handle_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.safe_edit_message_text(
            text="🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂\n\nPlease choose a settings category:",
            reply_markup=get_general_settings_buttons(),
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def handle_btn_done_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # delete message
    if update.effective_chat and update.callback_query and update.callback_query.message:
        await context.bot.delete_message(chat_id=update.chat_id, message_id=update.callback_query.message.message_id)
