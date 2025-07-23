import logging
from datetime import datetime, timedelta

from lunchable.models import BudgetObject
from telegram import InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from persistence import get_db
from telegram_extensions import Update
from utils import Keyboard, make_tag

logger = logging.getLogger("messaging")

# Constants
DECEMBER_MONTH = 12
MAX_PROGRESS_BAR_BLOCKS = 10


def get_bugdet_buttons(current_budget_date: datetime) -> InlineKeyboardMarkup:
    if current_budget_date.month == 1:
        previous_month = current_budget_date.replace(month=12, year=current_budget_date.year - 1)
    else:
        previous_month = current_budget_date.replace(month=current_budget_date.month - 1)

    first_day_current_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    next_month = None
    if current_budget_date < first_day_current_month:
        if current_budget_date.month == DECEMBER_MONTH:
            next_month = current_budget_date.replace(month=1, year=current_budget_date.year + 1)
        else:
            next_month = current_budget_date.replace(month=current_budget_date.month + 1)

    kbd = Keyboard()
    kbd += (f"⏮️ {previous_month.strftime('%B %Y')}", f"showBudget_{previous_month.isoformat()}")
    if next_month:
        kbd += (f"{next_month.strftime('%B %Y')} ⏭️", f"showBudget_{next_month.isoformat()}")

    kbd += ("Details", f"showBudgetCategories_{current_budget_date.isoformat()}")
    kbd += ("Done", "doneBudget")

    return kbd.build()


def get_budget_category_buttons(budget_items: list[BudgetObject], budget_date: datetime) -> InlineKeyboardMarkup:
    kbd = Keyboard()
    for budget_item in budget_items:
        kbd += (budget_item.category_name, f"showBudgetDetails_{budget_date.isoformat()}_{budget_item.category_id}")

    kbd += ("Back", f"exitBudgetDetails_{budget_date}")
    kbd += ("Done", "doneBudget")
    return kbd.build(columns=2)


def _create_budget_progress_bar(spending_to_base: float, budgeted: float) -> tuple[str, float]:
    """Create a visual progress bar based on spending percentage."""
    pct = spending_to_base * 100 / budgeted
    blocks = int(pct / 10)
    empty = MAX_PROGRESS_BAR_BLOCKS - blocks
    bar = "█" * blocks + "░" * empty
    extra = ""
    if blocks > MAX_PROGRESS_BAR_BLOCKS:
        bar = "█" * MAX_PROGRESS_BAR_BLOCKS
        extra = "▓" * (blocks - MAX_PROGRESS_BAR_BLOCKS)
    return f"`[{bar}]{extra}`", pct


def _initialize_budget_data(budget: list[BudgetObject]) -> tuple[dict, dict]:
    """Initialize budget data by grouping subcategories into parent categories."""
    total_budget_per_supercategory = {}
    budget_currency_per_supercategory = {}

    for budget_item in budget:
        if budget_item.category_group_name is not None:
            _, budget_data = next(iter(budget_item.data.items()))
            if budget_data.budget_to_base is not None:
                total_budget_per_supercategory[budget_item.group_id] = (
                    total_budget_per_supercategory.get(budget_item.group_id, 0) + budget_data.budget_to_base
                )
            # just use the last one
            if budget_data.budget_currency:
                budget_currency_per_supercategory[budget_item.group_id] = budget_data.budget_currency

    return total_budget_per_supercategory, budget_currency_per_supercategory


