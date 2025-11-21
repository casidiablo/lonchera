import logging
from textwrap import dedent

from lunchable import TransactionUpdateObject
from telegram.ext import ContextTypes

from handlers.ai_agent import get_agent_response
from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from tx_messaging import send_transaction_message

logger = logging.getLogger("categorization")


def categorize_transaction_with_agent(tx_id: int, chat_id: int) -> str:
    """
    Categorize a transaction using the DSPy agent.

    Metrics tracked by this function (via get_agent_response):
    - ai_agent_requests: Total categorization requests
    - ai_agent_prompt_chars: Prompt length
    - ai_agent_response_chars: Response length
    - ai_agent_transactions_updated: Successful categorizations
    - ai_agent_response_status_success/error: Outcome tracking

    Args:
        tx_id: Transaction ID to categorize
        chat_id: Chat ID for accessing Lunch Money data

    Returns:
        str: Human-readable result message
    """
    logger.info("Starting agent-based categorization for tx_id=%s, chat_id=%s", tx_id, chat_id)

    try:
        # Fetch the transaction
        lunch = get_lunch_client_for_chat_id(chat_id)
        transaction = lunch.get_transaction(tx_id)
        logger.info("Fetched transaction: payee=%s, amount=%s", transaction.payee, transaction.amount)

        # Build a focused categorization prompt
        prompt = dedent(
            """
            Categorize this transaction. Analyze the transaction details and determine the most appropriate category.

            Important rules:
            1. Only suggest leaf categories (subcategories), never parent categories
            2. For Amazon transactions: Only use the Amazon category if the notes don't indicate a more specific category
            3. Consider the payee, amount, currency, plaid metadata, and notes when making your decision
            4. After determining the category, update the transaction using the update_transaction tool

            Please:
            1. First, get the transaction details using get_single_transaction
            2. Then, get available categories using get_categories
            3. Analyze the transaction and choose the best matching category
            4. Update the transaction with the chosen category using update_transaction

            Respond with a brief message indicating which category was applied.
            """
        ).strip()

        logger.info("Calling agent with categorization prompt")

        # Get the telegram message ID if available for context
        telegram_message_id = get_db().get_message_id_associated_with(tx_id, chat_id)

        # Call the agent
        response = get_agent_response(
            user_prompt=prompt, chat_id=chat_id, tx_id=tx_id, telegram_message_id=telegram_message_id, verbose=False
        )

        logger.info("Agent response status: %s", response.status)

        # Check if the agent successfully updated the transaction
        if response.status == "success" and tx_id in response.transaction_updated_ids:
            # Fetch the updated transaction to verify the category was applied
            updated_tx = lunch.get_transaction(tx_id)
            logger.info("Transaction updated successfully. New category: %s", updated_tx.category_name)

            # Check if we need to mark as reviewed
            settings = get_db().get_current_settings(chat_id)
            if settings and settings.mark_reviewed_after_categorized and updated_tx.status != "cleared":
                logger.info("Marking transaction as reviewed per user settings")
                lunch.update_transaction(tx_id, TransactionUpdateObject(status="cleared"))  # type: ignore
                return f"Transaction categorized as {updated_tx.category_name} and marked as reviewed"

            return f"Transaction categorized as {updated_tx.category_name}"

        elif response.status == "error":
            logger.error("Agent returned error status: %s", response.message)
            return "AI failed to categorize the transaction. Please try again or categorize manually."

        else:
            # Agent responded but didn't update the transaction
            logger.warning("Agent completed but transaction was not updated")
            return "AI could not determine an appropriate category. Please categorize manually."

    except Exception:
        logger.exception("Error during agent-based categorization for tx_id=%s", tx_id)
        return "AI categorization failed due to an error. Please try again or categorize manually."


async def ai_categorize_transaction(tx_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    response = categorize_transaction_with_agent(tx_id, chat_id)
    logger.info(f"AI-categorization response: {response}")

    # update the transaction message to show the new categories
    lunch = get_lunch_client_for_chat_id(chat_id)
    updated_tx = lunch.get_transaction(tx_id)
    msg_id = get_db().get_message_id_associated_with(tx_id, chat_id)
    await send_transaction_message(context, transaction=updated_tx, chat_id=chat_id, message_id=msg_id)
