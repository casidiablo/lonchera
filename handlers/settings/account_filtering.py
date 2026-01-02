import logging
from textwrap import dedent

from telegram import InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from telegram_extensions import Update
from utils import Keyboard, get_emoji_for_account_type

logger = logging.getLogger("account_filtering")


def get_account_filtering_text(chat_id: int) -> str | None:
    """Render menu with account list and ignore status."""
    try:
        # Get user's accounts from Lunch Money API
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        accounts = lunch_client.get_accounts()

        # Get ignored accounts from database
        ignored_accounts = get_db().get_ignored_accounts_list(chat_id)
        ignored_set = set(ignored_accounts)

        if not accounts:
            return dedent(
                """
                🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂 \\- *Account Filtering*

                ❌ No accounts available to configure\\.

                Please ensure your Lunch Money account has connected accounts\\.
                """
            )

        # Count ignored accounts
        ignored_count = len([acc for acc in accounts if acc.id in ignored_set])
        total_count = len(accounts)

        # Build account list text
        account_lines = []
        for account in accounts:
            emoji = get_emoji_for_account_type(account.type or "other")
            status_icon = "🔕" if account.id in ignored_set else "🔔"
            status_text = "Ignored" if account.id in ignored_set else "Active"

            # Escape special characters for Markdown V2
            account_name = (
                account.name.replace("_", "\\_")
                .replace("*", "\\*")
                .replace("[", "\\[")
                .replace("]", "\\]")
                .replace("(", "\\(")
                .replace(")", "\\)")
                .replace("~", "\\~")
                .replace("`", "\\`")
                .replace(">", "\\>")
                .replace("#", "\\#")
                .replace("+", "\\+")
                .replace("-", "\\-")
                .replace("=", "\\=")
                .replace("|", "\\|")
                .replace("{", "\\{")
                .replace("}", "\\}")
                .replace(".", "\\.")
                .replace("!", "\\!")
            )

            account_lines.append(f"{emoji} *{account_name}*: {status_icon} {status_text}")

        accounts_text = "\n".join(account_lines)

        return dedent(
            f"""
            🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂 \\- *Account Filtering*

            Configure which accounts should be ignored for transaction notifications\\.

            📊 *Summary*: {ignored_count} of {total_count} accounts ignored

            {accounts_text}

            Tap an account to toggle its notification status\\.
            """
        )

    except Exception:
        logger.exception("Error fetching accounts for filtering menu")
        return dedent(
            """
            🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂 \\- *Account Filtering*

            ❌ Error loading accounts\\.

            Please check your Lunch Money connection and try again\\.
            """
        )


def get_account_filtering_buttons(chat_id: int) -> InlineKeyboardMarkup:
    """Create toggle buttons for each account."""
    kbd = Keyboard()

    try:
        # Get user's accounts from Lunch Money API
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        accounts = lunch_client.get_accounts()

        # Get ignored accounts from database
        ignored_accounts = get_db().get_ignored_accounts_list(chat_id)
        ignored_set = set(ignored_accounts)

        # Create toggle buttons for each account
        for account in accounts:
            status_icon = "🔕" if account.id in ignored_set else "🔔"
            button_text = f"{status_icon} {account.name}"
            callback_data = f"toggleAccountIgnore_{account.id}"
            kbd += (button_text, callback_data)

        # Add back button
        kbd += ("Back", "transactionsHandlingSettings")

        return kbd.build(columns=1)

    except Exception:
        logger.exception("Error creating account filtering buttons")
        # Return minimal keyboard with just back button on error
        kbd += ("Back", "transactionsHandlingSettings")
        return kbd.build()


async def handle_account_filtering_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu handler for account filtering settings."""
    settings_text = get_account_filtering_text(update.chat_id)
    if settings_text:
        await update.safe_edit_message_text(
            text=settings_text,
            reply_markup=get_account_filtering_buttons(update.chat_id),
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def handle_btn_toggle_account_ignore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle handler for individual accounts."""
    try:
        # Extract account ID from callback data
        callback_data = update.callback_query.data
        if not callback_data.startswith("toggleAccountIgnore_"):
            logger.error(f"Invalid callback data: {callback_data}")
            return

        account_id_str = callback_data.replace("toggleAccountIgnore_", "")
        try:
            account_id = int(account_id_str)
        except ValueError:
            logger.exception(f"Invalid account ID in callback data: {account_id_str}")
            return

        # Get current ignored accounts
        ignored_accounts = get_db().get_ignored_accounts_list(update.chat_id)

        # Toggle the account's ignore status
        if account_id in ignored_accounts:
            # Remove from ignored list
            ignored_accounts.remove(account_id)
        else:
            # Add to ignored list
            ignored_accounts.append(account_id)

        # Update database
        get_db().update_ignored_accounts(update.chat_id, ignored_accounts)

        # Update UI to reflect changes
        settings_text = get_account_filtering_text(update.chat_id)
        if settings_text:
            await update.safe_edit_message_text(
                text=settings_text,
                reply_markup=get_account_filtering_buttons(update.chat_id),
                parse_mode=ParseMode.MARKDOWN_V2,
            )

        logger.info(f"Toggled account {account_id} ignore status for chat {update.chat_id}")

    except Exception:
        logger.exception("Error toggling account ignore status")
        # Try to refresh the menu on error
        settings_text = get_account_filtering_text(update.chat_id)
        if settings_text:
            await update.safe_edit_message_text(
                text=settings_text,
                reply_markup=get_account_filtering_buttons(update.chat_id),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
