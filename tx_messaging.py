from datetime import datetime
import logging
from typing import Optional, Union
import pytz
import os

from telegram import CallbackQuery, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from lunchable.models import TransactionObject

from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from utils import Keyboard, clean_md, make_tag


logger = logging.getLogger("messaging")


def get_tx_buttons(
    transaction: Union[TransactionObject, int],
    collapsed=True,
) -> InlineKeyboardMarkup:
    """Returns a list of buttons to be displayed for a transaction."""
    # if transaction is an int, it's a transaction_id
    if isinstance(transaction, int):
        transaction_id = transaction
        # assume the transaction is persisted if a transaction_id is provided
        tx = get_db().get_tx_by_id(transaction_id)
        if tx is None:
            raise ValueError(f"Transaction {transaction_id} not in the database")
        recurring_type, is_pending, is_reviewed = (
            tx.recurring_type,
            tx.pending,
            tx.reviewed_at is not None,
        )
    else:
        transaction_id = transaction.id
        recurring_type = transaction.recurring_type
        is_pending = transaction.is_pending
        is_reviewed = transaction.status == "cleared"

    kbd = Keyboard()
    if collapsed:
        kbd += ("☷", f"moreOptions_{transaction_id}")

    # recurring transactions are not categorizable
    categorize = recurring_type is None
    if categorize and not collapsed:
        kbd += ("Categorize", f"categorize_{transaction_id}")
        if os.getenv("DEEPINFRA_API_KEY"):
            kbd += ("Auto-categorize 🪄", f"autocategorize_{transaction_id}")

    if not collapsed:
        kbd += ("Rename payee", f"renamePayee_{transaction_id}")
        kbd += ("Set notes", f"editNotes_{transaction_id}")
        kbd += ("Set tags", f"setTags_{transaction_id}")
        kbd += ("Plaid details", f"plaid_{transaction_id}")

        skip = not is_pending
        if skip and not is_reviewed:
            kbd += ("Skip", f"skip_{transaction_id}")

        if is_reviewed:
            kbd += ("Unreview", f"unreview_{transaction_id}")

    if not is_reviewed and not is_pending:
        kbd += ("Reviewed ✓", f"review_{transaction_id}")

    if not is_pending and not collapsed:
        kbd += ("⬒ Collapse", f"collapse_{transaction_id}")

    return kbd.build()


async def send_transaction_message(
    context: ContextTypes.DEFAULT_TYPE,
    transaction: TransactionObject,
    chat_id: Union[str, int],
    message_id: Optional[int] = None,
    reply_to_message_id: Optional[int] = None,
) -> int:
    """Sends a message to the chat_id with the details of a transaction.
    If message_id is provided, edits the existing"""
    settings = get_db().get_current_settings(chat_id)
    show_datetime = settings.show_datetime if settings else True
    tagging = settings.tagging if settings else True

    # Get the datetime from plaid_metadata
    if transaction.plaid_metadata:
        authorized_datetime = transaction.plaid_metadata.get(
            "authorized_datetime", None
        )
        if authorized_datetime:
            date_time = datetime.fromisoformat(
                authorized_datetime.replace("Z", "-02:00")
            )
            pst_tz = pytz.timezone("US/Pacific")
            pst_date_time = date_time.astimezone(pst_tz)
            if show_datetime:
                formatted_date_time = pst_date_time.strftime(
                    "%a, %b %d at %I:%M %p PST"
                )
            else:
                formatted_date_time = transaction.date.strftime("%a, %b %d")
        else:
            formatted_date_time = transaction.plaid_metadata.get("date")
    elif show_datetime:
        formatted_date_time = transaction.date.strftime("%a, %b %d at %I:%M %p")
    else:
        formatted_date_time = transaction.date.strftime("%a, %b %d")

    recurring = ""
    if transaction.recurring_type:
        recurring = "(recurring 🔄)"

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
        reviewed_watermark = "\u200B"
    else:
        reviewed_watermark = "\u200C"

    message = f"*{clean_md(transaction.payee)}* {reviewed_watermark} {recurring} {split_transaction}\n\n"
    message += f"*Amount*: `{explicit_sign}{abs(transaction.amount):,.2f}` `{transaction.currency.upper()}`\n"
    message += f"*Date/Time*: {formatted_date_time}\n"

    # Get category and category group
    category_group = transaction.category_group_name
    if category_group is not None:
        category_group = make_tag(
            category_group, title=True, tagging=tagging, no_emojis=True
        )
        category_group = f"{category_group} / "

    category_name = transaction.category_name or "Uncategorized"
    message += (
        f"*Category*: {category_group}{make_tag(category_name, tagging=tagging)} \n"
    )

    acct_name = (
        transaction.plaid_account_display_name
        or transaction.account_display_name
        or "Unknown Account"
    )
    message += f"*Account*: {make_tag(acct_name, tagging=tagging)}\n"
    if transaction.notes:
        message += f"*Notes*: {transaction.notes}\n"
    if transaction.tags:
        tags = [f"{make_tag(tag.name)}" for tag in transaction.tags]
        message += f"*Tags*: {', '.join(tags)}\n"

    logger.info(f"Sending message to chat_id {chat_id}: {message}")
    if message_id:
        # edit existing message
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_tx_buttons(transaction),
            )
        except Exception as e:
            if "Message is not modified" in str(e):
                logger.debug(f"Message is not modified, skipping edit ({message_id})")
            else:
                raise e
        return message_id
    else:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_tx_buttons(transaction),
            reply_to_message_id=reply_to_message_id,
        )
        return msg.id


async def send_plaid_details(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    transaction_id: int,
    plaid_details: str,
):
    """Sends the plaid details of a transaction to the chat_id."""
    await context.bot.send_message(
        chat_id=chat_id,
        text=plaid_details,
        parse_mode=ParseMode.MARKDOWN,
        reply_to_message_id=query.message.message_id,
    )

    lunch = get_lunch_client_for_chat_id(chat_id)
    transaction = lunch.get_transaction(transaction_id)

    await query.edit_message_reply_markup(reply_markup=get_tx_buttons(transaction))
