import logging

from telegram.ext import ContextTypes

from deepinfra import auto_categorize
from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from tx_messaging import send_transaction_message

logger = logging.getLogger("categorization")


async def ai_categorize_transaction(
    tx_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE
):
    response = auto_categorize(tx_id, chat_id)
    logger.info(f"AI-categorization response: {response}")

    # update the transaction message to show the new categories
    lunch = get_lunch_client_for_chat_id(chat_id)
    updated_tx = lunch.get_transaction(tx_id)
    msg_id = get_db().get_message_id_associated_with(tx_id, chat_id)
    await send_transaction_message(
        context,
        transaction=updated_tx,
        chat_id=chat_id,
        message_id=msg_id,
    )
