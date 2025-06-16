import datetime
import json
import logging
import os
from textwrap import dedent

from lunchable import TransactionInsertObject
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from tx_messaging import send_transaction_message

logger = logging.getLogger("manual_tx")


async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    payload = update.effective_message.web_app_data.data
    payload = json.loads(payload)
    if payload["type"] == "manual_tx":
        try:
            await do_save_transaction(update, context, payload)
        except Exception as e:
            logger.error(f"Error saving transaction {payload}: {e}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Could not save transaction: {e}")
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=f"Unknown web app data type: {payload['type']}"
        )
        return


async def do_save_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, tx_data: dict):
    # received money must be sent as negative
    if tx_data["is_received"]:
        tx_data["amount"] = tx_data["amount"] * -1

    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)

    # get currency for this type of account
    assets = lunch.get_assets()
    account = next((asset for asset in assets if asset.id == int(tx_data["account_id"])), None)
    if account:
        tx_data["currency"] = account.currency

    logger.info(f"Transaction data: {tx_data}")

    tx_ids = lunch.insert_transactions(
        TransactionInsertObject(
            date=datetime.datetime.strptime(tx_data["date"], "%Y-%m-%d"),
            category_id=tx_data["category_id"],
            payee=tx_data["payee"],
            amount=float(tx_data["amount"]),
            currency=tx_data.get("currency", "USD").lower(),
            notes=tx_data.get("notes", None),
            status="cleared",
            asset_id=int(tx_data["account_id"]),
        )
    )

    # poll the transaction we just created
    [transaction_id] = tx_ids
    transaction = lunch.get_transaction(transaction_id)

    logger.info(f"Transaction saved: {transaction}")

    msg_id = await send_transaction_message(context, transaction=transaction, chat_id=update.effective_chat.id)
    get_db().mark_as_sent(
        transaction.id,
        update.effective_chat.id,
        msg_id,
        transaction.recurring_type,
        reviewed=True,
        plaid_id=None,  # this is a manual transaction
    )


async def handle_manual_tx(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    lunch = get_lunch_client_for_chat_id(chat_id)

    # Check for manually managed accounts
    assets = lunch.get_assets()
    manual_accounts = [asset for asset in assets if asset.type_name == "credit" or asset.type_name == "cash"]

    if not manual_accounts:
        await update.message.reply_text(
            text=dedent(
                """
            You don't have any manually managed accounts.

            Adding manual transactions is only possible for accounts that are not managed by Plaid,
            and they must be of type 'credit' or 'cash'.

            Need help?
            [Join our Discord support channel](https://discord.com/channels/842337014556262411/1311765488140816484)
            """
            ),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return

    app_name = os.getenv("FLY_APP_NAME", "lonchera")
    web_app = WebAppInfo(url=f"https://{app_name}.fly.dev/manual_tx/{chat_id}")
    await update.message.reply_text(
        text=dedent(
            """
            You can add a manual transaction by clicking the "Add manual transaction" button.

            This can only be done for accounts that are not managed by Plaid.
            """
        ),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_markup=ReplyKeyboardMarkup.from_button(
            button=KeyboardButton(text="Add manual transaction", web_app=web_app), one_time_keyboard=True
        ),
    )
