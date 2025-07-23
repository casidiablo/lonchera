import re
from textwrap import dedent

from telegram import InlineKeyboardMarkup
from telegram_extensions import Update
from telegram.constants import ParseMode, ReactionEmoji
from telegram.ext import ContextTypes

from handlers.expectations import EXPECTING_TOKEN, clear_expectation, set_expectation
from lunch import get_lunch_client, get_lunch_client_for_chat_id
from persistence import Settings, get_db
from utils import Keyboard


def get_session_text(chat_id: int) -> str | None:
    settings = get_db().get_current_settings(chat_id)
    if settings is None:
        return None

    return dedent(
        f"""
        🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂 \\- *Session*

        *API token*: ||{settings.token}||
        """
    )


def get_session_buttons(settings: Settings) -> InlineKeyboardMarkup:
    kbd = Keyboard()
    kbd += ("🚪 Log out", "logout")
    kbd += ("🔄 Trigger Plaid Refresh", "triggerPlaidRefresh")
    kbd += ("Back", "settingsMenu")
    return kbd.build()


async def handle_session_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_db().get_current_settings(update.chat_id)
    await update.callback_query.edit_message_text(
        text=get_session_text(update.chat_id),
        reply_markup=get_session_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_set_token_from_button(update: Update, _: ContextTypes.DEFAULT_TYPE):
    msg = await update.callback_query.edit_message_text(text="Please provide a token to register")
    set_expectation(update.chat_id, {"expectation": EXPECTING_TOKEN, "msg_id": msg.message_id})


async def handle_logout(update: Update, _: ContextTypes.DEFAULT_TYPE):
    kbd = Keyboard()
    kbd += ("Yes, delete my token", "logout_confirm")
    kbd += ("Nevermind", "logout_cancel")
    await update.callback_query.edit_message_text(
        text=dedent(
            """
            This will remove the API token from the DB and delete all the cache associated with this chat.
            You need to delete the chat history manually by deleting the whole chat.

            You can /start again anytime you want by providing a new token.

            Do you want to proceed?
            """
        ),
        reply_markup=kbd.build(),
    )


async def handle_logout_confirm(update: Update, _: ContextTypes.DEFAULT_TYPE):
    get_db().logout(update.chat_id)
    get_db().delete_transactions_for_chat(update.chat_id)

    await update.callback_query.delete_message()
    await update.callback_query.answer(
        "Your API token has been removed, as well as the transaction history. It was a pleasure to serve you 🖖"
    )


async def handle_logout_cancel(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.delete_message()


async def handle_btn_trigger_plaid_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lunch = get_lunch_client_for_chat_id(update.message.chat_id)
    lunch.trigger_fetch_from_plaid()
    await context.bot.set_message_reaction(
        chat_id=update.message.chat_id, message_id=update.message.message_id, reaction=ReactionEmoji.HANDSHAKE
    )

    settings_text = get_session_text(update.chat_id)
    settings = get_db().get_current_settings(update.chat_id)
    await update.callback_query.edit_message_text(
        text=f"_Plaid refresh triggered_\n\n{settings_text}",
        reply_markup=get_session_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


def extract_api_token(input_string: str) -> str:
    # Define the regex pattern for the API token
    pattern = r"\b[a-f0-9]{50}\b"

    # Search for the pattern in the input string
    match = re.search(pattern, input_string)

    # If a match is found, return the matched string, otherwise return None
    return match.group(0) if match else None


async def handle_register_token(update: Update, context: ContextTypes.DEFAULT_TYPE, token_msg: str, hello_msg_id: int):
    # be forgiving and extract the token from the message, if possible
    token = extract_api_token(token_msg)

    if not token:
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text=dedent(
                """
                I couldn't find a valid token in the message you sent me.
                Please make sure you send me the token in the correct format.
                It's typically a 50-character long string of hexadecimal characters.
                """
            ),
        )
        return

    # delete the message with the token
    await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)

    try:
        # make sure the token is valid
        lunch = get_lunch_client(token)
        lunch_user = lunch.get_user()
        get_db().save_token(update.message.chat_id, token)

        clear_expectation(hello_msg_id)

        await context.bot.delete_message(chat_id=update.chat_id, message_id=hello_msg_id)

        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text=dedent(
                f"""
                🎉 🎊 Hello {lunch_user.user_name}!

                Your token was successfully stored. I will start polling for unreviewed transactions, shortly.

                These are some commands to get you started:

                /review\\_transactions - Check for unreviewed transactions now.

                Use /settings to change my behavior, like how often to poll for new transactions.

                /add\\_transaction - Adds a transaction manually
                /show\\_budget - Show the budget for the current month
                /balances - Shows the current balances in all accounts
                /pending\\_transactions - Lists all pending transactions

                Need help?
                [Join our Discord support channel](https://discord.com/channels/842337014556262411/1311765488140816484)

                (_I deleted the message with the token you provided for security purposes_)
                """
            ),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
    except Exception as e:
        # if e contains "Access token does not exist." it means
        # the token is revoked or just invalid

        if "Access token does not exist." in str(e):
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=dedent(
                    f"""
                    Failed to register token `{token}`:

                    *The token provided is invalid or has been revoked\\.*

                    Double check the token is valid or create a new one at the [Lunch Money developer console](https://my.lunchmoney.app/developers)
                    """
                ),
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True,
            )
            return
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text=dedent(
                f"""
                Failed to register token `{token}`:
                ```
                {e}
                ```

                If you need help, reach out in the
                [Discord support channel](https://discord.com/channels/842337014556262411/1311765488140816484)
                """
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
