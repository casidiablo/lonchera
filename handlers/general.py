import logging
import os
import traceback
from textwrap import dedent

import pytz
from lunchable import TransactionUpdateObject
from telegram.constants import ParseMode, ReactionEmoji
from telegram.ext import ContextTypes

from constants import NOTES_MAX_LENGTH
from errors import NoLunchTokenError
from handlers.amz import handle_amazon_export
from handlers.categorization import ai_categorize_transaction
from handlers.expectations import (
    AMAZON_EXPORT,
    EDIT_NOTES,
    EXPECTING_TIME_ZONE,
    EXPECTING_TOKEN,
    RENAME_PAYEE,
    SET_TAGS,
    clear_expectation,
    get_expectation,
    set_expectation,
)
from handlers.lunch_money_agent import handle_generic_message_with_ai
from handlers.settings.schedule_rendering import get_schedule_rendering_buttons, get_schedule_rendering_text
from handlers.settings.session import handle_register_token
from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from telegram_extensions import Update
from tx_messaging import send_transaction_message

logger = logging.getLogger("handlers")


async def handle_start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return

    msg = await update.message.reply_text(
        text=dedent(
            """
            Welcome to Lonchera! A Telegram bot that helps you stay on top of your Lunch Money transactions.
            To start, please send me your *Lunch Money API token*

            If you are not a Lunch Money user already, you can use my referral link to create an account:

            https://lunchmoney.app/?refer=g5cotlcw

            It's an amazing tool to track your finances. Do give them a try!
            """
        ),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )

    set_expectation(update.chat_id, {"expectation": EXPECTING_TOKEN, "msg_id": str(msg.message_id)})


async def handle_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log Errors caused by Updates."""
    get_db().inc_metric("errors_handled")
    if update is None:
        logger.error("Update is None", exc_info=context.error)
        return

    if not update.effective_chat:
        logger.error("No effective chat in update", exc_info=context.error)
        return

    if isinstance(context.error, NoLunchTokenError):
        await context.bot.send_message(
            chat_id=update.chat_id,
            text="No Lunch Money API token found. Please register a token using /start",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if os.environ.get("DEBUG"):
        error = context.error
        if error:
            error_traceback = traceback.format_exception(type(error), error, error.__traceback__)
        else:
            error_traceback = ["Unknown error"]
        await context.bot.send_message(
            chat_id=update.chat_id,
            text=dedent(
                f"""
                An error occurred:
                ```
                {"".join(error_traceback)}
                ```
                """
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)


async def handle_generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_chat or not update.message or not update.message.text:
        return False

    chat_id = update.chat_id
    # if waiting for a token, register it
    expectation = get_expectation(chat_id)
    if expectation and expectation["expectation"] == EXPECTING_TOKEN:
        msg_id = int(expectation["msg_id"]) if isinstance(expectation["msg_id"], str) else expectation["msg_id"]
        await handle_register_token(update, context, token_msg=update.message.text, hello_msg_id=msg_id)
        return True

    # if waiting for a time zone, persist it
    if expectation and expectation["expectation"] == EXPECTING_TIME_ZONE:
        return await handle_timezone_setting(update, context, expectation)

    settings = get_db().get_current_settings(chat_id)
    if settings is not None and settings.ai_agent:
        # If AI Agent is enabled, we just pass the message to the AI handler
        await handle_generic_message_with_ai(update, context)
        return True

    # These are disabled when AI Agent is enabled
    if expectation and expectation["expectation"] == RENAME_PAYEE:
        return await handle_rename_payee(update, context, expectation)
    elif expectation and expectation["expectation"] == EDIT_NOTES:
        return await handle_edit_notes(update, context, expectation)
    elif expectation and expectation["expectation"] == SET_TAGS:
        return await handle_set_tags(update, context, expectation)

    return False


async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    get_db().delete_transactions_for_chat(update.chat_id)
    await context.bot.set_message_reaction(
        chat_id=update.chat_id, message_id=update.message.message_id, reaction=ReactionEmoji.THUMBS_UP
    )


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generic handler for cancel buttons that simply deletes the message."""
    query = update.callback_query
    if not query or not query.message or not update.effective_chat:
        return

    await context.bot.delete_message(chat_id=update.chat_id, message_id=query.message.message_id)


async def handle_rename_payee(update: Update, context: ContextTypes.DEFAULT_TYPE, expectation: dict) -> bool:
    """Handle renaming a payee for a transaction."""
    if not update.effective_chat or not update.message or not update.message.text:
        return False

    clear_expectation(update.chat_id)

    # updates the transaction with the new payee
    lunch = get_lunch_client_for_chat_id(update.chat_id)
    transaction_id = int(expectation["transaction_id"])
    lunch.update_transaction(transaction_id, TransactionUpdateObject(payee=update.message.text))  # type: ignore

    # edit the message to reflect the new payee
    updated_transaction = lunch.get_transaction(transaction_id)
    msg_id = int(expectation["msg_id"])
    await send_transaction_message(
        context=context, transaction=updated_transaction, chat_id=update.chat_id, message_id=msg_id
    )

    # react to the message
    await context.bot.set_message_reaction(
        chat_id=update.chat_id, message_id=update.message.message_id, reaction=ReactionEmoji.WRITING_HAND
    )
    return True


