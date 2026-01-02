import logging
import os
from datetime import datetime

import pytz
import telegram.error
from lunchable.models import TransactionObject
from telegram import InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from telegram_extensions import Update
from utils import Keyboard, clean_md, make_tag

logger = logging.getLogger("messaging")


def _add_expanded_buttons(
    kbd: Keyboard, transaction_id: int, recurring_type, is_pending: bool, is_reviewed: bool, plaid_id, ai_agent=False
) -> Keyboard:
    """Adds buttons for the expanded view of a transaction."""
    # recurring transactions are not categorizable
    categorize = recurring_type is None
    if categorize:
        kbd += ("Categorize", f"categorize_{transaction_id}")
        if os.getenv("OPENROUTER_API_KEY"):
            kbd += ("AI-categorize 🪄", f"aicategorize_{transaction_id}")

    # These are disabled when AI Agent is enabled
    if not ai_agent:
        kbd += ("Rename payee", f"renamePayee_{transaction_id}")
        kbd += ("Set notes", f"editNotes_{transaction_id}")
        kbd += ("Set tags", f"setTags_{transaction_id}")

    if plaid_id:
        kbd += ("Plaid details", f"plaid_{transaction_id}")

    if not is_pending and not is_reviewed:
        kbd += ("Skip", f"skip_{transaction_id}")

    if is_reviewed:
        kbd += ("Unreview", f"unreview_{transaction_id}")

    # Add Refresh button in expanded state
    kbd += ("Refresh", f"refresh_{transaction_id}")

    return kbd


def get_tx_buttons(chat_id: int, transaction: TransactionObject | int, collapsed=True) -> InlineKeyboardMarkup:
    """Returns a list of buttons to be displayed for a transaction."""
    # if transaction is an int, it's a transaction_id, so we fetch it from the API
    if isinstance(transaction, int):
        lunch = get_lunch_client_for_chat_id(chat_id)
        # assume the transaction is persisted if a transaction_id is provided
        tx_id = transaction
        transaction = lunch.get_transaction(tx_id)

    # Fetch settings and ai_agent value
    settings = get_db().get_current_settings(chat_id)
    ai_agent = settings.ai_agent if settings else False

    tx_id = transaction.id
    is_pending = transaction.is_pending
    is_reviewed = transaction.status == "cleared"

    kbd = Keyboard()
    if collapsed:
        kbd += ("☷", f"moreOptions_{tx_id}")
    elif not collapsed:
        kbd = _add_expanded_buttons(
            kbd,
            tx_id,
            transaction.recurring_type,
            is_pending or False,
            is_reviewed,
            transaction.plaid_account_id,
            ai_agent,
        )

    if not is_reviewed and not is_pending:
        # we can't mark a pending transaction as reviewed
        kbd += ("Reviewed ✓", f"review_{tx_id}")

    if not collapsed:
        kbd += ("⬒ Collapse", f"collapse_{tx_id}")

    return kbd.build()


def format_transaction_datetime(transaction: TransactionObject, show_datetime: bool) -> str:
    """Format the transaction's date/time string for display."""
    if transaction.plaid_metadata:
        authorized_datetime = transaction.plaid_metadata.get("authorized_datetime", None)
        if authorized_datetime:
            date_time = datetime.fromisoformat(authorized_datetime.replace("Z", "-02:00"))
            pst_tz = pytz.timezone("US/Pacific")
            pst_date_time = date_time.astimezone(pst_tz)
            if show_datetime:
                return pst_date_time.strftime("%a, %b %d at %I:%M %p PST")
            else:
                return transaction.date.strftime("%a, %b %d")
        else:
            return transaction.plaid_metadata.get("date") or ""
    elif show_datetime:
        return transaction.date.strftime("%a, %b %d at %I:%M %p")
    else:
        return transaction.date.strftime("%a, %b %d")


def format_transaction_message(transaction: TransactionObject, tagging: bool, show_datetime: bool) -> str:
    """Format the message string for a transaction."""
    formatted_date_time = format_transaction_datetime(transaction, show_datetime)

    recurring = ""
    if transaction.recurring_type:
        recurring = "(recurring 🔄)"

    pending = ""
    if transaction.is_pending:
        pending = " `pending`"

    split_transaction = ""
    if transaction.parent_id:
        split_transaction = "🔀"

    explicit_sign = ""
    if transaction.amount < 0:
        # lunch money shows credits as negative
        # here I just want to denote that this was a credit by
        # explicitly showing a + sign before the amount
        explicit_sign = "➕"

    is_reviewed = transaction.status == "cleared"
    if is_reviewed:
        reviewed_watermark = "\u200b"
    else:
        reviewed_watermark = "\u200c"

    message = f"*{clean_md(transaction.payee or '')}* {reviewed_watermark}{pending} {recurring} {split_transaction}\n\n"
    message += f"*Amount*: `{explicit_sign}{abs(transaction.amount):,.2f}` `{transaction.currency.upper() if transaction.currency else ''}`\n"
    message += f"*Date/Time*: {formatted_date_time}\n"

    # Get category and category group
    category_group = transaction.category_group_name
    if category_group is not None:
        category_group = make_tag(category_group or "", title=True, tagging=tagging, no_emojis=True)
        category_group = f"{category_group} / "
    else:
        category_group = ""

    category_name = transaction.category_name or "Uncategorized"
    message += f"*Category*: {category_group}{make_tag(category_name, tagging=tagging)} \n"

    acct_name = transaction.plaid_account_display_name or transaction.account_display_name

    asset_name = ""
    if (acct_name is None or acct_name == "") and transaction.asset_institution_name:
        acct_name = transaction.asset_institution_name
        asset_name = make_tag(transaction.asset_name or "", tagging=tagging)
        asset_name = f" / {asset_name}"

    if acct_name is None or acct_name == "":
        acct_name = "Unknown Account"

    message += f"*Account*: {make_tag(acct_name, tagging=tagging)}{asset_name}\n"
    if transaction.notes:
        message += f"*Notes*: {transaction.notes}\n"
    if transaction.tags:
        tags = [f"{make_tag(tag.name)}" for tag in transaction.tags]
        message += f"*Tags*: {', '.join(tags)}\n"

    return message


