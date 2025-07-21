import logging
import os
from textwrap import dedent

import requests
from lunchable import LunchMoney, TransactionUpdateObject
from lunchable.models import CategoriesObject, TransactionObject

from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from utils import remove_emojis

logger = logging.getLogger(__name__)

# Constants
HTTP_OK = 200


def get_transaction_input_variable(transaction: TransactionObject, override_notes: str | None = None) -> str:
    tx_input_variable = dedent(
        f"""
    Payee: {transaction.payee}
    Amount: {transaction.amount} {transaction.currency}"""
    )
    if transaction.plaid_metadata is not None:
        tx_input_variable += dedent(
            f"""
        merchant_name: {transaction.plaid_metadata["merchant_name"]}
        name: {transaction.plaid_metadata["name"]}"""
        )

    if transaction.notes or override_notes:
        tx_input_variable += dedent(
            f"""
        notes: {override_notes or transaction.notes}
        """
        )

    return tx_input_variable


def get_categories_input_variable(categories: list[CategoriesObject]) -> str:
    categories_info = []
    for category in categories:
        # when a category has subcategories (children is not empty),
        # we want to add an item to the categories_info with this format:
        # id: subcategory_name (parent_category_name)
        # but when a category has no subcategories, we want to add an item with this format:
        # id: category_name
        if category.children:
            for subcategory in category.children:
                categories_info.append(
                    f"{subcategory.id}:{remove_emojis(subcategory.name)} ({remove_emojis(category.name)})"
                )
        elif category.group_id is None:
            categories_info.append(f"{category.id}:{remove_emojis(category.name)}")
    return "\n".join(categories_info)


def build_prompt(
    transaction: TransactionObject, categories: list[CategoriesObject], override_notes: str | None = None
) -> str:
    logger.info(get_transaction_input_variable(transaction))
    return dedent(
        f"""
This is the transaction information:
{get_transaction_input_variable(transaction, override_notes=override_notes)}

What of the following categories would you suggest for this transaction?

If the Payee is Amazon, then choose the Amazon category ONLY if the notes of the transaction can't be categorized as a specific non-Amazon category.

Respond with the ID of the category, and only the ID.

These are the available categories (using the format `ID:Category Name`):

{get_categories_input_variable(categories)}

Remember to ONLY RESPOND with the ID, and nothing else.

DO NOT EXPLAIN YOURSELF. JUST RESPOND WITH THE ID or null.
        """
    )


def send_message_to_llm(content):
    url = "https://api.deepinfra.com/v1/openai/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + os.getenv("DEEPINFRA_API_KEY", "")}
    data = {
        "model": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
        "temperature": 0.0,
        "messages": [{"role": "user", "content": content}],
    }

    response = requests.post(url, headers=headers, json=data)
    get_db().inc_metric("deepinfra_requests")

    if response.status_code == HTTP_OK:
        response_json = response.json()
        usage = response_json.get("usage", {})
        get_db().inc_metric("deepinfra_prompt_tokens", usage.get("prompt_tokens", 0))
        get_db().inc_metric("deepinfra_completion_tokens", usage.get("completion_tokens", 0))
        get_db().inc_metric("deepinfra_estimated_cost", usage.get("estimated_cost", 0.0))

        return response_json["choices"][0]["message"]["content"]
    else:
        response.raise_for_status()


def auto_categorize(tx_id: int, chat_id: int) -> str:
    lunch = get_lunch_client_for_chat_id(chat_id)
    categories = lunch.get_categories()

    try:
        tx, category_id = get_suggested_category_id(tx_id, lunch)
        if int(category_id) == tx.category_id:
            # no need to recategorize
            return "Already categorized correctly"

        logger.info(f"AI response: {category_id}")
        for cat in categories:
            if cat.id == int(category_id):
                settings = get_db().get_current_settings(chat_id)
                if settings.mark_reviewed_after_categorized:
                    lunch.update_transaction(tx_id, TransactionUpdateObject(category_id=cat.id, status="cleared"))  # type: ignore
                else:
                    lunch.update_transaction(tx_id, TransactionUpdateObject(category_id=cat.id))  # type: ignore
                return f"Transaction recategorized to {cat.name}"

        return "AI failed to categorize the transaction"
    except Exception as e:
        logger.exception(f"Error while categorizing transaction: {e}")
        return "AI crashed while categorizing the transaction"


def get_suggested_category_id(
    tx_id: int, lunch: LunchMoney, override_notes: str | None = None
) -> tuple[TransactionObject, int]:
    tx = lunch.get_transaction(tx_id)
    categories = lunch.get_categories()

    prompt = build_prompt(tx, categories, override_notes=override_notes)
    logger.info(prompt)

    try:
        category_id = send_message_to_llm(prompt)
        return tx, int(category_id or 0)
    except Exception as e:
        logger.exception(f"Error while categorizing transaction: {e}")
        return tx, -1
