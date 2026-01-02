import logging
from textwrap import dedent

from lunchable.exceptions import LunchMoneyError
from telegram import InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from errors import NoLunchTokenError
from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from telegram_extensions import Update
from utils import Keyboard

logger = logging.getLogger("account_filtering")


def get_account_filtering_text(chat_id: int) -> str | None:
    """Render menu with account list and ignore status."""
    try:
        # Get user's Plaid accounts from Lunch Money API (only these have transactions)
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        accounts = lunch_client.get_plaid_accounts()

        logger.info(f"Successfully fetched {len(accounts)} accounts for chat {chat_id}")

        # Get ignored accounts from database
        ignored_accounts = get_db().get_ignored_accounts_list(chat_id)
        ignored_set = set(ignored_accounts)

        # Filter out any ignored accounts that no longer exist (account deletion scenario)
        valid_account_ids = {acc.id for acc in accounts}
        stale_ignored_accounts = [acc_id for acc_id in ignored_accounts if acc_id not in valid_account_ids]

        if stale_ignored_accounts:
            logger.warning(
                f"Found {len(stale_ignored_accounts)} stale ignored account IDs for chat {chat_id}: {stale_ignored_accounts}"
            )
            # Remove stale account IDs from ignored list
            cleaned_ignored_accounts = [acc_id for acc_id in ignored_accounts if acc_id in valid_account_ids]
            get_db().update_ignored_accounts(chat_id, cleaned_ignored_accounts)
            ignored_set = set(cleaned_ignored_accounts)
            logger.info(f"Cleaned up stale ignored accounts for chat {chat_id}")

        if not accounts:
            logger.warning(f"No Plaid accounts found for chat {chat_id}")
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

        return dedent(
            f"""
            🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂 \\- *Account Filtering*

            Configure which accounts should be ignored for transaction notifications\\.

            📊 *Summary*: {ignored_count} of {total_count} accounts ignored

            Tap an account below to toggle its notification status\\.
            """
        )

    except NoLunchTokenError:
        logger.exception(f"No Lunch Money token found for chat {chat_id}")
        return dedent(
            """
            🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂 \\- *Account Filtering*

            ❌ Lunch Money token not found\\.

            Please set up your Lunch Money connection first in Settings → Session\\.
            """
        )
    except LunchMoneyError:
        logger.exception(f"Lunch Money API error for chat {chat_id}")
        return dedent(
            """
            🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂 \\- *Account Filtering*

            ❌ Error connecting to Lunch Money API\\.

            Please check your connection and try again\\. If the problem persists, your token may need to be refreshed\\.
            """
        )
    except Exception:
        logger.exception(f"Unexpected error fetching accounts for filtering menu for chat {chat_id}")
        return dedent(
            """
            🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂 \\- *Account Filtering*

            ❌ Unexpected error loading accounts\\.

            Please try again later\\. If the problem persists, please contact support\\.
            """
        )


def get_account_filtering_buttons(chat_id: int) -> InlineKeyboardMarkup:
    """Create toggle buttons for each account."""
    kbd = Keyboard()

    try:
        # Get user's Plaid accounts from Lunch Money API (only these have transactions)
        lunch_client = get_lunch_client_for_chat_id(chat_id)
        accounts = lunch_client.get_plaid_accounts()

        # Get ignored accounts from database
        ignored_accounts = get_db().get_ignored_accounts_list(chat_id)
        ignored_set = set(ignored_accounts)

        # Create toggle buttons for each account
        for account in accounts:
            status_icon = "🔕" if account.id in ignored_set else "🔔"

            # Get account name - use display_name if available, otherwise name
            account_name = getattr(account, "display_name", None) or account.name

            button_text = f"{status_icon} {account_name}"
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
