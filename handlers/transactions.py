from datetime import datetime, timedelta
import logging
from textwrap import dedent
from typing import List
from lunchable import TransactionUpdateObject
from telegram import ForceReply, Update
from telegram.ext import ContextTypes
from telegram.constants import ReactionEmoji, ParseMode

from deepinfra import auto_categorize
from handlers.expectations import (
    EDIT_NOTES,
    RENAME_PAYEE,
    SET_TAGS,
    set_expectation,
)
from handlers.general import handle_generic_message
from lunch import get_lunch_client_for_chat_id
from lunchable.models import TransactionObject

from persistence import get_db
from tx_messaging import get_tx_buttons, send_plaid_details, send_transaction_message
from utils import Keyboard, find_related_tx

logger = logging.getLogger("tx_handler")


async def check_posted_transactions_and_telegram_them(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> List[TransactionObject]:
    # get date from 30 days ago
    two_weeks_ago = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=30)
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    logger.info(f"Polling for new transactions from {two_weeks_ago} to {now}...")

    lunch = get_lunch_client_for_chat_id(chat_id)
    transactions = lunch.get_transactions(
        status="uncleared",
        pending=False,
        start_date=two_weeks_ago,
        end_date=now,
    )

    logger.info(f"Found {len(transactions)} unreviewed transactions")

    settings = get_db().get_current_settings(chat_id)
    for transaction in transactions:
        if settings.auto_mark_reviewed:
            lunch.update_transaction(
                transaction.id, TransactionUpdateObject(status="cleared")
            )
            transaction.status = "cleared"

        if get_db().was_already_sent(transaction.id):
            # TODO: for debugging purposes, sometimes it would be useful
            # to at least send a message with a reply to the message already sent
            # and potentially udpate its state
            continue

        # check if the current transaction is related to a previously sent one
        # like a payment to a credit card
        related_tx = find_related_tx(transaction, transactions)
        reply_msg_id = None
        if related_tx:
            logger.info(
                f"Found related transaction {related_tx.id} for {transaction.id}"
            )
            reply_msg_id = get_db().get_message_id_associated_with(
                related_tx.id, chat_id
            )

        msg_id = await send_transaction_message(
            context, transaction, chat_id, reply_to_message_id=reply_msg_id
        )
        get_db().mark_as_sent(
            transaction.id,
            chat_id,
            msg_id,
            transaction.recurring_type,
            plaid_id=transaction.plaid_metadata.get("transaction_id", None),
        )

    return transactions


async def check_pending_transactions_and_telegram_them(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
) -> List[TransactionObject]:
    # get date from 15 days ago
    two_weeks_ago = datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=15)
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    logger.info(f"Polling for new transactions from {two_weeks_ago} to {now}...")

    lunch = get_lunch_client_for_chat_id(chat_id)
    transactions = lunch.get_transactions(
        pending=True, start_date=two_weeks_ago, end_date=now
    )
    logger.info(f"Found {len(transactions)} pending transactions")
    transactions = [tx for tx in transactions if tx.is_pending and tx.notes is None]

    logger.info(f"Found {len(transactions)} pending transactions")

    for transaction in transactions:
        if get_db().was_already_sent(transaction.id, pending=True):
            logger.info(f"Skipping already sent pending transaction {transaction.id}")
            continue
        msg_id = await send_transaction_message(context, transaction, chat_id)
        get_db().mark_as_sent(
            transaction.id,
            chat_id,
            msg_id,
            transaction.recurring_type,
            pending=True,
            plaid_id=transaction.plaid_metadata.get("transaction_id", None),
        )

    return transactions


