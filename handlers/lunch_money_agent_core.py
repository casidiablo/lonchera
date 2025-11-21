import datetime
import logging
from dataclasses import dataclass

import dspy
from pydantic import BaseModel, Field

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the Lunch Money agent."""

    chat_id: int
    language: str = "English"
    timezone: str = "UTC"
    model_name: str | None = None
    is_admin: bool = False


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


class LunchMoneyAgentSignature(dspy.Signature):
    """You are a helpful assistant that can provide Lunch Money information and help users manage their finances.
    Work on the user request systematically. User only provides a single request
    and there is no way for them to refine their choices so make sure to fullfill
    the request or fail with a reasonable message.
    NEVER TELL THE USER WHAT YOU INTENT TO DO, JUST DO IT.
    NEVER TELL TO USER TO CONFIRM OR APPROVE YOUR ACTIONS.
    ONLY add a transaction when the user asks you to.

    If user asks you to update a transaction, like setting notes, transaction, or tags, use the
    update_transaction tool.

    If user asked you to categorize the transaction, make sure to call get_categories
    to get the right category ID. Unless specified, only update the transaction's category.

    If all the user provides is a random concept like: "milk and honey", or "car payment",
    assume they want to set the transaction's notes and assign a category.

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

    When user asks for balances, remember to include the currency when possible.
    If the user asks for the balance of one or more accounts make sure to use
    `get_plaid_account_balances`, `get_manual_accounts_balances`, and `get_crypto_accounts_balances`
    before providing an answer.

    Note that when user asks for how much money they have in cash, you must bias
    towards using `get_manual_accounts_balances`.

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
    - Do never leak the transaction ID
    """

    request = dspy.InputField(desc="The user's request.")
    current_date_info = dspy.InputField(desc="This is the current date and the user's time zone")
    language = dspy.InputField(
        desc="Preferred user's language. All your responses, explanations, and messages should be written in this language."
    )
    transaction_id = dspy.InputField(desc="ID of the Lunch Money transaction the user is referring to.")
    chat_id = dspy.InputField(
        desc="ID of the Telegram chat the user is in. Always use this ID when interacting with tools that require a chat_id"
    )
    telegram_message_id = dspy.InputField(desc="ID of the Telegram message the user request is in the context of.")
    result: LunchMoneyAgentResponse = dspy.OutputField(desc="Agent response")


def get_dspy_lm(config: AgentConfig) -> dspy.LM:
    """Gets the language model based on agent configuration.

    Args:
        config: AgentConfig containing model preferences and admin status

    Returns:
        Configured dspy.LM instance
    """
    # Default model for non-admin users
    default_model = "google/gemini-2.5-flash"

    # Admin-only models
    admin_models = [
        "openai/gpt-4.1-nano",
        "openai/gpt-4.1-mini",
        "openai/gpt-4.1",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openai/o4-mini",
        "google/gemini-2.5-flash",
        "anthropic/claude-haiku-4.5",
    ]

    # Determine which model to use
    selected_model = config.model_name if config.model_name else default_model

    # Only allow advanced models for admin users
    if config.is_admin and selected_model in admin_models:
        model_name = selected_model
        logger.info(f"Using model: {model_name} (admin user)")
    else:
        # Use default model for non-admin users or invalid selections
        model_name = default_model
        logger.info(f"Using model: {model_name} (default)")

    # Prepend openrouter/ for LiteLLM compatibility
    return dspy.LM(model=f"openrouter/{model_name}", temperature=0, max_tokens=50000)


def execute_agent(
    user_prompt: str, config: AgentConfig, tx_id: int | None = None, telegram_message_id: int | None = None
) -> LunchMoneyAgentResponse:
    """Execute the Lunch Money agent with the given prompt and configuration.

    Args:
        user_prompt: The user's request or question
        config: AgentConfig containing chat_id, language, timezone, model preferences
        tx_id: Optional transaction ID if the request is in context of a transaction
        telegram_message_id: Optional Telegram message ID for context

    Returns:
        LunchMoneyAgentResponse with status, message, and transaction IDs

    Raises:
        Exception: Any exceptions from agent execution are propagated to caller
    """
    logger.info("Creating Lunch Money agent for chat_id: %s", config.chat_id)

    # Get language model based on configuration
    lm = get_dspy_lm(config)

    # Define tools list (same as current implementation)
    tools = [
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
    ]

    logger.info("User message: %s", user_prompt)

    # Create DSPy ReAct agent with LunchMoneyAgentSignature and tools
    with dspy.context(lm=lm):
        agent = dspy.ReAct(LunchMoneyAgentSignature, tools=tools)

        # Execute agent with user prompt and config parameters
        response = agent(
            request=user_prompt,
            language=config.language,
            current_date_info=f"{datetime.date.today().strftime('%Y-%m-%d')} user timezone is {config.timezone}",
            transaction_id=tx_id,
            chat_id=config.chat_id,
            telegram_message_id=telegram_message_id,
        )

        # Return LunchMoneyAgentResponse
        return response.result


if __name__ == "__main__":
    """Standalone testing function for the Lunch Money agent core.

    This allows testing the agent logic independently without Telegram bot integration.

    Usage:
        python handlers/lunch_money_agent_core.py
        python handlers/lunch_money_agent_core.py --prompt "Show me my balances"
        python handlers/lunch_money_agent_core.py --mlflow https://mlflow.example.com --prompt "What are my recent transactions?"
    """
    import argparse

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Test Lunch Money agent with optional MLflow tracking")
    parser.add_argument("--mlflow", type=str, help="MLflow tracking URI (e.g., https://mlflow.example.com)")
    parser.add_argument("--prompt", type=str, help="Custom prompt to test (default: 'What are my recent transactions?')")
    args = parser.parse_args()

    # Setup MLflow if requested
    mlflow_enabled = args.mlflow is not None
    if mlflow_enabled:
        import mlflow

        mlflow.set_tracking_uri(args.mlflow)
        mlflow.set_experiment("lonchera")
        mlflow.dspy.autolog()
        logger.info(f"MLflow tracking enabled: {args.mlflow}")

    # Create sample AgentConfig with test values
    test_config = AgentConfig(
        chat_id=123456789,
        language="English",
        timezone="America/New_York",
        model_name="anthropic/claude-haiku-4.5",
        is_admin=False,
    )

    # Use custom prompt if provided, otherwise use default
    test_prompt = args.prompt if args.prompt else "What are my recent transactions?"

    try:
        if mlflow_enabled:
            with mlflow.start_run():
                mlflow.log_param("prompt", test_prompt)
                mlflow.log_param("language", test_config.language)
                mlflow.log_param("timezone", test_config.timezone)

                # Execute the agent
                response = execute_agent(
                    user_prompt=test_prompt, config=test_config, tx_id=None, telegram_message_id=None
                )

                # Log results to MLflow
                mlflow.log_metric("status", 1 if response.status == "success" else 0)
                mlflow.log_text(response.message, "response_message.txt")

                # Print results
                print(f"Status: {response.status}")
                print(f"\nMessage:\n{response.message}")

                if response.transactions_created_ids:
                    print(f"\nTransactions Created: {response.transactions_created_ids}")
                    mlflow.log_param("transactions_created", len(response.transactions_created_ids))

                if response.transaction_updated_ids:
                    print(f"\nTransactions Updated: {response.transaction_updated_ids}")
                    mlflow.log_param("transactions_updated", len(response.transaction_updated_ids))
        else:
            # Execute without MLflow
            response = execute_agent(user_prompt=test_prompt, config=test_config, tx_id=None, telegram_message_id=None)

            # Print results
            print(f"Status: {response.status}")
            print(f"\nMessage:\n{response.message}")

            if response.transactions_created_ids:
                print(f"\nTransactions Created: {response.transactions_created_ids}")

            if response.transaction_updated_ids:
                print(f"\nTransactions Updated: {response.transaction_updated_ids}")

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        logger.exception("Error executing agent")

        if mlflow_enabled:
            mlflow.log_param("error", str(e))
