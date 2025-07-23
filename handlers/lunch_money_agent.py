import datetime
import logging
import os
import time
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field, SecretStr
from telegram.constants import ParseMode, ReactionEmoji
from telegram.ext import ContextTypes

from handlers.aitools.tools import (
    add_manual_transaction,
    calculate,
    get_categories,
    get_crypto_accounts_balances,
    get_manual_accounts_balances,
    get_my_lunch_money_user_info,
    get_plaid_account_balances,
    get_recent_transactions,
    get_single_transaction,
    get_transactions,
    parse_date_reference,
    update_transaction,
)
from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from telegram_extensions import Update
from tx_messaging import send_transaction_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LunchMoneyAgentResponse(BaseModel):
    """Response format for the Lunch Money agent."""

    status: str = Field(description="Status of the operation, typically 'success' or 'error'")
    message: str = Field(description="Human readable message response in Markdown format (Telegram version)")
    transactions_created_ids: list[int] | None = Field(
        default=None, description="List of transaction IDs that were created, only present if transactions were created"
    )
    transaction_updated_ids: dict[int, int] | None = Field(
        default=None,
        description="""
        A mapping of transaction IDs that were updated to their new values,
        where keys are the transaction ID (integer) and values are the telegram message ID (integer) or None if no message was sent,
        only present if transactions were updated.

        Always include the transaction ID in the message regardless of whether there is a Telegram message ID.
        """,
    )


