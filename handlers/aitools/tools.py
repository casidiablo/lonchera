import datetime
import json
import logging

import dateparser
from langchain_core.tools import tool
from lunchable import TransactionInsertObject, TransactionUpdateObject

from constants import NOTES_MAX_LENGTH
from lunch import get_lunch_client_for_chat_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aitools")


def transaction_to_dict(transaction) -> dict:
    """Convert a transaction object to a dictionary.

    Args:
        transaction: The transaction object from the API

    Returns:
        Dictionary representation of the transaction
    """
    # Handle tags - they might be strings or objects with name attribute
    tags_list = []
    if transaction.tags:
        tags_list = [tag.name if hasattr(tag, "name") else tag for tag in transaction.tags]

    transaction_info = {
        "id": transaction.id,
        "date": transaction.date.isoformat(),
        "payee": transaction.payee,
        "amount": float(transaction.amount),
        "currency": transaction.currency.upper() if transaction.currency else "USD",
        "category_name": transaction.category_name if transaction.category_name else "Uncategorized",
        "category_id": transaction.category_id,
        "notes": transaction.notes,
        "tags": tags_list,
        "status": transaction.status,
        "asset_id": transaction.asset_id,
        "asset_name": transaction.asset_name,
        "is_income": float(transaction.amount) < 0,  # Negative amounts are income in Lunch Money
        "original_name": getattr(transaction, "original_name", None),
        "is_pending": getattr(transaction, "is_pending", None),
    }

    return transaction_info


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
def get_plaid_account_balances(chat_id: int) -> str:
    """Get current balance for all Plaid-managed accounts"""
    logger.info("Calling get_plaid_account_balances for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        plaid_accounts = lunch_client.get_plaid_accounts()
        logger.info("Retrieved %d Plaid accounts", len(plaid_accounts))

        accounts_data = []
        for acc in plaid_accounts:
            logger.debug("Processing account: %s (id: %s, type: %s)", acc.display_name or acc.name, acc.id, acc.type)
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
def get_manual_accounts_balances(chat_id: int) -> str:
    """Get manually-managed asset accounts that can be used for manual transactions"""
    logger.info("Calling get_manual_accounts_balances for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)

        assets = lunch_client.get_assets()
        logger.info("Retrieved %d total assets", len(assets))

        # Filter for manually managed accounts (credit and cash types)
        manual_accounts = [asset for asset in assets if asset.type_name in {"credit", "cash"}]
        logger.info("Filtered to %d manually managed accounts (credit/cash types)", len(manual_accounts))

        accounts_data = []
        for asset in manual_accounts:
            logger.debug(
                "Processing manual account: %s (id: %s, type: %s)",
                asset.display_name or asset.name,
                asset.id,
                asset.type_name,
            )
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
            category_info = {"id": category.id, "name": category.name}
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
        chat_id,
        date,
        account_id,
        payee,
        amount,
        is_received,
        category_id,
        notes,
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
            logger.warning("Account '%s' (type: %s) is not manually managed", account.name, account.type_name)
            return json.dumps(
                {
                    "error": f"Account '{account.name}' is not manually managed. Only credit and cash accounts support manual transactions."
                }
            )

        logger.info("Account validated: %s (id: %s, type: %s)", account.name, account.id, account.type_name)

        # Convert received money to negative amount
        final_amount = amount * -1 if is_received else amount
        logger.debug("Transaction amount: %s → %s (%s)", amount, final_amount, "income" if is_received else "expense")

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

        logger.info(
            "Creating transaction object for account %s: %s to %s for %s %s",
            account_id,
            "Income" if is_received else "Payment",
            payee,
            abs(final_amount),
            account.currency.upper(),
        )

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
        logger.error(f"Error adding manual transaction: {e}", exc_info=True)
        return json.dumps({"error": str(e)})


@tool
def get_crypto_accounts_balances(chat_id: int) -> str:
    """Get all cryptocurrency accounts and their balances"""
    logger.info("Calling get_crypto_accounts_balances for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        crypto_accounts = lunch_client.get_crypto()
        logger.info("Retrieved %d crypto accounts", len(crypto_accounts))

        accounts_data = []
        for crypto in crypto_accounts:
            logger.debug(
                "Processing crypto account: %s (id: %s, currency: %s)",
                crypto.display_name or crypto.name,
                crypto.id,
                crypto.currency,
            )
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


def prepare_transaction_update_data(
    payee: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
    category_id: int | None = None,
    amount: float | None = None,
    date: str | None = None,
) -> dict | str:
    """Prepare update data dictionary for transaction update.

    Args:
        payee: New payee name (optional)
        notes: New notes text (optional, max 350 characters)
        tags: List of tags to set (optional, without # prefix)
        category_id: New category ID (optional)
        amount: New transaction amount (optional)
        date: New transaction date in YYYY-MM-DD format (optional)

    Returns:
        Dictionary with update data or error string if validation fails
    """
    update_data = {}

    if payee is not None:
        update_data["payee"] = payee

    if notes is not None:
        # Truncate notes if too long (same as in general.py)
        if len(notes) > NOTES_MAX_LENGTH:
            notes = notes[:NOTES_MAX_LENGTH]
            logger.warning("Notes truncated to %d characters", NOTES_MAX_LENGTH)
        update_data["notes"] = notes

    if tags is not None:
        # Ensure tags don't have # prefix
        clean_tags = [tag.lstrip("#") for tag in tags]
        update_data["tags"] = clean_tags

    if category_id is not None:
        if category_id == 0:
            category_id = None  # 0 means uncategorized
        update_data["category_id"] = category_id

    if amount is not None:
        update_data["amount"] = amount

    if date is not None:
        try:
            transaction_date = datetime.datetime.strptime(date, "%Y-%m-%d")
            update_data["date"] = transaction_date
        except ValueError:
            logger.warning("Invalid date format: %s", date)
            return "Invalid date format. Use YYYY-MM-DD"

    if not update_data:
        logger.warning("No fields provided to update")
        return "No fields provided to update"

    return update_data


@tool
def update_transaction(
    chat_id: int,
    transaction_id: int,
    payee: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
    category_id: int | None = None,
    amount: float | None = None,
    date: str | None = None,
) -> str:
    """Update details of an existing transaction.

    Args:
        chat_id: The chat ID
        transaction_id: ID of the transaction to update
        payee: New payee name (optional)
        notes: New notes text (optional, max 350 characters)
        tags: List of tags to set (optional, without # prefix)
        category_id: New category ID (optional)
        amount: New transaction amount (optional)
        date: New transaction date in YYYY-MM-DD format (optional)

    Returns:
        JSON with success status and updated transaction details
    """
    logger.info(
        "Calling update_transaction with chat_id=%s, transaction_id=%s, payee=%s, notes=%s, tags=%s, category_id=%s, amount=%s, date=%s",
        chat_id,
        transaction_id,
        payee,
        notes,
        tags,
        category_id,
        amount,
        date,
    )
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)

        # Prepare update data using helper function
        update_data = prepare_transaction_update_data(
            payee=payee,
            notes=notes,
            tags=tags,
            category_id=category_id,
            amount=amount,
            date=date,
        )

        # Check if preparation returned an error
        if isinstance(update_data, str):
            return json.dumps({"error": update_data})

        # Update the transaction
        logger.info("Updating transaction %s with fields: %s", transaction_id, list(update_data.keys()))
        lunch_client.update_transaction(transaction_id, TransactionUpdateObject(**update_data))

        # Get the updated transaction to return details
        updated_transaction = lunch_client.get_transaction(transaction_id)
        logger.info("Transaction %s updated successfully", transaction_id)

        return json.dumps(
            {
                "success": True,
                "transaction_id": transaction_id,
                "updated_fields": list(update_data.keys()),
                "transaction": transaction_to_dict(updated_transaction),
            }
        )
    except Exception as e:
        logger.error("Error updating transaction %s: %s", transaction_id, str(e), exc_info=True)
        return json.dumps({"error": str(e)})


@tool
def get_transactions(
    chat_id: int,
    limit: int = 10,
    offset: int = 0,
    start_date: str | None = None,
    end_date: str | None = None,
    payee: str | None = None,
    category_id: int | None = None,
    asset_id: int | None = None,
    tag_id: int | None = None,
) -> str:
    """Get transactions with optional filtering.

    Args:
        chat_id: The chat ID
        limit: Maximum number of transactions to return (default: 10, max: 100)
        offset: Number of transactions to skip for pagination (default: 0)
        start_date: Filter transactions from this date (YYYY-MM-DD format, optional)
        end_date: Filter transactions to this date (YYYY-MM-DD format, optional)
        payee: Filter by payee name (partial match, optional)
        category_id: Filter by category ID (optional)
        asset_id: Filter by asset/account ID (optional)
        tag_id: Filter by tag ID (optional)

    Returns:
        JSON with list of transactions matching the filters
    """
    logger.info(
        "Calling get_transactions with chat_id=%s, limit=%s, offset=%s, start_date=%s, end_date=%s, payee=%s, category_id=%s, asset_id=%s, tag_id=%s",
        chat_id,
        limit,
        offset,
        start_date,
        end_date,
        payee,
        category_id,
        asset_id,
        tag_id,
    )
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)

        # Validate and parse dates
        parsed_start_date = None
        parsed_end_date = None

        if start_date:
            try:
                parsed_start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
                logger.debug("Parsed start_date: %s", parsed_start_date)
            except ValueError:
                logger.warning("Invalid start_date format: %s", start_date)
                return json.dumps({"error": "Invalid start_date format. Use YYYY-MM-DD"})

        if end_date:
            try:
                parsed_end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
                logger.debug("Parsed end_date: %s", parsed_end_date)
            except ValueError:
                logger.warning("Invalid end_date format: %s", end_date)
                return json.dumps({"error": "Invalid end_date format. Use YYYY-MM-DD"})

        # Limit validation
        if limit > 100:
            limit = 100
            logger.warning("Limit capped at 100")

        logger.info("Fetching transactions with filters")
        transactions = lunch_client.get_transactions(
            start_date=parsed_start_date,
            end_date=parsed_end_date,
            tag_id=tag_id,
            recurring_id=None,  # Not filtering by recurring
            plaid_account_id=None,  # Not filtering by plaid account
            category_id=category_id,
            asset_id=asset_id,
            group_id=None,  # Not filtering by group
            is_group=None,  # Not filtering by group status
            status=None,  # Not filtering by status
            offset=offset,
            limit=limit,
        )

        logger.info("Retrieved %d transactions", len(transactions))

        # Apply payee filter if specified (API doesn't support payee filtering directly)
        if payee:
            logger.debug("Applying payee filter: %s", payee)
            payee_lower = payee.lower()
            transactions = [t for t in transactions if t.payee and payee_lower in t.payee.lower()]
            logger.info("Filtered to %d transactions matching payee", len(transactions))

        transactions_data = []
        for transaction in transactions:
            logger.debug("Processing transaction: %s (id: %s)", transaction.payee, transaction.id)
            transaction_info = transaction_to_dict(transaction)
            transactions_data.append(transaction_info)

        logger.info("Successfully processed %d transactions", len(transactions_data))
        return json.dumps(
            {
                "transactions": transactions_data,
                "count": len(transactions_data),
                "filters_applied": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "payee": payee,
                    "category_id": category_id,
                    "asset_id": asset_id,
                    "tag_id": tag_id,
                    "limit": limit,
                    "offset": offset,
                },
            }
        )
    except Exception as e:
        logger.error("Error fetching transactions: %s", str(e), exc_info=True)
        return json.dumps({"error": str(e)})


