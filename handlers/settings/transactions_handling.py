from textwrap import dedent

from telegram import InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from persistence import Settings, get_db
from telegram_extensions import Update
from utils import Keyboard


def get_transactions_handling_text(chat_id: int) -> str | None:
    settings = get_db().get_current_settings(chat_id)
    if settings is None:
        return None

    return dedent(
        f"""
        🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂 \\- *Transactions Handling*

        ➊ *Auto\\-mark transactions as reviewed*: {"🟢 ᴏɴ" if settings.auto_mark_reviewed else "🔴 ᴏꜰꜰ"}
        > When enabled, transactions will be marked as reviewed automatically after being sent to Telegram\\.
        > When disabled, you need to explicitly mark them as reviewed\\.


        ➋ *Mark as reviewed after categorization*: {"🟢 ᴏɴ" if settings.mark_reviewed_after_categorized else "🔴 ᴏꜰꜰ"}
        > When enabled, transactions will be marked as reviewed automatically after being categorized\\.


        ➌ *Auto\\-categorize after adding notes*: {"🟢 ᴏɴ" if settings.auto_categorize_after_notes else "🔴 ᴏꜰꜰ"}
        > When enabled, automatically runs auto\\-categorization after a note is added to a transaction\\.
        > _Requires AI to be enabled_\\.


        ➍ *Account Filtering*
        > Configure which accounts should be ignored for transaction notifications\\.


        ➎ *Sync delete with Lunch Money*: {"🟢 ᴏɴ" if settings.sync_delete_with_lunchmoney else "🔴 ᴏꜰꜰ"}
        > When enabled, dismissing a transaction message will also delete it from Lunch Money\\.
        > _Disabled by default\\. Only works for manually\\-created transactions\\._
        """
    )


def get_transactions_handling_buttons(settings: Settings) -> InlineKeyboardMarkup:
    kbd = Keyboard()
    kbd += ("➊ Auto-mark reviewed?", f"toggleAutoMarkReviewed_{settings.auto_mark_reviewed}")
    kbd += ("➋ Mark reviewed after categorization?", "toggleMarkReviewedAfterCategorized")
    kbd += ("➌ Auto-categorize after notes?", f"toggleAutoCategorizeAfterNotes_{settings.auto_categorize_after_notes}")
    kbd += ("➍ Account Filtering", "accountFilteringSettings")
    kbd += ("➎ Sync delete with Lunch Money?", "toggleSyncDeleteWithLunchMoney")
    kbd += ("Back", "settingsMenu")
    return kbd.build()


async def handle_transactions_handling_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings_text = get_transactions_handling_text(update.chat_id)
    if settings_text:
        settings = get_db().get_current_settings(update.chat_id)
        await update.safe_edit_message_text(
            text=settings_text,
            reply_markup=get_transactions_handling_buttons(settings),
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def handle_btn_toggle_auto_mark_reviewed(update: Update, _: ContextTypes.DEFAULT_TYPE):
    settings = get_db().get_current_settings(update.chat_id)
    get_db().update_auto_mark_reviewed(update.chat_id, not settings.auto_mark_reviewed)

    await update.safe_edit_message_text(
        text=get_transactions_handling_text(update.chat_id),
        reply_markup=get_transactions_handling_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_toggle_mark_reviewed_after_categorized(update: Update, _: ContextTypes.DEFAULT_TYPE):
    settings = get_db().get_current_settings(update.chat_id)
    get_db().update_mark_reviewed_after_categorized(update.chat_id, not settings.mark_reviewed_after_categorized)

    await update.safe_edit_message_text(
        text=get_transactions_handling_text(update.chat_id),
        reply_markup=get_transactions_handling_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_toggle_auto_categorize_after_notes(update: Update, _: ContextTypes.DEFAULT_TYPE):
    settings = get_db().get_current_settings(update.chat_id)
    get_db().update_auto_categorize_after_notes(update.chat_id, not settings.auto_categorize_after_notes)

    await update.safe_edit_message_text(
        text=get_transactions_handling_text(update.chat_id),
        reply_markup=get_transactions_handling_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_toggle_sync_delete_with_lunchmoney(update: Update, _: ContextTypes.DEFAULT_TYPE):
    settings = get_db().get_current_settings(update.chat_id)
    get_db().update_sync_delete_with_lunchmoney(update.chat_id, not settings.sync_delete_with_lunchmoney)

    await update.safe_edit_message_text(
        text=get_transactions_handling_text(update.chat_id),
        reply_markup=get_transactions_handling_buttons(get_db().get_current_settings(update.chat_id)),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
