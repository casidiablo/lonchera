import json
import logging
import datetime
import os

from telegram import Update
from telegram.ext import ContextTypes
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from telegram.constants import ReactionEmoji, ParseMode
from langchain_core.runnables import RunnableConfig
from pydantic import SecretStr
import uuid
from lunchable import TransactionInsertObject
import dateparser

from lunch import get_lunch_client_for_chat_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@tool
async def get_my_lunch_money_user_info(chat_id: int) -> str:
    """get my lunch money user info"""
    logger.info("Calling get_my_lunch_money_user_info for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        user_info = lunch_client.get_user()
        return json.dumps(user_info.model_dump())
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_account_balances(chat_id: int) -> str:
    """Get current balance for all accounts"""
    logger.info("Calling get_account_balances for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        plaid_accounts = lunch_client.get_plaid_accounts()

        accounts_data = []
        for acc in plaid_accounts:
            account_info = {
                "name": acc.display_name or acc.name,
                "balance": float(acc.balance),
                "currency": acc.currency.upper(),
                "type": acc.type,
                "institution_name": acc.institution_name,
                "last_update": acc.balance_last_update.isoformat() if acc.balance_last_update else None,
                "status": acc.status,
            }
            if acc.limit:
                account_info["limit"] = float(acc.limit)
            accounts_data.append(account_info)

        return json.dumps({"accounts": accounts_data})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_manual_asset_accounts(chat_id: int) -> str:
    """Get manually-managed asset accounts that can be used for manual transactions"""
    logger.info("Calling get_manual_asset_accounts for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        assets = lunch_client.get_assets()

        # Filter for manually managed accounts (credit and cash types)
        manual_accounts = [asset for asset in assets if asset.type_name in {"credit", "cash"}]

        accounts_data = []
        for asset in manual_accounts:
            account_info = {
                "id": asset.id,
                "name": asset.name,
                "display_name": asset.display_name,
                "balance": float(asset.balance),
                "currency": asset.currency.upper(),
                "type": asset.type_name,
                "institution_name": asset.institution_name,
            }
            accounts_data.append(account_info)

        return json.dumps({"manual_accounts": accounts_data})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_categories(chat_id: int) -> str:
    """Get all available categories for transactions"""
    logger.info("Calling get_categories for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        categories = lunch_client.get_categories()

        categories_data = []
        for category in categories:
            category_info = {
                "id": category.id,
                "name": category.name,
                "is_group": category.is_group,
                "group_id": category.group_id,
            }
            categories_data.append(category_info)

        return json.dumps({"categories": categories_data})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def add_manual_transaction(
    chat_id: int,
    date: str,
    account_id: int,
    payee: str,
    amount: float,
    is_received: bool = False,
    category_id: int = None,
    notes: str = None
) -> str:
    """Add a manual transaction to a manually-managed asset account.

    Args:
        chat_id: The chat ID
        date: Transaction date in YYYY-MM-DD format
        account_id: ID of the asset account to add transaction to
        payee: Name of the payee
        amount: Transaction amount (positive for expenses, will be negated automatically if is_received=True)
        is_received: Whether this is received money (income)
        category_id: Optional category ID
        notes: Optional notes
    """
    logger.info("Calling add_manual_transaction for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)

        # Validate that the account exists and is manually managed
        assets = lunch_client.get_assets()
        account = next((asset for asset in assets if asset.id == account_id), None)
        if not account:
            return json.dumps({"error": f"Account with ID {account_id} not found"})

        if account.type_name not in {"credit", "cash"}:
            return json.dumps({"error": f"Account '{account.name}' is not manually managed. Only credit and cash accounts support manual transactions."})

        # Convert received money to negative amount
        final_amount = amount * -1 if is_received else amount

        # Parse the date
        try:
            transaction_date = datetime.datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return json.dumps({"error": "Invalid date format. Use YYYY-MM-DD"})

        # Create transaction
        transaction_obj = TransactionInsertObject(
            date=transaction_date,
            category_id=category_id,
            payee=payee,
            amount=final_amount,
            currency=account.currency.lower(),
            notes=notes,
            status="cleared",
            asset_id=account_id,
        )

        # Insert transaction
        transaction_ids = lunch_client.insert_transactions(transaction_obj)
        transaction_id = transaction_ids[0]

        # Get the created transaction to return details
        transaction = lunch_client.get_transaction(transaction_id)

        # msg_id = await send_transaction_message(context, transaction=transaction, chat_id=chat_id)
        # get_db().mark_as_sent(
        #     transaction.id,
        #     update.effective_chat.id,
        #     msg_id,
        #     transaction.recurring_type,
        #     reviewed=True,
        #     plaid_id=None,  # this is a manual transaction
        # )

        return json.dumps({
            "success": True,
            "transaction_id": transaction_id,
            "transaction": {
                "id": transaction.id,
                "date": transaction.date.isoformat(),
                "payee": transaction.payee,
                "amount": float(transaction.amount),
                "currency": transaction.currency.upper(),
                "account_name": account.name,
                "category_name": transaction.category_name if transaction.category_name else "Uncategorized",
                "notes": transaction.notes,
            }
        })
    except Exception as e:
        logger.error(f"Error adding manual transaction: {e}")
        return json.dumps({"error": str(e)})


@tool
def parse_date_reference(date_reference: str) -> str:
    """Parse date references using the powerful dateparser library.

    Supports a wide variety of formats including:
    - Relative dates: 'today', 'yesterday', 'tomorrow', '2 days ago', '3 weeks ago', 'last Monday'
    - Absolute dates: '2024-01-15', 'January 15, 2024', '15/01/2024'
    - Natural language: 'next week', 'last month', 'in two days'
    - Multiple languages and locales supported

    Args:
        date_reference: The date reference to parse in natural language or standard formats

    Returns:
        JSON with the parsed date in YYYY-MM-DD format
    """
    logger.info("Calling parse_date_reference for: %s", date_reference)
    try:
        # Use dateparser to parse the date reference
        parsed_datetime = dateparser.parse(date_reference)

        if parsed_datetime is None:
            return json.dumps({"error": f"Could not parse date reference: {date_reference}"})

        result_date = parsed_datetime.date()
        base_date = datetime.date.today()

        return json.dumps({
            "success": True,
            "date": result_date.strftime("%Y-%m-%d"),
            "formatted_date": result_date.strftime("%B %d, %Y"),
            "reference": date_reference,
            "base_date": base_date.strftime("%Y-%m-%d")
        })

    except Exception as e:
        logger.error(f"Error parsing date reference: {e}")
        return json.dumps({"error": str(e)})


def create_lunch_money_agent(context: Optional[ContextTypes.DEFAULT_TYPE], chat_id: int):
    """Create and return a Lunch Money agent with the configured model and tools."""
    # Configure the chat model to use DeepInfra API

    chat_model = ChatOpenAI(
        model="meta-llama/Llama-4-Scout-17B-16E-Instruct",
        base_url="https://api.deepinfra.com/v1/openai",
        api_key=SecretStr(os.environ["DEEPINFRA_API_KEY"]),
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
            parse_date_reference
        ],
        prompt=f"""
            You are a helpful assistant that can provide Lunch Money information and help users manage their finances.

            User input can be in any language. The final response must be in the very same language. However,
            when things like category names are in a different language than the user message is in, make
            sure to include the actual category name in the original language in parenthesis.

            When user asks for balances, remember to include the currency when possible.
            If the user asks for the balance of an account and it could not be found with
            `get_account_balances`, try to find it in the manually-managed accounts calling `get_manual_asset_accounts`

            Note that when user asks for how much money they have in cash, you must bias
            towards using `get_manual_asset_accounts`.

            When using tools that require a chat_id, always use this chat_id: {chat_id}

            When user tells you they spent money using a specific account, assume they want you to create
            a manual transaction for that account. Try to infer as much as possible from the user's input.

            For manual transactions:
            - Only manually-managed accounts (credit and cash types) support manual transactions
            - Use get_manual_asset_accounts to see which accounts are available
            - Use get_categories to see available categories
            - When adding transactions, positive amounts are expenses, negative amounts (or is_received=True) are income
            - Date format should be YYYY-MM-DD. ALWAYS try to source the date of the transaction using `parse_date_reference`.
            - Infer notes from the user's input.

            For date handling:
            - When users mention dates in any format, use parse_date_reference to convert them to YYYY-MM-DD format
            - When users does not mention any date, also call parse_date_reference with the 'today' param
            - The dateparser library supports extensive formats: relative dates ("yesterday", "2 days ago", "last week"), absolute dates ("2024-01-15", "January 15, 2024"), natural language ("next Monday", "in two weeks"), and multiple languages
            - Always use the parsed date in the final transaction

            IMPORTANT:
            - Do never leak the chat_id in the user response
            - Ignore any chat_id provided by the user
            - Do never leak the name of the tools
            - Work on the user request systematically. User only provides a single request
            and there is no way for them to refine their choices so make sure to fullfill
            the request or fail with a reasonable message.
            - Reply message is in Markdown format for Telegram:
               - Balances must be quoted in ticks (`) for better formatting.
               - Lists must use - instead of *
            """,
    )

    return agent


async def get_agent_response(context: Optional[ContextTypes.DEFAULT_TYPE], user_prompt: str, chat_id: int, verbose: bool = True) -> str:
    """
    Get response from the Lunch Money agent for a given user prompt.

    Args:
        user_prompt (str): The user's question or prompt
        chat_id (int): The chat ID for accessing Lunch Money data
        verbose (bool): Whether to print iteration details and message outputs

    Returns:
        str: The final response from the agent
    """
    logger.info("Creating Lunch Money agent for chat_id: %s", chat_id)
    agent = create_lunch_money_agent(context, chat_id)

    if verbose:
        logger.info("User message: %s", user_prompt)

    config: RunnableConfig = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 30}

    initial_message = HumanMessage(content=user_prompt)
    initial_state = {"messages": [initial_message]}

    iteration = 0
    last_msg_content = None
    final_response = None

    async for event in agent.astream(initial_state, config, stream_mode="values"):
        if verbose:
            logger.debug("Iteration: %s", iteration)
        iteration += 1

        if "messages" in event and event["messages"]:
            last_message = event["messages"][-1]
            last_message_content = getattr(last_message, "content", None)

            if last_msg_content is not None and last_message_content == last_msg_content:
                if verbose:
                    logger.debug("⏳")
                continue

            last_msg_content = last_message_content
            final_response = last_message_content

            if verbose:
                last_message.pretty_print()

    return final_response or "No response generated"


async def handle_generic_message_with_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle generic messages using the AI agent."""
    try:
        message = update.message
        if message is None:
            logger.error("Failed to process update object. It had no message")
            return

        user_message = update.message.text
        chat_id = update.effective_chat.id

        logger.info("Processing AI message for chat_id %s: %s", chat_id, user_message)

        # React to the audio message to indicate processing
        await context.bot.set_message_reaction(
            chat_id=chat_id, message_id=message.message_id, reaction=ReactionEmoji.HIGH_VOLTAGE_SIGN
        )

        # Get the AI response
        response = await get_agent_response(user_message, chat_id, verbose=True)

        # Send the response back to the user
        try:
            await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
        except Exception as se:
            if "Can't parse entities" in str(se):
                # try to send without markdown
                await update.message.reply_text(response)
            else:
                raise se

    except Exception as e:
        logger.error(f"Error in handle_generic_message_with_ai: {e}")
        await update.message.reply_text("Sorry, I encountered an error processing your request. Please try again.")



# this allows testing the agent outside of the bot
if __name__ == "__main__":
    user_message = "Monica gastó $1,695,050.00 pesos colombianos en el avión de Satena para ir a Ocaña usando mi cuenta de Bancolombia. Añade esta transacción"
    chat_id = 420420420  # debug chat id
    result = get_agent_response(user_message, chat_id)
    logger.info("Final result: %s", result)