async def handle_edit_notes(update: Update, context: ContextTypes.DEFAULT_TYPE, expectation: dict) -> bool:
    """Handle editing notes for a transaction."""
    if not update.effective_chat or not update.message or not update.message.text:
        return False

    clear_expectation(update.chat_id)

    # updates the transaction with the new notes
    lunch = get_lunch_client_for_chat_id(update.chat_id)
    transaction_id = int(expectation["transaction_id"])
    notes = update.message.text
    if len(notes) > NOTES_MAX_LENGTH:
        notes = notes[:NOTES_MAX_LENGTH]
    lunch.update_transaction(transaction_id, TransactionUpdateObject(notes=notes))  # type: ignore

    # edit the message to reflect the new notes
    updated_transaction = lunch.get_transaction(transaction_id)
    msg_id = int(expectation["msg_id"])
    await send_transaction_message(
        context=context, transaction=updated_transaction, chat_id=update.chat_id, message_id=msg_id
    )

    settings = get_db().get_current_settings(update.chat_id)
    if settings and settings.auto_categorize_after_notes:
        await ai_categorize_transaction(transaction_id, update.chat_id, context)

    # react to the message
    await context.bot.set_message_reaction(
        chat_id=update.chat_id, message_id=update.message.message_id, reaction=ReactionEmoji.WRITING_HAND
    )
    return True


async def handle_timezone_setting(update: Update, context: ContextTypes.DEFAULT_TYPE, expectation: dict) -> bool:
    """Handle setting the timezone for a user."""
    if not update.message or not update.message.text or not update.effective_chat:
        return False

    await context.bot.delete_message(chat_id=update.chat_id, message_id=update.message.message_id)

    # validate the time zone
    if update.message.text not in pytz.all_timezones:
        await context.bot.send_message(
            chat_id=update.chat_id,
            text=f"`{update.message.text}` is an invalid timezone. Please try again.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return True

    clear_expectation(update.chat_id)

    # save the time zone
    get_db().update_timezone(update.chat_id, update.message.text)

    settings = get_db().get_current_settings(update.chat_id)
    schedule_text = get_schedule_rendering_text(update.chat_id)
    if schedule_text:
        await context.bot.edit_message_text(
            message_id=int(expectation["msg_id"]),
            text=schedule_text,
            chat_id=update.chat_id,
            reply_markup=get_schedule_rendering_buttons(settings),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    return True


async def handle_set_tags(update: Update, context: ContextTypes.DEFAULT_TYPE, expectation: dict) -> bool:
    """Handle setting tags for a transaction."""
    if not update.message or not update.message.text or not update.effective_chat:
        return False

    # make sure they look like tags
    message_are_tags = True
    for word in update.message.text.split(" "):
        if not word.startswith("#"):
            message_are_tags = False
            break

    if not message_are_tags:
        await context.bot.send_message(
            chat_id=update.chat_id,
            text=dedent(
                """
                The message should only contain words suffixed with a hashtag `#`.
                For example: `#tag1 #tag2 #tag3`
                """
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
        return True

    clear_expectation(update.chat_id)

    # updates the transaction with the new notes
    lunch = get_lunch_client_for_chat_id(update.chat_id)
    transaction_id = int(expectation["transaction_id"])

    tags_without_hashtag = [tag[1:] for tag in update.message.text.split(" ") if tag.startswith("#")]
    logger.info(f"Setting tags to transaction ({transaction_id}): {tags_without_hashtag}")
    lunch.update_transaction(transaction_id, TransactionUpdateObject(tags=tags_without_hashtag))  # type: ignore

    # edit the message to reflect the new notes
    updated_transaction = lunch.get_transaction(transaction_id)
    msg_id = int(expectation["msg_id"])
    await send_transaction_message(
        context=context, transaction=updated_transaction, chat_id=update.chat_id, message_id=msg_id
    )

    # react to the message
    await context.bot.set_message_reaction(
        chat_id=update.chat_id, message_id=update.message.message_id, reaction=ReactionEmoji.WRITING_HAND
    )
    return True


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generic handler for file uploads"""
    if not update.effective_chat or not update.message:
        return False

    expectation = get_expectation(update.chat_id)
    logger.info(f"Expectation for chat {update.chat_id}: {expectation}")
    if expectation and expectation["expectation"] == AMAZON_EXPORT:
        # React to the file attachment
        await context.bot.set_message_reaction(
            chat_id=update.chat_id, message_id=update.message.message_id, reaction=ReactionEmoji.CLAPPING_HANDS
        )
        await handle_amazon_export(update, context)
    else:
        await context.bot.send_message(chat_id=update.chat_id, text="I'm not expecting a file right now.")
    return True
