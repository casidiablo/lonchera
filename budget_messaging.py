import logging
from datetime import datetime, timedelta

from lunchable.models import BudgetObject
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from persistence import get_db
from utils import Keyboard, make_tag

logger = logging.getLogger("messaging")


def get_bugdet_buttons(current_budget_date: datetime) -> InlineKeyboardMarkup:
    if current_budget_date.month == 1:
        previous_month = current_budget_date.replace(
            month=12, year=current_budget_date.year - 1
        )
    else:
        previous_month = current_budget_date.replace(
            month=current_budget_date.month - 1
        )

    first_day_current_month = datetime.now().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    next_month = None
    if current_budget_date < first_day_current_month:
        if current_budget_date.month == 12:
            next_month = current_budget_date.replace(
                month=1, year=current_budget_date.year + 1
            )
        else:
            next_month = current_budget_date.replace(
                month=current_budget_date.month + 1
            )

    kbd = Keyboard()
    kbd += (
        f"⏮️ {previous_month.strftime('%B %Y')}",
        f"showBudget_{previous_month.isoformat()}",
    )
    if next_month:
        kbd += (
            f"{next_month.strftime('%B %Y')} ⏭️",
            f"showBudget_{next_month.isoformat()}",
        )

    kbd += ("Details", f"showBudgetCategories_{current_budget_date.isoformat()}")
    kbd += ("Done", "doneBudget")

    return kbd.build()


def get_budget_category_buttons(
    budget_items: list[BudgetObject], budget_date: datetime
) -> InlineKeyboardMarkup:
    kbd = Keyboard()
    for budget_item in budget_items:
        kbd += (
            budget_item.category_name,
            f"showBudgetDetails_{budget_date.isoformat()}_{budget_item.category_id}",
        )

    kbd += ("Back", f"exitBudgetDetails_{budget_date}")
    kbd += ("Done", "doneBudget")
    return kbd.build(columns=2)


def build_budget_message(
    budget: list[BudgetObject], budget_date: datetime, tagging: bool = True
):
    msg = ""
    total_expenses_budget = 0
    total_income_budget = 0
    total_income = 0
    total_spent = 0
    net_spent = 0

    # first, lets group all the subcategories into their parent category
    # and sum the budgeted and spent amounts
    total_budget_per_supercategory = {}
    budget_currency_per_supercategory = {}
    for budget_item in budget:
        if budget_item.category_group_name is not None:
            _, budget_data = next(iter(budget_item.data.items()))
            if budget_data.budget_to_base is not None:
                total_budget_per_supercategory[budget_item.group_id] = (
                    total_budget_per_supercategory.get(budget_item.group_id, 0)
                    + budget_data.budget_to_base
                )
            # just use the last one
            if budget_data.budget_currency:
                budget_currency_per_supercategory[
                    budget_item.group_id
                ] = budget_data.budget_currency

    for budget_item in budget:
        if (
            budget_item.category_group_name is None
            and budget_item.category_id is not None
        ):
            _, budget_data = next(iter(budget_item.data.items()))
            spending_to_base = budget_data.spending_to_base
            budgeted = total_budget_per_supercategory.get(budget_item.category_id, 0)
            if budgeted is None or budgeted == 0:
                print(f"No budget data for: {budget_item}")
                continue
            total_spent += spending_to_base
            if budget_item.is_income:
                spending_to_base = -spending_to_base
                print(
                    f"income before {total_income_budget} + {budgeted} = {total_income_budget + budgeted}"
                )
                total_income_budget += budgeted
                total_income += spending_to_base
            else:
                total_expenses_budget += budgeted
                net_spent += spending_to_base
            pct = spending_to_base * 100 / budgeted

            # number of blocks to draw (max 10)
            blocks = int(pct / 10)
            empty = 10 - blocks
            bar = "█" * blocks + "░" * empty
            extra = ""
            if blocks > 10:
                bar = "█" * 10
                extra = "▓" * (blocks - 10)

            cat_name = make_tag(budget_item.category_name, tagging=tagging)

            currency = budget_data.budget_currency
            if currency is None:
                currency = (
                    budget_currency_per_supercategory.get(budget_item.category_id)
                    or "NOCURRENCY"
                )

            msg += f"`[{bar}]{extra}`\n"
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
    currency = (
        budget_data.budget_currency.upper() if budget_data.budget_currency else ""
    )
    msg += f" {currency} budgeted"

    data_from_this_month = budget_date.month == datetime.now().month

    if total_spent > 0 and not data_from_this_month:
        msg += f"\n*You saved*: `{-net_spent:,.1f}` of `{total_expenses_budget:,.1f}` budgeted"
        msg += f" (`{-total_spent*100/total_expenses_budget:,.1f}%`)"

    if total_income > 0:
        msg += (
            f"\n*Total income*: `{total_income:,.1f}` of `{total_income_budget:,.1f}` "
        )
        msg += f" {budget_data.budget_currency.upper()} proyected"

    return msg