@tool
def get_single_transaction(chat_id: int, transaction_id: int) -> str:
    """Get details of a specific transaction by ID.

    Args:
        chat_id: The chat ID
        transaction_id: ID of the transaction to retrieve

    Returns:
        JSON with transaction details
    """
    logger.info("Calling get_single_transaction with chat_id=%s, transaction_id=%s", chat_id, transaction_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)

        logger.info("Fetching transaction with ID: %s", transaction_id)
        transaction = lunch_client.get_transaction(transaction_id)

        logger.info("Successfully retrieved transaction: %s", transaction.payee)

        transaction_info = transaction_to_dict(transaction)

        return json.dumps({"success": True, "transaction": transaction_info})
    except Exception as e:
        logger.error("Error fetching transaction %s: %s", transaction_id, str(e), exc_info=True)
        return json.dumps({"error": str(e)})


@tool
def get_recent_transactions(chat_id: int, days: int = 7, limit: int = 20) -> str:
    """Get recent transactions from the last few days.

    This is a convenience tool for quickly accessing recent transactions without complex filtering.

    Args:
        chat_id: The chat ID
        days: Number of days back to look (default: 7)
        limit: Maximum number of transactions to return (default: 20)

    Returns:
        JSON with recent transactions
    """
    logger.info("Calling get_recent_transactions with chat_id=%s, days=%s, limit=%s", chat_id, days, limit)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)

        # Calculate date range
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days)

        logger.info("Fetching recent transactions from %s to %s", start_date, end_date)

        transactions = lunch_client.get_transactions(
            start_date=start_date, end_date=end_date, limit=min(limit, 100), offset=0
        )

        logger.info("Retrieved %d recent transactions", len(transactions))

        transactions_data = []
        for transaction in transactions:
            transaction_info = transaction_to_dict(transaction)
            transactions_data.append(transaction_info)

        return json.dumps(
            {
                "success": True,
                "transactions": transactions_data,
                "count": len(transactions_data),
                "date_range": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "days": days},
            }
        )

    except Exception as e:
        logger.error("Error fetching recent transactions: %s", str(e), exc_info=True)
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
        safe_functions = {"abs": abs, "round": round, "min": min, "max": max, "pow": pow, "sum": sum}

        # Define safe names (no built-ins that could be dangerous)
        safe_names = {"__builtins__": {}, **safe_functions}

        logger.info("Evaluating math expression: %r", expression)
        # Evaluate the expression safely
        result = eval(expression, safe_names, {})
        logger.info("Expression evaluated successfully: %r = %r", expression, result)

        return json.dumps({"success": True, "expression": expression, "result": result})

    except ZeroDivisionError:
        logger.warning("Division by zero in expression: %r", expression)
        return json.dumps({"error": "Division by zero"})
    except (SyntaxError, NameError, TypeError, ValueError) as e:
        logger.warning("Invalid expression %r: %s", expression, str(e))
        return json.dumps({"error": f"Invalid expression: {e!s}"})
    except Exception as e:
        logger.error("Error calculating expression %r: %s", expression, str(e), exc_info=True)
        return json.dumps({"error": f"Calculation error: {e!s}"})


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
        logger.info("Successfully parsed date reference %r to %s", date_reference, result_date.isoformat())

        days_diff = (result_date - base_date).days
        if days_diff != 0:
            logger.info("Date is %d days %s today", abs(days_diff), "after" if days_diff > 0 else "before")

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
