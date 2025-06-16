import logging
import os
import traceback
from textwrap import dedent

import pytz
from lunchable import TransactionUpdateObject
from telegram import Update
from telegram.constants import ParseMode, ReactionEmoji
from telegram.ext import ContextTypes

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
from handlers.settings.schedule_rendering import get_schedule_rendering_buttons, get_schedule_rendering_text
from handlers.settings.session import handle_register_token
from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from tx_messaging import send_transaction_message

logger = logging.getLogger("handlers")


async def handle_start(update: Update, _: ContextTypes.DEFAULT_TYPE):
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

    set_expectation(update.effective_chat.id, {"expectation": EXPECTING_TOKEN, "msg_id": msg.message_id})


async def handle_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log Errors caused by Updates."""
    get_db().inc_metric("errors_handled")
    if update is None:
        logger.error("Update is None", exc_info=context.error)
        return
    if isinstance(context.error, NoLunchTokenError):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="No Lunch Money API token found. Please register a token using /start",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if os.environ.get("DEBUG"):
        error = context.error
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=dedent(
                f"""
                An error occurred:
                ```
                {"".join(traceback.format_exception(type(error), error, error.__traceback__))}
                ```
                """
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)


async def handle_generic_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    # if waiting for a token, register it
    expectation = get_expectation(update.effective_chat.id)
    if expectation and expectation["expectation"] == EXPECTING_TOKEN:
        await handle_register_token(update, context, token_msg=update.message.text, hello_msg_id=expectation["msg_id"])
        return True
    # if waiting for a time zone, persist it
    elif expectation and expectation["expectation"] == EXPECTING_TIME_ZONE:
        await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)

        # validate the time zone
        if update.message.text not in pytz.all_timezones:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"`{update.message.text}` is an invalid timezone. Please try again.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return True

        clear_expectation(update.effective_chat.id)

        # save the time zone
        get_db().update_timezone(update.effective_chat.id, update.message.text)

        settings = get_db().get_current_settings(update.effective_chat.id)
        await context.bot.edit_message_text(
            message_id=expectation["msg_id"],
            text=get_schedule_rendering_text(update.effective_chat.id),
            chat_id=update.effective_chat.id,
            reply_markup=get_schedule_rendering_buttons(settings),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return True
    elif expectation and expectation["expectation"] == RENAME_PAYEE:
        clear_expectation(update.effective_chat.id)

        # updates the transaction with the new payee
        lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
        transaction_id = int(expectation["transaction_id"])
        lunch.update_transaction(transaction_id, TransactionUpdateObject(payee=update.message.text))

        # edit the message to reflect the new payee
        updated_transaction = lunch.get_transaction(transaction_id)
        msg_id = int(expectation["msg_id"])
        await send_transaction_message(
            context=context, transaction=updated_transaction, chat_id=update.effective_chat.id, message_id=msg_id
        )

        # react to the message
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id, message_id=update.message.message_id, reaction=ReactionEmoji.WRITING_HAND
        )
        return True
    elif expectation and expectation["expectation"] == EDIT_NOTES:
        clear_expectation(update.effective_chat.id)

        # updates the transaction with the new notes
        lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
        transaction_id = int(expectation["transaction_id"])
        notes = update.message.text
        if len(notes) > 350:
            notes = notes[:350]
        lunch.update_transaction(transaction_id, TransactionUpdateObject(notes=notes))

        # edit the message to reflect the new notes
        updated_transaction = lunch.get_transaction(transaction_id)
        msg_id = int(expectation["msg_id"])
        await send_transaction_message(
            context=context, transaction=updated_transaction, chat_id=update.effective_chat.id, message_id=msg_id
        )

        settings = get_db().get_current_settings(update.effective_chat.id)
        if settings.auto_categorize_after_notes:
            await ai_categorize_transaction(transaction_id, update.effective_chat.id, context)

        # react to the message
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id, message_id=update.message.message_id, reaction=ReactionEmoji.WRITING_HAND
        )
        return True
    elif expectation and expectation["expectation"] == SET_TAGS:
        # make sure they look like tags
        message_are_tags = True
        for word in update.message.text.split(" "):
            if not word.startswith("#"):
                message_are_tags = False
                break

        if not message_are_tags:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=dedent(
                    """
                    The message should only contain words suffixed with a hashtag `#`.
                    For example: `#tag1 #tag2 #tag3`
                    """
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
            return True

        clear_expectation(update.effective_chat.id)

        # updates the transaction with the new notes
        lunch = get_lunch_client_for_chat_id(update.effective_chat.id)
        transaction_id = int(expectation["transaction_id"])

        tags_without_hashtag = [tag[1:] for tag in update.message.text.split(" ") if tag.startswith("#")]
        logger.info(f"Setting tags to transaction ({transaction_id}): {tags_without_hashtag}")
        lunch.update_transaction(transaction_id, TransactionUpdateObject(tags=tags_without_hashtag))

        # edit the message to reflect the new notes
        updated_transaction = lunch.get_transaction(transaction_id)
        msg_id = int(expectation["msg_id"])
        await send_transaction_message(
            context=context, transaction=updated_transaction, chat_id=update.effective_chat.id, message_id=msg_id
        )

        # react to the message
        await context.bot.set_message_reaction(
            chat_id=update.message.chat_id, message_id=update.message.message_id, reaction=ReactionEmoji.WRITING_HAND
        )
        return True

    return False


async def clear_cache(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    get_db().delete_transactions_for_chat(update.message.chat_id)
    await context.bot.set_message_reaction(
        chat_id=update.message.chat_id, message_id=update.message.message_id, reaction=ReactionEmoji.THUMBS_UP
    )


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generic handler for cancel buttons that simply deletes the message."""
    query = update.callback_query
    await query.answer()
    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=query.message.message_id)


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generic handler for file uploads"""
    expectation = get_expectation(update.effective_chat.id)
    logger.info(f"Expectation for chat {update.effective_chat.id}: {expectation}")
    if expectation and expectation["expectation"] == AMAZON_EXPORT:
        # React to the file attachment
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            reaction=ReactionEmoji.CLAPPING_HANDS,
        )
        await handle_amazon_export(update, context)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm not expecting a file right now.")
    return True