async def send_budget(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    budget: list[BudgetObject],
    first_day_of_budget: datetime,
    message_id: int | None,
) -> None:
    settings = get_db().get_current_settings(update.effective_chat.id)
    tagging = settings.tagging if settings else True

    msg = build_budget_message(budget, first_day_of_budget, tagging=tagging)

    if message_id:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=message_id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_bugdet_buttons(first_day_of_budget),
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_bugdet_buttons(first_day_of_budget),
        )


async def show_budget_categories(
    update: Update,
    _: ContextTypes.DEFAULT_TYPE,
    budget: list[BudgetObject],
    budget_date: datetime,
) -> None:
    categories = []
    for budget_item in budget:
        if (
            budget_item.category_group_name is None
            and budget_item.category_id is not None
        ):
            categories.append(budget_item)

    query = update.callback_query
    # let the message intact
    await query.edit_message_reply_markup(
        reply_markup=get_budget_category_buttons(categories, budget_date)
    )


async def hide_budget_categories(
    update: Update, budget: list[BudgetObject], budget_date: datetime
) -> None:
    settings = get_db().get_current_settings(update.effective_chat.id)
    tagging = settings.tagging if settings else True

    msg = build_budget_message(budget, budget_date, tagging=tagging)
    query = update.callback_query
    await query.edit_message_text(
        text=msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_bugdet_buttons(budget_date),
    )


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

    # convert datetime to date
    budget_date_key = datetime.date(budget_date)

    for budget_item in category_budget:
        budget_data = budget_item.data[budget_date_key]
        spent_already = budget_data.spending_to_base
        budgeted = budget_data.budget_to_base
        if budgeted == 0 or budgeted is None:
            continue

        category_group_name = budget_item.category_group_name

        if budget_item.is_income:
            spent_already = -spent_already
            total_income += spent_already
            total_income_budget += budgeted
        else:
            total_budget += budgeted
            total_spent += spent_already

        pct = spent_already * 100 / budgeted

        # number of blocks to draw (max 10)
        blocks = int(pct / 10)
        empty = 10 - blocks
        bar = "█" * blocks + "░" * empty
        extra = ""
        if blocks > 10:
            bar = "█" * 10
            extra = "▓" * (blocks - 10)

        msg += f"`[{bar}]{extra}`\n"
        msg += f"{make_tag(budget_item.category_name, title=True, tagging=tagging)}: `{spent_already:,.1f}` of `{budgeted:,.1f}`"
        msg += f" {budget_data.budget_currency} (`{pct:,.1f}%`)\n"

        # show transactions list
        if budget_data.num_transactions > 0:
            plural = ""
            if budget_data.num_transactions > 1:
                plural = "s"
            start_date = budget_date.replace(day=1).strftime("%Y-%m-%d")
            end_date = (budget_date.replace(day=1) + timedelta(days=32)).replace(
                day=1
            ) - timedelta(days=1)
            end_date = end_date.strftime("%Y-%m-%d")
            link = "https://my.lunchmoney.app/transactions"
            link += f"?category={budget_item.category_id}&start_date={start_date}&end_date={end_date}&match=all&time=custom"
            msg += (
                f"    [{budget_data.num_transactions} transaction{plural}]({link})\n\n"
            )
        else:
            msg += "\n"

    if total_budget > 0 or total_income_budget > 0:
        msg = f"*{category_group_name} budget for {budget_date.strftime('%B %Y')}*\n\n{msg}"
        if total_budget > 0:
            msg += f"*Total spent*: `{total_spent:,.1f}` of `{total_budget:,.1f}`"
            msg += f" {budget_data.budget_currency} budgeted (`{total_spent*100/total_budget:,.1f}%`)\n"
        if total_income_budget > 0:
            msg += (
                f"*Total income*: `{total_income:,.1f}` of `{total_income_budget:,.1f}`"
            )
            msg += f"{budget_data.budget_currency} proyected"
    else:
        msg = "This category seems to have a global budget, not a per subcategory one"

    categories = []
    for budget_item in all_budget:
        if (
            budget_item.category_group_name is None
            and budget_item.category_id is not None
        ):
            categories.append(budget_item)

    await update.callback_query.edit_message_text(
        text=msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_budget_category_buttons(categories, budget_date),
        disable_web_page_preview=True,
    )
