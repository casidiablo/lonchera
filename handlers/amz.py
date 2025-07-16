import logging
import os
import random
import shutil
import tempfile
import zipfile
from datetime import datetime
from textwrap import dedent

from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

# Constants
MAX_PREVIEW_UPDATES = 3

from amazon import get_amazon_transactions_summary, process_amazon_transactions
from handlers.expectations import AMAZON_EXPORT, clear_expectation, set_expectation
from lunch import get_lunch_money_token_for_chat_id
from persistence import get_db
from utils import Keyboard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("amz")


async def handle_amazon_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Handling /amazon_sync command")
    msg = await update.message.reply_text(
        text=dedent(
            """
            This feature allows you to synchronize your Amazon transactions. It will try
            to match the Amazon transactions you provide with the transactions in your Lunch Money account,
            and set notes and categories for the transactions that match.

            To start, please upload the Amazon transaction history file, which you can get
            by following these steps:

            1. Go to the [Amazon](https://www.amazon.com/) website and log in.
            2. Click on the ["Account & Lists"](https://www.amazon.com/gp/css/homepage.html) dropdown menu.
            3. Scroll down to the "Manage your data" section and click on
            ["Request your data"](https://www.amazon.com/hz/privacy-central/data-requests/preview.html).
            5. Select "Your Orders" and click "Submit Request".
            6. Go to your email inbox and confirm.
            7. Wait an hour or so for them to email you a link to download your data.
            8. Download the zip file and upload it here.

            You can upload the whole zip file or just the CSV with the purchase history, which is found in the
            `Retail.OrderHistory.1/` folder.

            *Note*: _this is a very experimental feature and may not work as expected.
            It is also a little brittle because the data provided by Amazon does not include gift card
            transactions data, or information when you pay part with your credit card and part with a balance._

            *IMPORTANT*: for this to work:

            1. The Lunch Money transactions' payee must be exactly "Amazon"
            2. The transaction MUST not have a note already
            """
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard.build_from(("Nevermind", "cancel")),
        disable_web_page_preview=True,
    )

    set_expectation(update.message.chat_id, {"expectation": AMAZON_EXPORT, "msg_id": str(msg.id)})


def get_process_amazon_tx_buttons(ai_categorization_enabled: bool) -> InlineKeyboardMarkup:
    kbd = Keyboard()
    if ai_categorization_enabled:
        kbd += ("Disable AI categorization", f"update_amz_settings_{not ai_categorization_enabled}")
    else:
        kbd += ("Enable AI categorization", f"update_amz_settings_{not ai_categorization_enabled}")

    kbd += ("Preview", "preview_process_amazon_transactions")
    kbd += ("Process", "process_amazon_transactions")
    kbd += ("Cancel", "cancel")

    return kbd.build()


async def pre_processing_amazon_transactions(
    update: Update, context: ContextTypes.DEFAULT_TYPE, msg_id: int | None = None
):
    export_file = context.user_data.get("amazon_export_file")
    ai_categorization_enabled = context.user_data.get("ai_categorization_enabled", True)

    summary = get_amazon_transactions_summary(export_file)
    if ai_categorization_enabled:
        ai_categorization_enabled_text = "AI categorization is 🟢 ᴏɴ."
    else:
        ai_categorization_enabled_text = "AI categorization is 🔴 ᴏꜰꜰ."

    text = dedent(
        f"""
        I got the Amazon export. It contains {summary["total_transactions"]} transactions from {summary["start_date"]} to {summary["end_date"]}.

        Since this is a time-intensive process, I will only process transactions from the last 60 days.

        I can also do a dry run to show you what transactions will be updated, without actually updating them.

        AI categorization will ask an LLM what category best describes the transaction based on what items were purchased.

        {ai_categorization_enabled_text}
        """
    )

    if msg_id:
        await context.bot.edit_message_text(
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_process_amazon_tx_buttons(ai_categorization_enabled),
            chat_id=update.effective_chat.id,
            message_id=msg_id,
        )
    else:
        await update.message.reply_text(
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_process_amazon_tx_buttons(ai_categorization_enabled=False),
        )


async def extract_amazon_csv_file(update: Update, file_name: str, downloads_path: str) -> str | None:
    """Extract the Amazon CSV file from an upload.

    Args:
        update: The update object
        file_name: The name of the uploaded file
        downloads_path: Path to save downloaded files

    Returns:
        The path to the extracted CSV file or None if extraction failed
    """
    current_time_path = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file = await update.message.document.get_file()
    os.makedirs(downloads_path, exist_ok=True)
    download_path = f"{downloads_path}/{current_time_path}_{update.effective_chat.id}_{file_name}"
    logger.info(f"Downloading file to {download_path}")
    await file.download_to_drive(custom_path=download_path)

    # if zip, extract and find the csv file inside the Retail.OrderHistory.1/ folder
    if file_name.lower().endswith(".zip"):
        # Create a temporary directory for extracted CSV only
        temp_dir = tempfile.mkdtemp(dir=downloads_path)
        target_csv_path = os.path.join(temp_dir, "amazon_orders.csv")
        logger.info(f"Looking for CSV in zip file, will extract to {target_csv_path}")

        try:
            # Open the zip file and process one file at a time
            with zipfile.ZipFile(download_path, "r") as zip_ref:
                # Process zip contents without extracting everything
                csv_found = False
                for info in zip_ref.infolist():
                    # Look only for CSV files in the right directory
                    if info.filename.lower().endswith(".csv") and "Retail.OrderHistory.1" in info.filename:
                        logger.info(f"Found CSV file: {info.filename}")
                        # Extract just this one file
                        with zip_ref.open(info) as source, open(target_csv_path, "wb") as target:
                            # Copy in chunks to minimize memory usage
                            shutil.copyfileobj(source, target, 65536)  # 64KB chunks
                        csv_found = True
                        break

                if not csv_found:
                    await update.message.reply_text("Could not find the CSV file in the Retail.OrderHistory.1/ folder.")
                    # Clean up
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    os.remove(download_path)
                    return None

            # Remove the zip file to free up space
            os.remove(download_path)
            return target_csv_path

        except Exception as e:
            logger.error(f"Error extracting CSV from zip: {e}")
            # Clean up on error
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            if os.path.exists(download_path):
                os.remove(download_path)
            await update.message.reply_text(f"Error extracting CSV from zip file: {e}")
            return None

    return download_path


async def handle_amazon_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document is None:
        await update.message.reply_text(
            "Please upload the Amazon transaction history file (either the whole zip file or the CSV file)"
        )
        return

    file_name = update.message.document.file_name
    # make sure it's a zip or csv file
    if not file_name.lower().endswith(".zip") and not file_name.lower().endswith(".csv"):
        ext = file_name.split(".")[-1]
        await update.message.reply_text(f"Did not recognize the file format ({ext}). Please upload a zip or csv file.")
        return

    # download and extract file
    downloads_path = os.getenv("DOWNLOADS_PATH", f"/tmp/{random.randint(1000, 9999)}")
    download_path = await extract_amazon_csv_file(update, file_name, downloads_path)
    if download_path is None:
        return

    # Increment the metric for Amazon export uploads
    get_db().inc_metric("amazon_export_uploads")

    # get summary of the csv file
    try:
        context.user_data["amazon_export_file"] = download_path
        context.user_data["ai_categorization_enabled"] = True
        await pre_processing_amazon_transactions(update, context)

        # clear expectation and delete that initial message
        prev = clear_expectation(update.message.chat_id)
        if prev and prev["msg_id"]:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=int(prev["msg_id"]))
    except Exception as e:
        await update.message.reply_text(f"Error processing the file: {e}")


