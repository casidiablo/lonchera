import logging
from textwrap import dedent
from lunchable import TransactionInsertObject
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    Application,
)
from telegram.constants import ParseMode
import datetime

from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from tx_messaging import send_transaction_message
from utils import (
    CONVERSATION_MSG_ID,
    Keyboard,
    build_conversation_handler,
    ensure_token,
    make_tag,
)

# Conversation states
(
    DATE,
    CATEGORY_GROUP,
    CATEGORY,
    PAYEE,
    AMOUNT,
    CURRENCY,
    NOTES,
    ACCOUNT,
    CONFIRM,
) = range(9)

# Define callback data
CONTINUE = "continue"
TODAY, YESTERDAY = "today", "yesterday"
CREDIT, DEBIT, CASH = "credit", "debit", "cash"
SKIP = "skip"
SPENT_MONEY = "spent"
RECEIVED_MONEY = "received"
CANCEL = "cancel"


logger = logging.getLogger("manual_tx")


def get_transaction_state_message(
    context: ContextTypes.DEFAULT_TYPE, extra_info: str = ""
):
    date = context.user_data.get("date", "N/A")
    category = context.user_data.get("category", None)
    if category is None:
        category = "None selected"
    else:
        category = make_tag(category)
    payee = context.user_data.get("payee", "N/A")
    amount = context.user_data.get("amount", "0.0")
    amount = float(amount)
    currency = context.user_data.get("currency", "USD")
    notes = context.user_data.get("notes", "N/A")
    account = context.user_data.get("account", "N/A")

    result = dedent(
        f"""
        *Manual transaction form*

        *Account*: {account}
        *Amount*: `{amount:,.2f}` {currency.upper()}
        *Date*: {date}
        *Category*: {category}
        *Payee*: {payee}
        *Notes*: {notes}
        """
    )

    if extra_info:
        result += f"\n\n{extra_info}"

    return result


async def start_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ensure_token(update)

    msg = await update.message.reply_text(
        text=dedent(
            """
            *Add manual transaction*

            This wizard will allow you to add a transaction manually.

            This can only be done for accounts that are not managed by Plaid.

            It requires inputing the date, payee name and amount of the transaction.

            Alternatively, you can also specify the category, and notes.
            """
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard().build_from(
            ("Continue", CONTINUE),
            ("Cancel", CANCEL),
        ),
    )
    context.user_data.clear()
    return msg.message_id


async def prompt_for_date(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    error_msg: str = "",
):
    message = "Please enter the date in the format `YYYY-MM-DD` or select an option:"

    if error_msg != "":
        message = f"{error_msg}\n\n{message}"

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data[CONVERSATION_MSG_ID],
        text=get_transaction_state_message(
            context,
            extra_info=message,
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard().build_from(
            ("Today", TODAY),
            ("Yesterday", YESTERDAY),
            ("Cancel", CANCEL),
        ),
    )


async def capture_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if query:
        await query.answer()

        if query.data in [TODAY, YESTERDAY]:
            date = (
                datetime.date.today()
                if query.data == TODAY
                else datetime.date.today() - datetime.timedelta(days=1)
            )
            context.user_data["date"] = date.strftime("%Y-%m-%d")
            return True
        else:
            raise ValueError(f"Invalid button pressed: {query.data}")
    else:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
        )
        try:
            # validate date to make sure it's in the right format
            context.user_data["date"] = datetime.datetime.strptime(
                update.message.text, "%Y-%m-%d"
            )
            return True
        except ValueError:
            await prompt_for_date(
                update,
                context,
                error_msg=dedent(
                    f"""
                    Invalid date (`{update.message.text}`).
                    """
                ),
            )
            return False


async def prompt_for_category_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    categories = lunch.get_categories()

    kbd = Keyboard()
    for category in categories:
        if category.group_id is None:
            kbd += (category.name, f"subcategory_{category.id}")

    kbd += ("Cancel", CANCEL)

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data[CONVERSATION_MSG_ID],
        text=get_transaction_state_message(context, "Please select a category:"),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kbd.build(),
    )


async def capture_category_group(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    query = update.callback_query
    await query.answer()

    category_group_id = query.data.split("_")[1]
    context.user_data["category_group"] = category_group_id
    return True


async def prompt_for_subcategory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    subcategories = lunch.get_categories()
    kbd = Keyboard()
    for subcategory in subcategories:
        if str(subcategory.group_id) == str(context.user_data["category_group"]):
            kbd += (subcategory.name, f"subcategory_{subcategory.id}")

    kbd += ("Cancel", CANCEL)

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data[CONVERSATION_MSG_ID],
        text=get_transaction_state_message(context, "Please select a subcategory:"),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kbd.build(),
    )