async def handle_check_transactions(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    settings = get_db().get_current_settings(update.effective_chat.id)
    if not settings:
        logger.error(f"No settings found for chat {update.effective_chat.id}!")
        return

    if settings.poll_pending:
        transactions = await check_pending_transactions_and_telegram_them(
            context, chat_id=update.effective_chat.id
        )
    else:
        transactions = await check_posted_transactions_and_telegram_them(
            context, chat_id=update.message.chat_id
        )

    get_db().update_last_poll_at(update.effective_chat.id, datetime.now().isoformat())

    if not transactions:
        await update.message.reply_text("No unreviewed transactions found.")
        return


async def check_pending_transactions(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    transactions = await check_pending_transactions_and_telegram_them(
        context,
        chat_id=update.effective_chat.id,
    )

    if not transactions:
        await update.message.reply_text("No pending transactions found.")
    return


async def handle_btn_skip_transaction(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_reply_markup(reply_markup=None)
    await update.callback_query.answer(
        text="Transaction was left intact. You must review it manually from lunchmoney.app",
        show_alert=True,
    )


async def handle_btn_collapse_transaction(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_reply_markup(
        reply_markup=get_tx_buttons(
            int(update.callback_query.data.split("_")[1]), collapsed=True
        )
    )
    await update.callback_query.answer()


async def handle_btn_cancel_categorization(
    update: Update, _: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    transaction_id = int(query.data.split("_")[1])
    await query.edit_message_reply_markup(reply_markup=get_tx_buttons(transaction_id))
    await query.answer()


async def handle_btn_show_categories(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Updates the message to show the parent categories available"""
    query = update.callback_query
    chat_id = query.message.chat.id
    lunch = get_lunch_client_for_chat_id(chat_id)
    transaction_id = int(query.data.split("_")[1])

    categories = lunch.get_categories()
    kbd = Keyboard()
    for category in categories:
        if category.group_id is None:
            if category.children:
                kbd += (category.name, f"subcategorize_{transaction_id}_{category.id}")
            else:
                kbd += (category.name, f"applyCategory_{transaction_id}_{category.id}")

    kbd += ("Cancel", f"cancelCategorization_{transaction_id}")

    await query.edit_message_reply_markup(reply_markup=kbd.build(columns=2))
    await query.answer()


async def handle_btn_show_subcategories(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Updates the transaction with the selected category."""
    query = update.callback_query
    transaction_id, category_id = query.data.split("_")[1:]

    chat_id = query.message.chat.id
    lunch = get_lunch_client_for_chat_id(chat_id)
    subcategories = lunch.get_categories()
    kbd = Keyboard()
    for subcategory in subcategories:
        if str(subcategory.group_id) == str(category_id):
            kbd += (
                subcategory.name,
                f"applyCategory_{transaction_id}_{subcategory.id}",
            )
    kbd += ("Cancel", f"cancelCategorization_{transaction_id}")

    await query.edit_message_reply_markup(reply_markup=kbd.build(columns=2))
    await query.answer()


async def handle_btn_apply_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Updates the transaction with the selected category."""
    query = update.callback_query
    chat_id = query.message.chat.id

    transaction_id, category_id = query.data.split("_")[1:]
    lunch = get_lunch_client_for_chat_id(chat_id)

    settings = get_db().get_current_settings(chat_id)
    if settings.mark_reviewed_after_categorized:
        lunch.update_transaction(
            transaction_id,
            TransactionUpdateObject(category_id=category_id, status="cleared"),
        )
        get_db().mark_as_reviewed(query.message.message_id, chat_id)
    else:
        lunch.update_transaction(
            transaction_id,
            TransactionUpdateObject(category_id=category_id),
        )
    logger.info(f"Changed category for tx {transaction_id} to {category_id}")

    updated_transaction = lunch.get_transaction(transaction_id)
    await send_transaction_message(
        context, updated_transaction, chat_id, query.message.message_id
    )
    await query.answer()


async def handle_btn_dump_plaid_details(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Sends a new message with the plaid metadata of the transaction."""
    query = update.callback_query
    transaction_id = int(query.data.split("_")[1])

    chat_id = query.message.chat.id
    lunch = get_lunch_client_for_chat_id(chat_id)

    transaction = lunch.get_transaction(transaction_id)
    plaid_metadata = transaction.plaid_metadata
    plaid_details = "*Plaid Metadata*\n\n"
    plaid_details += f"*Transaction ID:* {transaction_id}\n"
    for key, value in plaid_metadata.items():
        if value is not None:
            plaid_details += f"*{key}:* `{value}`\n"

    await query.answer()
    await send_plaid_details(query, context, chat_id, transaction_id, plaid_details)


async def handle_btn_mark_tx_as_reviewed(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Updates the transaction status to reviewed."""
    query = update.callback_query
    chat_id = query.message.chat.id
    lunch = get_lunch_client_for_chat_id(chat_id)
    transaction_id = int(query.data.split("_")[1])
    try:
        lunch.update_transaction(
            transaction_id, TransactionUpdateObject(status="cleared")
        )

        # update message to show the right buttons
        updated_tx = lunch.get_transaction(transaction_id)
        msg_id = get_db().get_message_id_associated_with(transaction_id, chat_id)
        await send_transaction_message(
            context, transaction=updated_tx, chat_id=chat_id, message_id=msg_id
        )

        get_db().mark_as_reviewed(query.message.message_id, chat_id)
        await query.answer()
    except Exception as e:
        await query.answer(
            text=f"Error marking transaction as reviewed: {str(e)}", show_alert=True
        )


async def handle_btn_mark_tx_as_unreviewed(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Updates the transaction status to unreviewed."""
    query = update.callback_query
    chat_id = query.message.chat.id
    lunch = get_lunch_client_for_chat_id(chat_id)
    transaction_id = int(query.data.split("_")[1])
    try:
        logger.info(f"Marking transaction {transaction_id} as unreviewed")
        lunch.update_transaction(
            transaction_id, TransactionUpdateObject(status="uncleared")
        )

        # update message to show the right buttons
        updated_tx = lunch.get_transaction(transaction_id)
        msg_id = get_db().get_message_id_associated_with(transaction_id, chat_id)
        await send_transaction_message(
            context, transaction=updated_tx, chat_id=chat_id, message_id=msg_id
        )

        get_db().mark_as_unreviewed(query.message.message_id, chat_id)
        await query.answer()
    except Exception as e:
        await query.answer(
            text=f"Error marking transaction as reviewed: {str(e)}", show_alert=True
        )


async def handle_set_tx_notes_or_tags(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Updates the transaction notes."""
    handled = await handle_generic_message(update, context)
    if handled:
        return

    replying_to_msg_id = update.message.reply_to_message.message_id
    tx_id = get_db().get_tx_associated_with(replying_to_msg_id, update.message.chat_id)

    if tx_id is None:
        logger.error("No transaction ID found in bot data", exc_info=True)
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text=dedent(
                """
                Could not find the transaction associated with the message.
                This is a bug if you have not wiped the db.
                """
            ),
        )
        return

    msg_text = update.message.text
    message_are_tags = True
    for word in msg_text.split(" "):
        if not word.startswith("#"):
            message_are_tags = False
            break

    lunch = get_lunch_client_for_chat_id(update.message.chat_id)
    if message_are_tags:
        tags_without_hashtag = [
            tag[1:] for tag in msg_text.split(" ") if tag.startswith("#")
        ]
        logger.info(f"Setting tags to transaction ({tx_id}): {tags_without_hashtag}")
        lunch.update_transaction(
            tx_id, TransactionUpdateObject(tags=tags_without_hashtag)
        )
    else:
        notes = msg_text
        if len(notes) > 350:
            notes = notes[:350]
        logger.info(f"Setting notes to transaction ({tx_id}): {notes}")
        lunch.update_transaction(tx_id, TransactionUpdateObject(notes=notes))

    # update the transaction message to show the new notes
    updated_tx = lunch.get_transaction(tx_id)
    await send_transaction_message(
        context,
        transaction=updated_tx,
        chat_id=update.message.chat_id,
        message_id=replying_to_msg_id,
    )
    await context.bot.set_message_reaction(
        chat_id=update.message.chat_id,
        message_id=update.message.message_id,
        reaction=ReactionEmoji.WRITING_HAND,
    )


async def handle_btn_autocategorize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tx_id = int(query.data.split("_")[1])

    chat_id = query.message.chat.id
    response = auto_categorize(tx_id, chat_id)
    await update.callback_query.answer(
        text=response,
        show_alert=True,
    )

    # update the transaction message to show the new notes
    lunch = get_lunch_client_for_chat_id(chat_id)
    updated_tx = lunch.get_transaction(tx_id)
    await send_transaction_message(
        context,
        transaction=updated_tx,
        chat_id=chat_id,
        message_id=update.callback_query.message.message_id,
    )


async def poll_transactions_on_schedule(context: ContextTypes.DEFAULT_TYPE):
    """
    Gets called every minute to poll transactions for all registered chats.
    However, each chat can have its own polling settings, so we use this
    function to check the settings for each chat and decide whether to poll.
    """
    chat_ids = get_db().get_all_registered_chats()
    if len(chat_ids) is None:
        logger.info("No chats registered yet")

    for chat_id in chat_ids:
        settings = get_db().get_current_settings(chat_id)
        if not settings:
            logger.error(f"No settings found for chat {chat_id}!")
            continue

        # this is the last time we polled, saved as a string using:
        # datetime.now().isoformat()
        last_poll_at = settings.last_poll_at
        should_poll = False
        if last_poll_at is None:
            logger.info(f"First poll for chat {chat_id}")
            last_poll_at = datetime.now() - timedelta(days=1)
            should_poll = True
        else:
            poll_interval_seconds = settings.poll_interval_secs
            next_poll_at = last_poll_at + timedelta(seconds=poll_interval_seconds)
            should_poll = datetime.now() >= next_poll_at

        if should_poll:
            if settings.poll_pending:
                await check_pending_transactions_and_telegram_them(
                    context, chat_id=chat_id
                )
            else:
                await check_posted_transactions_and_telegram_them(
                    context, chat_id=chat_id
                )
            get_db().update_last_poll_at(chat_id, datetime.now().isoformat())


async def handle_expand_tx_options(update: Update, _: ContextTypes.DEFAULT_TYPE):
    transaction_id = int(update.callback_query.data.split("_")[1])
    await update.callback_query.answer()
    await update.callback_query.edit_message_reply_markup(
        reply_markup=get_tx_buttons(transaction_id, collapsed=False)
    )


async def handle_rename_payee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    transaction_id = int(update.callback_query.data.split("_")[1])
    await update.callback_query.answer()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please enter the new payee name:",
        reply_to_message_id=update.callback_query.message.message_id,
        reply_markup=ForceReply(),
    )
    set_expectation(
        update.effective_chat.id,
        {
            "expectation": RENAME_PAYEE,
            "msg_id": str(update.callback_query.message.message_id),
            "transaction_id": str(transaction_id),
        },
    )


async def handle_edit_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    transaction_id = int(update.callback_query.data.split("_")[1])
    await update.callback_query.answer()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=dedent(
            """
            Please enter notes for this transaction.\n\n
            *Hint:* _you can also reply to the transaction message to edit its notes._"""
        ),
        reply_to_message_id=update.callback_query.message.message_id,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ForceReply(),
    )
    set_expectation(
        update.effective_chat.id,
        {
            "expectation": EDIT_NOTES,
            "msg_id": str(update.callback_query.message.message_id),
            "transaction_id": str(transaction_id),
        },
    )


async def handle_set_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    transaction_id = int(update.callback_query.data.split("_")[1])
    await update.callback_query.answer()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=dedent(
            """
            Please enter the tags for this transaction\n\n
            💡 *Hint:* _you can also reply to the transaction message to edit its tags
            if the message contains only tags like this: #tag1 #tag2 #etc_
            """
        ),
        reply_to_message_id=update.callback_query.message.message_id,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ForceReply(),
    )
    set_expectation(
        update.effective_chat.id,
        {
            "expectation": SET_TAGS,
            "msg_id": str(update.callback_query.message.message_id),
            "transaction_id": str(transaction_id),
        },
    )