async def handle_update_amz_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ai_categorization_enabled = query.data.split("_")[-1] == "True"
    export_file = context.user_data.get("amazon_export_file")
    msg_id = query.message.message_id

    context.user_data["ai_categorization_enabled"] = ai_categorization_enabled

    if export_file is None:
        await query.edit_message_text("Seems like I forgot the Amazon export file. Please start over: /amazon_sync")
        return

    await pre_processing_amazon_transactions(update, context, msg_id)


async def handle_preview_process_amazon_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    export_file = context.user_data.get("amazon_export_file")
    ai_categorization_enabled = context.user_data.get("ai_categorization_enabled", False)

    if export_file is None:
        await query.edit_message_text("Seems like I forgot the Amazon export file. Please start over: /amazon_sync")
        return

    # Increment the metric for Amazon autocategorization runs
    get_db().inc_metric("amazon_autocategorization_runs")

    try:
        await query.edit_message_text("⏳ Processing transactions. This might take a while. Be patient.")

        lunch_money_token = get_lunch_money_token_for_chat_id(update.effective_chat.id)

        result = process_amazon_transactions(
            file_path=export_file,
            days_back=60,
            dry_run=True,
            allow_days=5,
            auto_categorize=ai_categorization_enabled,
            lunch_money_token=lunch_money_token,
        )

        processed_transactions = result["processed_transactions"]
        found_transactions = result["found_transactions"]
        will_update_transactions = result["will_update_transactions"]

        update_details = ""
        updates = result["updates"][:MAX_PREVIEW_UPDATES]
        if updates:
            first_n = MAX_PREVIEW_UPDATES if len(updates) >= MAX_PREVIEW_UPDATES else len(updates)
            update_details = f"Here are the first {first_n} transactions that will be updated:\n\n"
            update_details += "\n".join(
                [
                    f"- *Date*: {update['date']}\n"
                    f"  *Amount*: `{update['amount']}` {update['currency'].upper()}\n"
                    f"  *Notes*: {update['notes']}\n"
                    + (
                        f"  *Category*: {update['previous_category_name']} `=>` {update['new_category_name']}\n"
                        if update["previous_category_name"] != update["new_category_name"]
                        else ""
                    )
                    for update in updates
                ]
            )

            more_updates = will_update_transactions - 3
            if more_updates > 0:
                update_details += f"\n\nAnd {more_updates} more transactions will be updated."

        will_update_text = ""
        if will_update_transactions > 0:
            will_update_text = f"Will update {will_update_transactions} transactions."
        elif found_transactions == 0:
            will_update_text = "No transactions will be updated since none were found in the Amazon export."
        else:
            will_update_text = "No transactions will be updated since all seem to have notes."

        message = dedent(
            f"""
Processed {processed_transactions} Amazon transactions from Lunch Money,
{found_transactions} of those were found in the Amazon export file.
{will_update_text}

{update_details}
"""
        )

        kbd = Keyboard()
        if will_update_transactions > 0:
            kbd += ("Proceed", "process_amazon_transactions")
            # just a hack to go back to the previous menu
            kbd += ("Back to settings", "update_amz_settings_True")
            kbd += ("Cancel", "cancel")
        else:
            kbd += ("Close", "cancel")

        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            message_id=query.message.message_id,
            reply_markup=kbd.build(),
        )
    except Exception as e:
        await query.edit_message_text(f"Error processing Amazon transactions: {e}")


