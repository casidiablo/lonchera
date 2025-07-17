import logging
import os
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field, SecretStr
from telegram import Update
from telegram.constants import ParseMode, ReactionEmoji
from telegram.ext import ContextTypes

from handlers.aitools.tools import (
    add_manual_transaction,
    calculate,
    get_account_balances,
    get_categories,
    get_manual_asset_accounts,
    get_my_lunch_money_user_info,
    parse_date_reference,
    get_crypto_accounts,
)
from lunch import get_lunch_client_for_chat_id
from persistence import get_db
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


def create_lunch_money_agent(chat_id: int):
    """Create and return a Lunch Money agent with the configured model and tools."""
    use_openai = os.environ.get("USE_OPEN_AI", "false").lower() == "true"
    # For now only use OpenAI for chat_id 378659027 since it's in beta
    if use_openai and chat_id == 378659027:
        chat_model = ChatOpenAI(
            model="gpt-4.1-nano", api_key=SecretStr(os.environ.get("OPENAI_API_KEY", "")), temperature=0
        )
    else:
        chat_model = ChatOpenAI(
            model="meta-llama/Llama-4-Scout-17B-16E-Instruct",
            base_url="https://api.deepinfra.com/v1/openai",
            api_key=SecretStr(os.environ["DEEPINFRA_API_KEY"]),
            temperature=0,
        )

    # Create a React agent with our model and tools
    agent = create_react_agent(
        model=chat_model,
        tools=[
            get_my_lunch_money_user_info,
            get_account_balances,
            get_manual_asset_accounts,
            get_categories,
            add_manual_transaction,
            parse_date_reference,
            get_crypto_accounts,
            calculate,
        ],
        response_format=LunchMoneyAgentResponse,
    )

    return agent


def get_agent_response(user_prompt: str, chat_id: int, verbose: bool = True) -> LunchMoneyAgentResponse:
    """
    Get response from the Lunch Money agent for a given user prompt.

    Args:
        user_prompt (str): The user's question or prompt
        chat_id (int): The chat ID for accessing Lunch Money data
        verbose (bool): Whether to print iteration details and message outputs

    Returns:
        str: The final response from the agent
    """
    logger.info("Creating Lunch Money agent for chat_id: %s (verbose? %s)", chat_id, verbose)
    agent = create_lunch_money_agent(chat_id)

    if verbose:
        logger.info("User message: %s", user_prompt)

    config: RunnableConfig = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 30}

    system_message = SystemMessage(
        content=f"""
        You are a helpful assistant that can provide Lunch Money information and help users manage their finances.

        User input can be in any language. However, when things like category names are in
        a different language than the user message is in, make sure to include the actual
        category name in the original language in parenthesis.

        When user asks for balances, remember to include the currency when possible.
        If the user asks for the balance of an account and it could not be found with
        `get_account_balances`, try to find it in the manually-managed accounts calling `get_manual_asset_accounts`

        Note that when user asks for how much money they have in cash, you must bias
        towards using `get_manual_asset_accounts`.

        When using tools that require a chat_id, always use this chat_id: {chat_id}

        When user tells you they spent money using a specific account, assume they want you to create
        a manual transaction for that account. Try to infer as much as possible from the user's input.

        For manual transactions:
        - Only manually-managed accounts support manual transactions
        - Use get_manual_asset_accounts to see which accounts are available
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
        """
    )
    initial_message = HumanMessage(content=user_prompt)
    initial_state = {"messages": [system_message, initial_message]}

    response = agent.invoke(initial_state, config)
    return response["structured_response"]


async def handle_generic_message_with_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle generic messages using the AI agent."""
    message = update.message
    if message is None or update.message is None or update.message.text is None or update.effective_chat is None:
        logger.error("Failed to process update object. It had no message")
        return
    try:
        user_message = update.message.text
        chat_id = update.effective_chat.id

        logger.info("Processing AI message for chat_id %s: %s", chat_id, user_message)

        # React to the audio message to indicate processing
        await context.bot.set_message_reaction(
            chat_id=chat_id, message_id=message.message_id, reaction=ReactionEmoji.HIGH_VOLTAGE_SIGN
        )

        # Get the AI response
        response = get_agent_response(user_message, chat_id, verbose=True)
        await handle_ai_response(update, context, response)

    except Exception as e:
        logger.error(f"Error in handle_generic_message_with_ai: {e}")
        await message.reply_text("Sorry, I encountered an error processing your request. Please try again.")


async def handle_ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE, response: LunchMoneyAgentResponse):
    message = update.message
    if message is None or update.effective_chat is None:
        # should never happen
        logger.error("handle_ai_response called with None message or chat")
        return
    try:
        await message.reply_text(
            text=response.message, parse_mode=ParseMode.MARKDOWN, reply_to_message_id=message.message_id
        )
    except Exception as se:
        if "Can't parse entities" in str(se):
            # try to send without markdown
            await message.reply_text(text=response.message, reply_to_message_id=message.message_id)
        else:
            raise se

    if response.transactions_created_ids:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        for tx_id in response.transactions_created_ids:
            tx = lunch_client.get_transaction(tx_id)
            msg_id = await send_transaction_message(
                context, transaction=tx, chat_id=chat_id, reply_to_message_id=message.message_id
            )
            get_db().mark_as_sent(
                tx.id,
                update.effective_chat.id,
                msg_id,
                tx.recurring_type,
                reviewed=True,
                plaid_id=None,  # this is a manual transaction
            )


# this allows testing the agent outside of the bot
if __name__ == "__main__":
    user_message = "I just spent 1000 COP in efectivo"
    chat_id = 420420420  # debug chat id
    result = get_agent_response(user_message, chat_id)
    logger.info("Final result: %s", result)
