import logging
import os
import time

from telegram.constants import ParseMode, ReactionEmoji
from telegram.ext import ContextTypes

from handlers.lunch_money_agent_core import AgentConfig, LunchMoneyAgentResponse, execute_agent
from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from telegram_extensions import Update
from tx_messaging import send_transaction_message
from utils import Keyboard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_agent_response(
    user_prompt: str,
    chat_id: int,
    tx_id: int | None = None,
    telegram_message_id: int | None = None,
    verbose: bool = True,
) -> LunchMoneyAgentResponse:
    """
    Get response from the Lunch Money agent for a given user prompt.

    Args:
        user_prompt (str): The user's question or prompt
        chat_id (int): The chat ID for accessing Lunch Money data
        tx_id (int | None): Optional transaction ID for context
        telegram_message_id (int | None): Optional Telegram message ID
        verbose (bool): Whether to print iteration details and message outputs

    Returns:
        LunchMoneyAgentResponse: The structured response from the agent
    """
    start_time = time.time()
    get_db().inc_metric("ai_agent_requests")

    logger.info("Creating Lunch Money agent for chat_id: %s (verbose? %s)", chat_id, verbose)

    # Track prompt characteristics
    get_db().inc_metric("ai_agent_prompt_chars", len(user_prompt))
    if tx_id:
        get_db().inc_metric("ai_agent_requests_with_tx_context")

    # Fetch user settings from database
    settings = get_db().get_current_settings(chat_id)
    user_language = settings.ai_response_language if settings else "English"
    user_timezone = settings.timezone if settings else "UTC"
    model_name = settings.ai_model if settings else None

    # Determine if user is admin
    admin_user_id = os.environ.get("ADMIN_USER_ID")
    is_admin = admin_user_id is not None and str(chat_id) == admin_user_id

    # Create AgentConfig with fetched settings
    config = AgentConfig(
        chat_id=chat_id, language=user_language, timezone=user_timezone, model_name=model_name, is_admin=is_admin
    )

    try:
        # Call execute_agent from core module
        structured_response = execute_agent(
            user_prompt=user_prompt, config=config, tx_id=tx_id, telegram_message_id=telegram_message_id
        )

        # Track successful responses and their characteristics
        processing_time = time.time() - start_time
        get_db().inc_metric("ai_agent_requests_successful")
        get_db().inc_metric("ai_agent_processing_time_seconds", processing_time)
        get_db().inc_metric("ai_agent_response_chars", len(structured_response.message))

        # Track response status
        get_db().inc_metric(f"ai_agent_response_status_{structured_response.status}")

        # Track specific actions taken
        if structured_response.transactions_created_ids:
            get_db().inc_metric("ai_agent_transactions_created", len(structured_response.transactions_created_ids))

        if structured_response.transaction_updated_ids:
            get_db().inc_metric("ai_agent_transactions_updated", len(structured_response.transaction_updated_ids))

        # Track language preference usage
        if settings and settings.ai_response_language:
            get_db().inc_metric(f"ai_agent_language_{settings.ai_response_language.lower()}")

        return structured_response

    except Exception as e:
        processing_time = time.time() - start_time
        get_db().inc_metric("ai_agent_requests_failed")
        get_db().inc_metric("ai_agent_processing_time_seconds", processing_time)
        logger.exception("Error in agent processing: %s", e)
        # Return a default LunchMoneyAgentResponse on error for type compliance
        return LunchMoneyAgentResponse(
            message=f"Agent failed to process request: {e}",
            status="error",
            transactions_created_ids=[],
            transaction_updated_ids={},
        )


async def handle_generic_message_with_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle generic messages using the AI agent."""
    message = update.message
    if message is None or update.message is None or update.message.text is None:
        logger.error("Failed to process update object. It had no message", exc_info=True)
        return
    try:
        user_message = update.message.text
        chat_id = update.chat_id

        # Track text message processing
        get_db().inc_metric("ai_agent_text_messages")

        # try to see if the message is a reply to a transaction message
        tx_id = None
        replying_to_msg_id = None
        if update.message.reply_to_message:
            replying_to_msg_id = update.message.reply_to_message.message_id
            tx_id = get_db().get_tx_associated_with(replying_to_msg_id, update.chat_id)

        logger.info("Processing AI message for chat_id %s: %s (tx id: %s)", chat_id, user_message, tx_id)

        # React to the audio message to indicate processing
        await context.bot.set_message_reaction(
            chat_id=chat_id, message_id=message.message_id, reaction=ReactionEmoji.HIGH_VOLTAGE_SIGN
        )

        # Get the AI response
        response = get_agent_response(user_message, chat_id, tx_id, replying_to_msg_id, verbose=True)
        await handle_ai_response(update, context, response)

        get_db().inc_metric("ai_agent_text_messages_successful")

    except Exception as e:
        get_db().inc_metric("ai_agent_text_messages_failed")
        logger.error(f"Error in handle_generic_message_with_ai: {e}", exc_info=True)
        await message.reply_text("Sorry, I encountered an error processing your request. Please try again.")


async def handle_ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE, response: LunchMoneyAgentResponse):
    message = update.message
    if message is None:
        # should never happen
        logger.error("handle_ai_response called with None message", exc_info=True)
        return

    logger.info(f"Handling message from AI: {response}")

    chat_id = update.chat_id
    get_db().inc_metric("ai_agent_responses_sent")

    ai_message = response.message

    try:
        await message.reply_text(
            text=ai_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_to_message_id=message.message_id,
            reply_markup=Keyboard.build_from(("Done", "cancel")),
        )
        get_db().inc_metric("ai_agent_responses_sent_markdown")
    except Exception as se:
        if "Can't parse entities" in str(se):
            # try to send without markdown
            await message.reply_text(
                text=ai_message,
                reply_to_message_id=message.message_id,
                reply_markup=Keyboard.build_from(("Done", "cancel")),
            )
            get_db().inc_metric("ai_agent_responses_sent_plaintext")
        else:
            raise

    if response.transactions_created_ids:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        for tx_id in response.transactions_created_ids:
            tx = lunch_client.get_transaction(tx_id)
            msg_id = await send_transaction_message(
                context, transaction=tx, chat_id=chat_id, reply_to_message_id=message.message_id
            )
            get_db().mark_as_sent(
                tx.id,
                update.chat_id,
                msg_id,
                tx.recurring_type,
                reviewed=True,
                plaid_id=None,  # this is a manual transaction
            )

    if response.transaction_updated_ids:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        for tx_id, telegram_message_id in response.transaction_updated_ids.items():
            if telegram_message_id is None:
                continue
            # update the transaction message to show its new content
            updated_tx = lunch_client.get_transaction(tx_id)
            await send_transaction_message(
                context, transaction=updated_tx, chat_id=chat_id, message_id=telegram_message_id
            )