def build_budget_message(budget: list[BudgetObject], budget_date: datetime, tagging: bool = True):
    msg = ""
    total_expenses_budget = 0
    total_income_budget = 0
    total_income = 0
    total_spent = 0
    net_spent = 0

    # first, lets group all the subcategories into their parent category
    # and sum the budgeted and spent amounts
    total_budget_per_supercategory, budget_currency_per_supercategory = _initialize_budget_data(budget)

    for budget_item in budget:
        if budget_item.category_group_name is None and budget_item.category_id is not None:
            _, budget_data = next(iter(budget_item.data.items()))
            spending_to_base = budget_data.spending_to_base
            budgeted = total_budget_per_supercategory.get(budget_item.category_id, 0)
            if budgeted is None or budgeted == 0:
                logger.info(f"No budget data for: {budget_item}")
                continue
            total_spent += spending_to_base
            if budget_item.is_income:
                spending_to_base = -spending_to_base
                total_income_budget += budgeted
                total_income += spending_to_base
            else:
                total_expenses_budget += budgeted
                net_spent += spending_to_base

            progress_bar, pct = _create_budget_progress_bar(spending_to_base, budgeted)
            cat_name = make_tag(budget_item.category_name, tagging=tagging)

            currency = budget_data.budget_currency
            if currency is None:
                currency = budget_currency_per_supercategory.get(budget_item.category_id) or "NOCURRENCY"

            msg += f"{progress_bar}\n"
            msg += f"{cat_name}: `{spending_to_base:,.1f}` of `{budgeted:,.1f}`"
            msg += f" {currency.upper()} (`{pct:,.1f}%`)"
            if budget_item.is_income:
                msg += "\n_This is income_"
            msg += "\n\n"

    header = f"*Budget for {budget_date.strftime('%B %Y')}*\n\n"
    header += "_This shows the summary for each category group for which there is a budget set._ "
    header += "_To see the budget for a subcategory hit the_ `Details` _button._"

    msg = f"{header}\n\n{msg}"
    msg += f"\n*Total spent*: `{net_spent:,.1f}` of `{total_expenses_budget:,.1f}`"
    currency = budget_data.budget_currency.upper() if budget_data.budget_currency else ""
    msg += f" {currency} budgeted"

    data_from_this_month = budget_date.month == datetime.now().month

    if total_spent > 0 and not data_from_this_month:
        msg += f"\n*You saved*: `{-net_spent:,.1f}` of `{total_expenses_budget:,.1f}` budgeted"
        msg += f" (`{-total_spent * 100 / total_expenses_budget:,.1f}%`)"

    if total_income > 0:
        msg += f"\n*Total income*: `{total_income:,.1f}` of `{total_income_budget:,.1f}` "
        msg += f" {budget_data.budget_currency.upper()} proyected"

    return msg


async def send_budget(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    budget: list[BudgetObject],
    first_day_of_budget: datetime,
    message_id: int | None,
) -> None:
    settings = get_db().get_current_settings(update.chat_id)
    tagging = settings.tagging if settings else True

    msg = build_budget_message(budget, first_day_of_budget, tagging=tagging)

    if message_id:
        await context.bot.edit_message_text(
            chat_id=update.chat_id,
            message_id=message_id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_bugdet_buttons(first_day_of_budget),
        )
    else:
        await context.bot.send_message(
            chat_id=update.chat_id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_bugdet_buttons(first_day_of_budget),
        )


async def show_budget_categories(
    update: Update, _: ContextTypes.DEFAULT_TYPE, budget: list[BudgetObject], budget_date: datetime
) -> None:
    categories = []
    for budget_item in budget:
        if budget_item.category_group_name is None and budget_item.category_id is not None:
            categories.append(budget_item)

    # let the message intact
    await update.safe_edit_message_reply_markup(reply_markup=get_budget_category_buttons(categories, budget_date))


async def hide_budget_categories(update: Update, budget: list[BudgetObject], budget_date: datetime) -> None:
    settings = get_db().get_current_settings(update.chat_id)
    tagging = settings.tagging if settings else True

    msg = build_budget_message(budget, budget_date, tagging=tagging)
    await update.safe_edit_message_text(
        text=msg, parse_mode=ParseMode.MARKDOWN, reply_markup=get_bugdet_buttons(budget_date)
    )