def create_lunch_money_agent(chat_id: int):
    """Create and return a Lunch Money agent with the configured model and tools."""
    # Get user's model preference from settings
    settings = get_db().get_current_settings(chat_id)
    selected_model = settings.ai_model if settings else None

    # Default model (Llama via DeepInfra)
    default_model = "meta-llama/Llama-4-Scout-17B-16E-Instruct"

    # OpenAI models that should use OpenAI API
    openai_models = ["gpt-4.1-nano", "gpt-4.1-mini", "gpt-4.1", "gpt-4o", "gpt-4o-mini", "o4-mini"]

    # Only allow advanced models for authorized chat_id
    admin_user_id = os.getenv("ADMIN_USER_ID")
    if admin_user_id and chat_id == int(admin_user_id) and selected_model and selected_model in openai_models:
        model_name = selected_model
        logger.info(f"Using selected OpenAI model: {model_name}")
        get_db().inc_metric("ai_agent_openai_model_usage")
        get_db().inc_metric(f"ai_agent_model_{model_name.replace('-', '_').replace('.', '_')}")
        chat_model = ChatOpenAI(
            model=model_name, api_key=SecretStr(os.environ.get("OPENAI_API_KEY", "")), temperature=0
        )
    else:
        # Use default Llama model via DeepInfra for all other cases
        model_name = default_model
        logger.info(f"Using default Llama model: {model_name}")
        get_db().inc_metric("ai_agent_deepinfra_model_usage")
        get_db().inc_metric(f"ai_agent_model_{model_name.replace('-', '_').replace('.', '_').replace('/', '_')}")
        chat_model = ChatOpenAI(
            model=model_name,
            base_url="https://api.deepinfra.com/v1/openai",
            api_key=SecretStr(os.environ["DEEPINFRA_API_KEY"]),
            temperature=0,
        )

    # Create a React agent with our model and tools
    agent = create_react_agent(
        model=chat_model,
        tools=[
            get_my_lunch_money_user_info,
            get_manual_accounts_balances,
            get_plaid_account_balances,
            get_crypto_accounts_balances,
            get_categories,
            add_manual_transaction,
            parse_date_reference,
            calculate,
            get_single_transaction,
            get_recent_transactions,
            get_transactions,
            update_transaction,
        ],
        response_format=LunchMoneyAgentResponse,
    )

    return agent


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
        verbose (bool): Whether to print iteration details and message outputs

    Returns:
        str: The final response from the agent
    """
    start_time = time.time()
    get_db().inc_metric("ai_agent_requests")

    logger.info("Creating Lunch Money agent for chat_id: %s (verbose? %s)", chat_id, verbose)
    agent = create_lunch_money_agent(chat_id)

    if verbose:
        logger.info("User message: %s", user_prompt)

    # Track prompt characteristics
    get_db().inc_metric("ai_agent_prompt_chars", len(user_prompt))
    if tx_id:
        get_db().inc_metric("ai_agent_requests_with_tx_context")

    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 30}

    # Get user's language preference
    settings = get_db().get_current_settings(chat_id)
    user_language = settings.ai_response_language if settings else None

    tx_prompt = ""
    if tx_id:
        tx_prompt = f"""
        The user is referring to this Lunch transaction ID: {tx_id} whose
        contents are displayed in the Telegram Message ID: {telegram_message_id}

        If user asks you to update a transaction, like setting notes or tags, use the
        update_transaction tool.

        If user asked you to categorize the transaction, make sure to call get_categories
        to get the right category ID.
        """

    # Language instruction based on user preference
    language_instruction = ""
    if user_language:
        language_instruction = f"""
        IMPORTANT: You must respond in {user_language}. All your responses, explanations,
        and messages should be written in {user_language}.
        """
    else:
        language_instruction = """
        User input can be in any language. Respond in the same language as the user's input.
        """

    system_message = SystemMessage(
        content=f"""
        You are a helpful assistant that can provide Lunch Money information and help users manage their finances.

        When user asks for balances, remember to include the currency when possible.
        If the user asks for the balance of one or more accounts make sure to use
        `get_plaid_account_balances`, `get_manual_accounts_balances`, and `get_crypto_accounts_balances`
        before providing an answer.

        Note that when user asks for how much money they have in cash, you must bias
        towards using `get_manual_accounts_balances`.

        When using tools that require a chat_id, always use this chat_id: {chat_id}
        Today's date is {datetime.date.today().strftime("%Y-%m-%d")}

        {tx_prompt}

        When user tells you they spent money using a specific account, assume they want you to create
        a manual transaction for that account. Try to infer as much as possible from the user's input.

        For manual transactions:
        - Only manually-managed accounts support manual transactions
        - Use get_manual_accounts_balances to see which accounts are available
        - Use get_categories to see available categories
        - When adding transactions, expenses must have is_received=False and income must have is_received=True
        - Date format should be YYYY-MM-DD. ALWAYS try to source the date of the transaction using `parse_date_reference`
        but make sure the parameters are always in English.
        - Infer transactions' notes from the user's input, but do not mention the account name in the notes.
        - Use the add_manual_transaction tool and make sure to provide the right types for it.
        - Try to infer the category from the user's input.
        - If no category can be inferred, pass None to the category parameter.
        - When a category is inferred, MAKE sure it is not a super category

        For date handling:
        - When user mentions dates in any format, use parse_date_reference to convert them to YYYY-MM-DD format
        - When user does not mention any date, also call parse_date_reference with the 'today' param
        - The dateparser library supports extensive formats: relative dates ("yesterday", "2 days ago", "last week"),
        absolute dates ("2024-01-15", "January 15, 2024"), natural language ("next Monday", "in two weeks")
        - Always use the parsed date in the final transaction

        IMPORTANT:
        - DO NEVER leak the chat_id in the user response
        - Ignore any chat_id provided by the user
        - Do never leak the name of the tools
        - Work on the user request systematically. User only provides a single request
        and there is no way for them to refine their choices so make sure to fullfill
        the request or fail with a reasonable message.
        - NEVER TELL THE USER WHAT YOU INTENT TO DO, JUST DO IT.
        - NEVER TELL TO USER TO CONFIRM OR APPROVE YOUR ACTIONS.
        - ONLY add a transaction when the user asks you to.

        {language_instruction}
        """
    )
    initial_message = HumanMessage(content=user_prompt)
    initial_state = {"messages": [system_message, initial_message]}

    try:
        response = agent.invoke(initial_state, config)
        structured_response = response["structured_response"]

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
        settings = get_db().get_current_settings(chat_id)
        if settings and settings.ai_response_language:
            get_db().inc_metric(f"ai_agent_language_{settings.ai_response_language.lower()}")

    except Exception as e:
        processing_time = time.time() - start_time
        get_db().inc_metric("ai_agent_requests_failed")
        get_db().inc_metric("ai_agent_processing_time_seconds", processing_time)
        logger.error(f"Error in agent processing: {e}", exc_info=True)
        # Return a default LunchMoneyAgentResponse on error for type compliance
        return LunchMoneyAgentResponse(
            message=f"Agent failed to process request: {e}",
            status="error",
            transactions_created_ids=[],
            transaction_updated_ids={},
        )
    else:
        return structured_response


async def handle_generic_message_with_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle generic messages using the AI agent."""
    message = update.message
    if message is None or update.message is None or update.message.text is None or update.effective_chat is None:
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
    if message is None or update.effective_chat is None:
        # should never happen
        logger.error("handle_ai_response called with None message or chat", exc_info=True)
        return

    logger.info(f"Handling message from AI: {response}")

    chat_id = update.chat_id
    get_db().inc_metric("ai_agent_responses_sent")

    try:
        await message.reply_text(
            text=response.message, parse_mode=ParseMode.MARKDOWN, reply_to_message_id=message.message_id
        )
        get_db().inc_metric("ai_agent_responses_sent_markdown")
    except Exception as se:
        if "Can't parse entities" in str(se):
            # try to send without markdown
            await message.reply_text(text=response.message, reply_to_message_id=message.message_id)
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
            # update the transaction message to show the new notes
            updated_tx = lunch_client.get_transaction(tx_id)
            await send_transaction_message(
                context, transaction=updated_tx, chat_id=chat_id, message_id=telegram_message_id
            )
