import datetime
import json
import logging

import dateparser
from langchain_core.tools import tool
from lunchable import TransactionInsertObject

from lunch import get_lunch_client_for_chat_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aitools")


@tool
async def get_my_lunch_money_user_info(chat_id: int) -> str:
    """get my lunch money user info"""
    logger.info("Calling get_my_lunch_money_user_info for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        user_info = lunch_client.get_user()
        return json.dumps(user_info.model_dump())
    except Exception as e:
        logger.error("Error fetching user info: %s", str(e), exc_info=True)
        return json.dumps({"error": str(e)})


@tool
def get_account_balances(chat_id: int) -> str:
    """Get current balance for all accounts"""
    logger.info("Calling get_account_balances for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        plaid_accounts = lunch_client.get_plaid_accounts()
        logger.info("Retrieved %d Plaid accounts", len(plaid_accounts))

        accounts_data = []
        for acc in plaid_accounts:
            logger.debug("Processing account: %s (id: %s, type: %s)",
                        acc.display_name or acc.name, acc.id, acc.type)
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
        logger.error("Error fetching account balances: %s", str(e), exc_info=True)
        return json.dumps({"error": str(e)})


@tool
def get_manual_asset_accounts(chat_id: int) -> str:
    """Get manually-managed asset accounts that can be used for manual transactions"""
    logger.info("Calling get_manual_asset_accounts for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)

        assets = lunch_client.get_assets()
        logger.info("Retrieved %d total assets", len(assets))

        # Filter for manually managed accounts (credit and cash types)
        manual_accounts = [asset for asset in assets if asset.type_name in {"credit", "cash"}]
        logger.info("Filtered to %d manually managed accounts (credit/cash types)", len(manual_accounts))

        accounts_data = []
        for asset in manual_accounts:
            logger.debug("Processing manual account: %s (id: %s, type: %s)",
                        asset.display_name or asset.name, asset.id, asset.type_name)
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

        logger.info("Successfully processed %d manual accounts", len(accounts_data))
        return json.dumps({"manual_accounts": accounts_data})
    except Exception as e:
        logger.error("Error fetching manual asset accounts: %s", str(e), exc_info=True)
        return json.dumps({"error": str(e)})


@tool
def get_categories(chat_id: int) -> str:
    """Get all available categories for transactions"""
    logger.info("Calling get_categories for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        categories = lunch_client.get_categories()
        logger.info("Retrieved %d categories", len(categories))

        categories_data = []
        for category in categories:
            if category.is_group:
                continue  # Skip category groups
            category_info = {
                "id": category.id,
                "name": category.name,
            }
            categories_data.append(category_info)

        return json.dumps({"categories": categories_data})
    except Exception as e:
        logger.error("Error fetching categories: %s", str(e), exc_info=True)
        return json.dumps({"error": str(e)})


@tool
def add_manual_transaction(
    chat_id: int,
    date: str,
    account_id: int,
    payee: str,
    amount: float,
    is_received: bool = False,
    category_id: int | None = None,
    notes: str | None = None,
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
    logger.info(
        "Calling add_manual_transaction with chat_id=%s, date=%s, account_id=%s, payee=%s, amount=%s, is_received=%s, category_id=%s, notes=%s",
        chat_id, date, account_id, payee, amount, is_received, category_id, notes
    )
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)

        # Validate that the account exists and is manually managed
        logger.info("Fetching assets to validate account_id=%s", account_id)
        assets = lunch_client.get_assets()
        logger.debug("Retrieved %d assets for validation", len(assets))

        account = next((asset for asset in assets if asset.id == account_id), None)
        if not account:
            logger.warning("Account with ID %s not found", account_id)
            return json.dumps({"error": f"Account with ID {account_id} not found"})

        if account.type_name not in {"credit", "cash"}:
            logger.warning("Account '%s' (type: %s) is not manually managed",
                          account.name, account.type_name)
            return json.dumps(
                {
                    "error": f"Account '{account.name}' is not manually managed. Only credit and cash accounts support manual transactions."
                }
            )

        logger.info("Account validated: %s (id: %s, type: %s)",
                   account.name, account.id, account.type_name)

        # Convert received money to negative amount
        final_amount = amount * -1 if is_received else amount
        logger.debug("Transaction amount: %s → %s (%s)",
                    amount, final_amount, "income" if is_received else "expense")

        # Parse the date
        try:
            logger.debug("Parsing date: %s", date)
            transaction_date = datetime.datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            logger.warning("Invalid date format: %s", date)
            return json.dumps({"error": "Invalid date format. Use YYYY-MM-DD"})

        # Create transaction
        if category_id == 0:
            category_id = None

        logger.info("Creating transaction object for account %s: %s to %s for %s %s",
                   account_id, "Income" if is_received else "Payment",
                   payee, abs(final_amount), account.currency.upper())

        transaction_obj = TransactionInsertObject(
            date=transaction_date,
            category_id=category_id,
            payee=payee,
            amount=final_amount,
            currency=account.currency.lower(),
            notes=notes,
            status=TransactionInsertObject.StatusEnum.cleared,
            asset_id=account_id,
            recurring_id=None,
            external_id=None,
            tags=None,
        )

        # Insert transaction
        transaction_ids = lunch_client.insert_transactions(transaction_obj)
        transaction_id = transaction_ids[0]
        logger.info("Transaction inserted with ID: %s", transaction_id)

        # Get the created transaction to return details
        transaction = lunch_client.get_transaction(transaction_id)

        return json.dumps(
            {
                "success": True,
                "transaction_id": transaction_id,
                "transaction": {
                    "id": transaction.id,
                    "date": transaction.date.isoformat(),
                    "payee": transaction.payee,
                    "amount": float(transaction.amount),
                    "currency": transaction.currency.upper() if transaction.currency else "USD",
                    "account_name": account.name,
                    "category_name": transaction.category_name if transaction.category_name else "Uncategorized",
                    "notes": transaction.notes,
                },
            }
        )
    except Exception as e:
        logger.error(f"Error adding manual transaction: {e}")
        return json.dumps({"error": str(e)})


@tool
def get_crypto_accounts(chat_id: int) -> str:
    """Get all cryptocurrency accounts and their balances"""
    logger.info("Calling get_crypto_accounts for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        crypto_accounts = lunch_client.get_crypto()
        logger.info("Retrieved %d crypto accounts", len(crypto_accounts))

        accounts_data = []
        for crypto in crypto_accounts:
            logger.debug("Processing crypto account: %s (id: %s, currency: %s)",
                        crypto.display_name or crypto.name, crypto.id, crypto.currency)
            account_info = {
                "id": crypto.id,
                "name": crypto.name,
                "display_name": crypto.display_name,
                "balance": float(crypto.balance),
                "currency": crypto.currency.upper(),
                "institution_name": crypto.institution_name,
                "last_update": crypto.balance_as_of.isoformat() if crypto.balance_as_of else None,
                "status": crypto.status,
            }
            accounts_data.append(account_info)

        logger.info("Successfully processed %d crypto accounts", len(accounts_data))
        return json.dumps({"crypto_accounts": accounts_data})
    except Exception as e:
        logger.error("Error fetching crypto accounts: %s", str(e), exc_info=True)
        return json.dumps({"error": str(e)})


@tool
def calculate(expression: str) -> str:
    """Perform basic arithmetic calculations safely.

    Supports basic arithmetic operations: +, -, *, /, %, ** (power), and parentheses.
    Also supports common math functions like abs, round, min, max.

    Args:
        expression: Mathematical expression to evaluate (e.g., "2 + 3 * 4", "round(15.7)", "abs(-5)")

    Returns:
        JSON with the calculation result
    """
    logger.info("Calling calculate for expression: %s", expression)
    try:
        # Define safe functions that can be used in expressions
        safe_functions = {
            'abs': abs,
            'round': round,
            'min': min,
            'max': max,
            'pow': pow,
            'sum': sum,
        }

        # Define safe names (no built-ins that could be dangerous)
        safe_names = {
            "__builtins__": {},
            **safe_functions
        }

        logger.info("Evaluating math expression: %r", expression)
        # Evaluate the expression safely
        result = eval(expression, safe_names, {})
        logger.info("Expression evaluated successfully: %r = %r", expression, result)

        return json.dumps({
            "success": True,
            "expression": expression,
            "result": result,
        })

    except ZeroDivisionError:
        logger.warning("Division by zero in expression: %r", expression)
        return json.dumps({"error": "Division by zero"})
    except (SyntaxError, NameError, TypeError, ValueError) as e:
        logger.warning("Invalid expression %r: %s", expression, str(e))
        return json.dumps({"error": f"Invalid expression: {str(e)}"})
    except Exception as e:
        logger.error("Error calculating expression %r: %s", expression, str(e), exc_info=True)
        return json.dumps({"error": f"Calculation error: {str(e)}"})


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
        logger.info("Parsing date reference: %r", date_reference)
        base_date = datetime.date.today()
        logger.debug("Base date for reference: %s", base_date.isoformat())

        parsed_datetime = dateparser.parse(date_reference)

        if parsed_datetime is None:
            logger.warning("Failed to parse date reference: %r", date_reference)
            return json.dumps({"error": f"Could not parse date reference: {date_reference}"})

        result_date = parsed_datetime.date()
        logger.info("Successfully parsed date reference %r to %s",
                   date_reference, result_date.isoformat())

        days_diff = (result_date - base_date).days
        if days_diff != 0:
            logger.info("Date is %d days %s today",
                       abs(days_diff), "after" if days_diff > 0 else "before")

        return json.dumps(
            {
                "success": True,
                "date": result_date.strftime("%Y-%m-%d"),
                "formatted_date": result_date.strftime("%B %d, %Y"),
                "reference": date_reference,
                "base_date": base_date.strftime("%Y-%m-%d"),
            }
        )

    except Exception as e:
        logger.error("Error parsing date reference %r: %s", date_reference, str(e), exc_info=True)
        return json.dumps({"error": str(e)})