async def handle_process_amazon_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    export_file = context.user_data.get("amazon_export_file")
    ai_categorization_enabled = context.user_data.get("ai_categorization_enabled", False)

    if export_file is None:
        await query.edit_message_text("Seems like I forgot the Amazon export file. Please start over: /amazon_sync")
        return

    # Increment the metric for Amazon autocategorization runs
    get_db().inc_metric("amazon_autocategorization_runs")

    try:
        msg = await query.edit_message_text("⏳ Processing transactions. This might take a while. Be patient.")

        lunch_money_token = get_lunch_money_token_for_chat_id(update.effective_chat.id)

        result = process_amazon_transactions(
            file_path=export_file,
            days_back=60,
            dry_run=False,
            allow_days=5,
            auto_categorize=ai_categorization_enabled,
            lunch_money_token=lunch_money_token,
        )

        processed_transactions = result["processed_transactions"]
        found_transactions = result["found_transactions"]
        will_update_transactions = result["will_update_transactions"]

        not_updated = found_transactions - will_update_transactions
        not_updated_text = ""
        if not_updated > 0:
            not_updated_text = f"{not_updated} transactions were not updated because they already had notes."

        message = dedent(
            f"""
            Found {processed_transactions} Amazon transactions in Lunch Money,
            out of which {found_transactions} were found in the Amazon export file,
            and will update {will_update_transactions} in total.

            {not_updated_text}
            """
        )

        await context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode=ParseMode.MARKDOWN)
        await msg.delete()
    except Exception as e:
        await query.edit_message_text(f"Error processing Amazon transactions: {e}")
    finally:
        # Clean up extracted files
        if export_file and os.path.exists(export_file):
            try:
                # Remove the file
                os.remove(export_file)
                # If it's in a temp directory, try to remove the directory too
                parent_dir = os.path.dirname(export_file)
                if os.path.basename(parent_dir).startswith("tmp") and len(os.listdir(parent_dir)) == 0:
                    shutil.rmtree(parent_dir, ignore_errors=True)
            except Exception as e:
                logger.error(f"Error cleaning up temporary files: {e}")
