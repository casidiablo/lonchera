from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from utils import Keyboard, ensure_token


def get_general_settings_buttons() -> InlineKeyboardMarkup:
    kbd = Keyboard()
    kbd += ("🗓️ Schedule & Rendering", "scheduleRenderingSettings")
    kbd += ("💳 Transactions Handling", "transactionsHandlingSettings")
    kbd += ("🔑 Session", "sessionSettings")
    kbd += ("Done", "doneSettings")
    return kbd.build(columns=1)


async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_token(update)

    await update.message.reply_text(
        text="🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂\n\nPlease choose a settings category:",
        reply_markup=get_general_settings_buttons(),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await context.bot.delete_message(
        chat_id=update.message.chat_id, message_id=update.message.message_id
    )


async def handle_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text(
        text="🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂\n\nPlease choose a settings category:",
        reply_markup=get_general_settings_buttons(),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_done_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # delete message
    await context.bot.delete_message(
        chat_id=update.effective_chat.id,
        message_id=update.callback_query.message.message_id,
    )