def format_compact_transaction_message(transaction: TransactionObject, tagging: bool) -> str:
    """Format the message string for a transaction in a compact view."""
    explicit_sign = ""
    if transaction.amount < 0:
        # lunch money shows credits as negative
        # here I just want to denote that this was a credit by
        # explicitly showing a + sign before the amount
        explicit_sign = "➕"
    category_name = transaction.category_name or "Uncategorized"
    return f"*{transaction.payee}* `{explicit_sign}{abs(transaction.amount):,.2f}` {make_tag(category_name, tagging=tagging)}"


def get_rendered_transaction_message(chat_id: str | int, transaction: TransactionObject, detailed_view: bool = False):
    settings = get_db().get_current_settings(chat_id)
    # Ensure settings fields are bool, not SQLAlchemy Columns
    show_datetime = settings.show_datetime if settings else True
    tagging = settings.tagging if settings else True
    compact_view_enabled = settings.compact_view if settings else False

    if compact_view_enabled and not detailed_view:
        return format_compact_transaction_message(transaction, tagging)
    else:
        return format_transaction_message(transaction, tagging, show_datetime)


async def _handle_blocked_user_error(e: telegram.error.Forbidden, chat_id: str | int) -> bool:
    """Handle Forbidden error when user blocks the bot. Returns True if user was blocked."""
    if "bot was blocked by the user" in str(e):
        logger.warning(f"User {chat_id} has blocked the bot, marking as blocked")
        get_db().mark_user_as_blocked(int(chat_id))
        return True
    return False


async def send_transaction_message(
    context: ContextTypes.DEFAULT_TYPE,
    transaction: TransactionObject,
    chat_id: str | int,
    message_id: int | None = None,
    reply_to_message_id: int | None = None,
) -> int:
    """Sends a message to the chat_id with the details of a transaction.
    If message_id is provided, edits the existing"""

    message = get_rendered_transaction_message(chat_id, transaction)

    logger.info(f"Sending message to chat_id {chat_id} (tx id: {transaction.id}): {message}")
    get_db().inc_metric("sent_transaction_messages")

    if message_id:
        # edit existing message
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_tx_buttons(int(chat_id), transaction.id),
            )
        except telegram.error.BadRequest as e:
            if "Can't parse entities" in str(e):
                logger.warning(f"Markdown parsing failed for edit in chat_id {chat_id}, retrying without markdown: {e}")
                # Retry without markdown formatting
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=message,
                    reply_markup=get_tx_buttons(int(chat_id), transaction.id),
                )
            elif "Message is not modified" in str(e):
                logger.debug(f"Message is not modified, skipping edit ({message_id})")
            else:
                raise
        except telegram.error.Forbidden as e:
            if await _handle_blocked_user_error(e, chat_id):
                return -1
            raise
        except Exception as e:
            if "Message is not modified" in str(e):
                logger.debug(f"Message is not modified, skipping edit ({message_id})")
            else:
                raise
        return message_id

    # send new message
    try:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_tx_buttons(int(chat_id), transaction),
            reply_to_message_id=reply_to_message_id,
        )
    except telegram.error.BadRequest as e:
        if "Can't parse entities" in str(e):
            logger.warning(f"Markdown parsing failed for chat_id {chat_id}, sending without markdown: {e}")
            # Retry without markdown formatting
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=get_tx_buttons(int(chat_id), transaction),
                reply_to_message_id=reply_to_message_id,
            )
        else:
            raise
    except telegram.error.Forbidden as e:
        if await _handle_blocked_user_error(e, chat_id):
            return -1
        raise
    except Exception:
        logger.exception(f"Failed to send message for chat_id {chat_id}")
        raise

    return msg.id


async def send_plaid_details(
    update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, transaction_id: int, plaid_details: str
):
    """Sends the plaid details of a transaction to the chat_id."""
    # Create close button for the plaid details message
    close_kbd = Keyboard()
    close_kbd += ("❌ Close", f"closeplaid_{transaction_id}")
    close_keyboard = close_kbd.build(columns=1)

    await context.bot.send_message(
        chat_id=chat_id,
        text=plaid_details,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=close_keyboard,
        reply_to_message_id=update.callback_query.message.message_id
        if update.callback_query and update.callback_query.message
        else None,
    )

    lunch = get_lunch_client_for_chat_id(chat_id)
    transaction = lunch.get_transaction(transaction_id)

    await update.safe_edit_message_reply_markup(reply_markup=get_tx_buttons(chat_id, transaction))
