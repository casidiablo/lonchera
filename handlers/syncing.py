import logging
from datetime import timedelta

from telegram.ext import ContextTypes

from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from telegram_extensions import Update
from tx_messaging import send_transaction_message

logger = logging.getLogger("messaging")


async def handle_resync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /resync command."""
    if not update.message or not update.message.text or not update.effective_chat:
        return

    parts = update.message.text.split(" ")
    last_n_days = 15  # default to last 15 days
    if len(parts) > 1:
        last_n_days = int(parts[1])

    chat_id = update.chat_id
    lunch = get_lunch_client_for_chat_id(chat_id)
    chat_txs = get_db().get_all_tx_by_chat_id(chat_id)

    # get the created_at bounds (i.e. the earliest and latest tx)
    earliest_tx_date = min(chat_txs, key=lambda tx: tx.created_at).created_at.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    earliest_tx_date = earliest_tx_date - timedelta(days=5)
    latest_tx_date = max(chat_txs, key=lambda tx: tx.created_at).created_at.replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    if last_n_days:
        earliest_tx_date = latest_tx_date - timedelta(days=last_n_days)

    # get the txs within the bounds
    logger.info(f"Pulling transactions from lunch for range {earliest_tx_date} - {latest_tx_date}")
    lunch_txs = lunch.get_transactions(start_date=earliest_tx_date, end_date=latest_tx_date)

    # make a lookup map for the txs from lunch
    lunch_txs_map = {tx.id: tx for tx in lunch_txs}

    # now we use the information in this the tx from lunch to update the tx in the db
    # and if we miss any, we will query them individually later on
    if last_n_days:
        chat_txs = [tx for tx in chat_txs if tx.created_at >= earliest_tx_date]

    errors = 0
    missing = 0
    for tx in chat_txs:
        if tx.tx_id in lunch_txs_map:
            lunch_tx = lunch_txs_map[tx.tx_id]
            # for each transaction we must find the message that holds its information
            # and update it to reflect the new information, if any
            try:
                await send_transaction_message(context, lunch_tx, chat_id, tx.message_id)

                # update the tx in the db
                if lunch_tx.status == "cleared":
                    get_db().mark_as_reviewed(tx.message_id, chat_id)
                else:
                    get_db().mark_as_unreviewed(tx.message_id, chat_id)
            except Exception:
                logger.exception(f"Error sending transaction message for tx_id {tx.tx_id}")
                errors += 1
        else:
            try:
                lunch_tx = lunch.get_transaction(tx.tx_id)
                await send_transaction_message(context, lunch_tx, chat_id, tx.message_id)
            except Exception:
                logger.exception(f"Error fetching transaction {tx.tx_id}")
                missing += 1

    logger.info(f"Resynced {len(chat_txs) - errors - missing} transactions, {errors} errors, {missing} missing")
    # send a message showing the results
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Resynced {len(chat_txs) - errors - missing} transactions, {errors} errors, {missing} missing",
    )