async def capture_subcategory(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    query = update.callback_query
    await query.answer()

    category_id = query.data.split("_")[1]
    context.user_data["category_id"] = category_id

    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    category = lunch.get_category(category_id)
    context.user_data["category"] = category.name
    return True


async def prompt_for_payee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data[CONVERSATION_MSG_ID],
        text=get_transaction_state_message(
            context, "Enter the name of the merchant or payee:"
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard.build_from(("Cancel", CANCEL)),
    )


async def capture_payee(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    context.user_data["payee"] = update.message.text
    await context.bot.delete_message(
        chat_id=update.effective_chat.id, message_id=update.message.message_id
    )
    return True


async def prompt_for_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    error_msg: str = "",
):
    currency = context.user_data.get("currency", "USD")
    account = context.user_data["account"]
    message = f"The currency for *{account}* is `{currency.upper()}`\n\nEnter the transaction amount:"
    if error_msg != "":
        message = f"{error_msg}\n\n{message}"

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data[CONVERSATION_MSG_ID],
        text=get_transaction_state_message(
            context,
            message,
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard.build_from(("Cancel", CANCEL)),
    )


async def capture_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    amount = update.message.text
    if " " in amount:
        amount, currency = amount.split(" ")

        # make sure currency is a three letters string
        if len(currency) != 3:
            await prompt_for_amount(
                update,
                context,
                f"Invalid currency (`{currency}`). It must be a three letters string (e.g. `USD`).",
            )

            await context.bot.delete_message(
                chat_id=update.effective_chat.id, message_id=update.message.message_id
            )
            return False

        context.user_data["currency"] = currency.upper()

    # validate amount to make sure it's a number
    try:
        float(amount)
    except ValueError:
        await prompt_for_amount(
            update,
            context,
            f"Invalid amount (`{amount}`). It must be a number (e.g. `42.5`).",
        )

        await context.bot.delete_message(
            chat_id=update.effective_chat.id, message_id=update.message.message_id
        )
        context.user_data["currency"] = None
        await context.bot.delete_message(
            chat_id=update.effective_chat.id, message_id=update.message.message_id
        )
        return False

    context.user_data["amount"] = amount

    await context.bot.delete_message(
        chat_id=update.effective_chat.id, message_id=update.message.message_id
    )
    return True


async def prompt_for_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data[CONVERSATION_MSG_ID],
        text=get_transaction_state_message(
            context,
            "Enter any notes (optional):",
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard.build_from(("Skip", SKIP), ("Cancel", CANCEL)),
    )


async def capture_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if query:
        # assume it was a skip button
        await query.answer()
        return True

    context.user_data["notes"] = update.message.text
    await context.bot.delete_message(
        chat_id=update.effective_chat.id, message_id=update.message.message_id
    )
    return True


async def prompt_for_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # get all the assets accounts
    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    assets = lunch.get_assets()

    only_accounts = [
        asset
        for asset in assets
        if asset.type_name == "credit" or asset.type_name == "cash"
    ]

    kbd = Keyboard()
    for acct in only_accounts:
        kbd += (f"{acct.display_name or acct.name}", f"account_{acct.id}")
    kbd += ("Cancel", CANCEL)

    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data[CONVERSATION_MSG_ID],
        text=get_transaction_state_message(
            context,
            "Select the account:",
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kbd.build(),
    )


async def capture_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query

    account_id = query.data.split("_")[1]
    context.user_data["account_id"] = account_id

    # get asset name
    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    assets = lunch.get_assets()
    account = next((asset for asset in assets if asset.id == int(account_id)), None)

    if account:
        context.user_data["account"] = account.display_name or account.name

    context.user_data["currency"] = account.currency

    await query.answer()
    return True


async def confirm_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data[CONVERSATION_MSG_ID],
        text=get_transaction_state_message(context),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard.build_from(
            ("I spent this money", SPENT_MONEY),
            ("I received this money", RECEIVED_MONEY),
            ("Cancel", CANCEL),
        ),
    )


async def save_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data == RECEIVED_MONEY:
        context.user_data["amount"] = "-" + context.user_data["amount"]

    transaction_data = context.user_data
    logger.info(f"Transaction data: {transaction_data}")

    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
    tx_ids = lunch.insert_transactions(
        TransactionInsertObject(
            date=datetime.datetime.strptime(transaction_data["date"], "%Y-%m-%d"),
            category_id=transaction_data["category_id"],
            payee=transaction_data["payee"],
            amount=float(transaction_data["amount"]),
            currency=transaction_data.get("currency", "USD").lower(),
            notes=transaction_data.get("notes", None),
            status="cleared",
            asset_id=int(transaction_data["account_id"]),
        )
    )

    # poll the transaction we just created
    [transaction_id] = tx_ids
    transaction = lunch.get_transaction(transaction_id)

    await query.answer("Transaction saved successfully!", show_alert=True)
    logger.info(f"Transaction saved: {transaction}")

    msg_id = await send_transaction_message(
        context,
        transaction=transaction,
        chat_id=update.effective_chat.id,
        message_id=context.user_data[CONVERSATION_MSG_ID],
    )
    get_db().mark_as_sent(
        transaction.id,
        update.effective_chat.id,
        msg_id,
        transaction.recurring_type,
        reviewed=True,
        plaid_id=None,  # this is a manual transaction
    )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.delete_message(
        chat_id=update.effective_chat.id,
        message_id=context.user_data[CONVERSATION_MSG_ID],
    )
    context.user_data.clear()
    return ConversationHandler.END


def setup_manual_tx_handler(app: Application, config: dict):
    steps = [
        (prompt_for_account, capture_account),
        (prompt_for_amount, capture_amount),
        (prompt_for_date, capture_date),
        (prompt_for_payee, capture_payee),
    ]

    if config["PROMPT_FOR_CATEGORIES"]:
        steps.extend(
            [
                (prompt_for_category_group, capture_category_group),
                (prompt_for_subcategory, capture_subcategory),
            ]
        )

    if config["PROMPT_FOR_NOTES"]:
        steps.append((prompt_for_notes, capture_notes))

    steps.append((confirm_transaction, save_transaction))

    transaction_handler = build_conversation_handler(
        start_step=start_transaction,
        steps=steps,
        cancel_handler=CallbackQueryHandler(cancel, pattern=CANCEL),
    )

    app.add_handler(transaction_handler)
