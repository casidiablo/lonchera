import logging
from datetime import datetime, timedelta

from lunchable import LunchMoney
from telegram.ext import ContextTypes

from budget_messaging import hide_budget_categories, send_budget, show_budget_categories, show_bugdget_for_category
from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from telegram_extensions import Update

logger = logging.getLogger("budget_handler")

# Constants
DECEMBER_MONTH = 12


def end_of_month_for(d: datetime) -> datetime:
    # Determine the first day of the next month
    if d.month == DECEMBER_MONTH:  # December
        d = datetime(d.year + 1, 1, 1)
    else:
        d = datetime(d.year, d.month + 1, 1)
    # Subtract one day from the first day of the next month
    return d - timedelta(days=1)


def get_default_budget_range() -> tuple[datetime, datetime]:
    """Get the budget for the current month."""
    # get a datetime of the first day of the current month
    first_day_current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # get the end of the month
    end_of_month = end_of_month_for(first_day_current_month)

    return first_day_current_month, end_of_month


def get_budget_range_from(date: datetime) -> tuple[datetime, datetime]:
    end_of_month = end_of_month_for(date)
    return date, end_of_month


def get_default_budget(lunch: LunchMoney):
    """Get the budget for the current month."""
    # get a datetime of the first day of the current month
    first_day_current_month, final_day_current_month = get_default_budget_range()

    return lunch.get_budgets(start_date=first_day_current_month, end_date=final_day_current_month)


async def handle_show_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a message with the current budget."""
    message_id = None
    if update.callback_query and update.callback_query.data:
        budget_date = update.callback_data_suffix
        budget_date, budget_end_date = get_budget_range_from(datetime.fromisoformat(budget_date))
        if update.callback_query.message:
            message_id = update.callback_query.message.message_id
    else:
        budget_date, budget_end_date = get_default_budget_range()

    lunch = get_lunch_client_for_chat_id(update.chat_id)
    logger.info(f"Pulling budget for chat id {update.chat_id}...")

    budget = lunch.get_budgets(start_date=budget_date, end_date=budget_end_date)
    await send_budget(update, context, budget, budget_date, message_id)

    # delete command message
    await update.safe_delete_message()


async def handle_btn_show_budget_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Updates the message to show the budget categories available."""
    budget_date = update.callback_data_suffix
    budget_date = datetime.fromisoformat(budget_date)

    lunch = get_lunch_client_for_chat_id(update.chat_id)

    budget_date, final_day_current_month = get_budget_range_from(budget_date)
    budget = lunch.get_budgets(start_date=budget_date, end_date=final_day_current_month)

    await show_budget_categories(update, context, budget, budget_date)


async def handle_btn_hide_budget_categories(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Updates the message to hide the budget categories."""
    budget_date = update.callback_data_suffix
    budget_date = datetime.fromisoformat(budget_date)

    lunch = get_lunch_client_for_chat_id(update.chat_id)

    budget_date, budget_end_date = get_budget_range_from(budget_date)
    budget = lunch.get_budgets(start_date=budget_date, end_date=budget_end_date)

    await hide_budget_categories(update, budget, budget_date)


async def handle_btn_show_budget_for_category(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Updates the message to show the budget for a specific category"""
    if not update.callback_query or not update.callback_query.data or not update.callback_query.message:
        return

    parts = update.callback_data_suffix
    budget_date = parts[1]
    budget_date = datetime.fromisoformat(budget_date)
    category_id = int(parts[2])

    lunch = get_lunch_client_for_chat_id(update.chat_id)

    budget_date, budget_end_date = get_budget_range_from(budget_date)
    all_budget = lunch.get_budgets(start_date=budget_date, end_date=budget_end_date)

    # get super category
    category = lunch.get_category(category_id)
    children_categories_ids = []
    if category and category.children:
        children_categories_ids = [child.id for child in category.children]

    sub_budget = []
    for budget_item in all_budget:
        if budget_item.category_id in children_categories_ids:
            sub_budget.append(budget_item)

    settings = get_db().get_current_settings(update.chat_id)
    tagging = settings.tagging if settings else True

    await show_bugdget_for_category(update, all_budget, sub_budget, budget_date, tagging)


async def handle_done_budget(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Done' button press to delete the budget message."""
    await update.safe_delete_message()
