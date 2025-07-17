import datetime
import json
import logging

import dateparser
from langchain_core.tools import tool
from lunchable import TransactionInsertObject

from lunch import get_lunch_client_for_chat_id

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
    logger.info("Calling add_manual_transaction for chat_id: %s", chat_id)
    try:
        lunch_client = get_lunch_client_for_chat_id(chat_id)

        # Validate that the account exists and is manually managed
        assets = lunch_client.get_assets()
        account = next((asset for asset in assets if asset.id == account_id), None)
        if not account:
            return json.dumps({"error": f"Account with ID {account_id} not found"})

        if account.type_name not in {"credit", "cash"}:
            return json.dumps(
                {
                    "error": f"Account '{account.name}' is not manually managed. Only credit and cash accounts support manual transactions."
                }
            )

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
            status=TransactionInsertObject.StatusEnum.cleared,
            asset_id=account_id,
            recurring_id=None,
            external_id=None,
            tags=None,
        )

        # Insert transaction
        transaction_ids = lunch_client.insert_transactions(transaction_obj)
        transaction_id = transaction_ids[0]

        # Get the created transaction to return details
        transaction = lunch_client.get_transaction(transaction_id)
        logger.info(f"Transaction {transaction_id} created")

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
        logger.error(f"Error parsing date reference: {e}")
        return json.dumps({"error": str(e)})