def _create_progress_bar(spent_already: float, budgeted: float) -> tuple[str, float]:
    """Create a visual progress bar based on spending percentage."""
    pct = spent_already * 100 / budgeted
    blocks = int(pct / 10)
    empty = MAX_PROGRESS_BAR_BLOCKS - blocks
    bar = "█" * blocks + "░" * empty
    extra = ""
    if blocks > MAX_PROGRESS_BAR_BLOCKS:
        bar = "█" * MAX_PROGRESS_BAR_BLOCKS
        extra = "▓" * (blocks - MAX_PROGRESS_BAR_BLOCKS)
    return f"`[{bar}]{extra}`", pct


def _format_transaction_link(budget_item: BudgetObject, budget_data, budget_date: datetime) -> str:
    """Format transaction link message for budget item."""
    if budget_data.num_transactions <= 0:
        return "\n"

    plural = "s" if budget_data.num_transactions > 1 else ""
    start_date = budget_date.replace(day=1).strftime("%Y-%m-%d")
    end_date = (budget_date.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    end_date = end_date.strftime("%Y-%m-%d")
    link = "https://my.lunchmoney.app/transactions"
    link += f"?category={budget_item.category_id}&start_date={start_date}&end_date={end_date}&match=all&time=custom"
    return f"    [{budget_data.num_transactions} transaction{plural}]({link})\n\n"


def _get_filtered_categories(all_budget: list[BudgetObject]) -> list[BudgetObject]:
    """Extract categories for the budget category buttons."""
    categories = []
    for budget_item in all_budget:
        if budget_item.category_group_name is None and budget_item.category_id is not None:
            categories.append(budget_item)
    return categories


async def show_bugdget_for_category(
    update: Update,
    all_budget: list[BudgetObject],
    category_budget: list[BudgetObject],
    budget_date: datetime,
    tagging: bool = True,
) -> None:
    msg = ""
    total_budget = 0
    total_spent = 0
    total_income = 0
    total_income_budget = 0
    category_group_name = ""
    budget_currency = ""

    # convert datetime to date
    budget_date_key = datetime.date(budget_date)

    for budget_item in category_budget:
        budget_data = budget_item.data[budget_date_key]
        spent_already = budget_data.spending_to_base
        budgeted = budget_data.budget_to_base
        if budgeted == 0 or budgeted is None:
            continue

        category_group_name = budget_item.category_group_name
        budget_currency = budget_data.budget_currency

        # Track financials
        if budget_item.is_income:
            spent_already = -spent_already
            total_income += spent_already
            total_income_budget += budgeted
        else:
            total_budget += budgeted
            total_spent += spent_already

        # Create progress bar and format item message
        progress_bar, pct = _create_progress_bar(spent_already, budgeted)
        msg += f"{progress_bar}\n"
        msg += f"{make_tag(budget_item.category_name, title=True, tagging=tagging)}: `{spent_already:,.1f}` of `{budgeted:,.1f}`"
        msg += f" {budget_currency} (`{pct:,.1f}%`)\n"
        msg += _format_transaction_link(budget_item, budget_data, budget_date)

    # Format the summary message
    if total_budget > 0 or total_income_budget > 0:
        msg = f"*{category_group_name} budget for {budget_date.strftime('%B %Y')}*\n\n{msg}"
        if total_budget > 0:
            msg += f"*Total spent*: `{total_spent:,.1f}` of `{total_budget:,.1f}`"
            msg += f" {budget_currency} budgeted (`{total_spent * 100 / total_budget:,.1f}%`)\n"
        if total_income_budget > 0:
            msg += f"*Total income*: `{total_income:,.1f}` of `{total_income_budget:,.1f}`"
            msg += f" {budget_currency} proyected"
    else:
        msg = "This category seems to have a global budget, not a per subcategory one"

    categories = _get_filtered_categories(all_budget)

    await update.safe_edit_message_text(
        text=msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_budget_category_buttons(categories, budget_date),
        disable_web_page_preview=True,
    )
