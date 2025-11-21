"""
Admin command handlers for managing blocked users.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from persistence import get_db
from telegram_extensions import Update
from utils import is_admin_user

logger = logging.getLogger("admin")


async def handle_blocked_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /blocked_users command - list all blocked users.

    This command is only available to admin users. It displays a list of all users
    who have blocked the bot, along with counts of their associated database records.
    """
    if not update.message:
        return

    chat_id = update.chat_id

    # Check if user is admin
    if not is_admin_user(chat_id):
        await update.message.reply_text("Unauthorized")
        return

    # Get blocked users from database
    db = get_db()
    blocked_chat_ids = db.get_blocked_users()

    # If no blocked users, send friendly message
    if not blocked_chat_ids:
        await update.message.reply_text("No blocked users found. All users are active!", parse_mode=ParseMode.MARKDOWN)
        return

    # Format response with chat_ids
    response_lines = ["*Blocked Users:*\n"]

    for blocked_chat_id in blocked_chat_ids:
        response_lines.append(f"• `{blocked_chat_id}`")

    response = "\n".join(response_lines)

    # Send formatted message to admin
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)


async def handle_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delete_user <chat_id> command - delete a blocked user.

    This command is only available to admin users. It prompts for confirmation
    before deleting all data associated with a blocked user.
    """
    if not update.message:
        return

    chat_id = update.chat_id

    # Check if user is admin
    if not is_admin_user(chat_id):
        await update.message.reply_text("Unauthorized")
        return

    # Parse chat_id from command arguments
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "Usage: /delete_user <chat_id>\n\nExample: /delete_user 123456789", parse_mode=ParseMode.MARKDOWN
        )
        return

    # Validate chat_id format (must be integer)
    try:
        target_chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "Invalid chat_id format. Please provide a valid integer chat_id.", parse_mode=ParseMode.MARKDOWN
        )
        return

    # Check if user exists and is blocked
    db = get_db()
    if not db.is_user_blocked(target_chat_id):
        await update.message.reply_text(
            f"User with chat_id `{target_chat_id}` is not blocked or does not exist.\n\n"
            "Only blocked users can be deleted. Use /blocked_users to see the list of blocked users.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Get transaction count for confirmation message
    tx_count = db.get_user_transaction_count(target_chat_id)

    # Create inline keyboard with "Confirm Delete" and "Cancel" buttons
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm Delete", callback_data=f"confirmDeleteUser_{target_chat_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancelDeleteUser"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send confirmation message with user info and buttons
    confirmation_message = (
        f"⚠️ *Delete User Confirmation*\n\n"
        f"You are about to delete all data for:\n"
        f"*Chat ID:* `{target_chat_id}`\n\n"
        f"This will delete {tx_count} transaction(s) and their settings.\n\n"
        f"*This action cannot be undone!*"
    )

    await update.message.reply_text(confirmation_message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


async def handle_btn_confirm_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation button for user deletion."""
    if not update.callback_query:
        return

    query = update.callback_query
    await query.answer()

    # Extract chat_id from callback data
    callback_data = query.data
    if not callback_data or not callback_data.startswith("confirmDeleteUser_"):
        await query.edit_message_text("Invalid callback data.")
        return

    try:
        target_chat_id = int(callback_data.replace("confirmDeleteUser_", ""))
    except ValueError:
        await query.edit_message_text("Invalid chat_id in callback data.")
        return

    # Call delete_user_data from database
    db = get_db()
    deleted_counts = db.delete_user_data(target_chat_id)

    # Format success message with deletion counts
    success_message = (
        f"✅ *User Deleted Successfully*\n\n"
        f"*Chat ID:* `{target_chat_id}`\n\n"
        f"*Deleted records:*\n"
        f"  • Transactions: {deleted_counts['transactions']}\n"
        f"  • Settings: {deleted_counts['settings']}\n"
        f"  • Analytics: {deleted_counts['analytics']}\n\n"
        f"Total records deleted: {sum(deleted_counts.values())}"
    )

    # Edit original message to show success
    await query.edit_message_text(success_message, parse_mode=ParseMode.MARKDOWN)


async def handle_btn_cancel_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle cancel button for user deletion."""
    if not update.callback_query:
        return

    query = update.callback_query
    await query.answer()

    # Delete the confirmation message
    await query.delete_message()

    # Send cancellation acknowledgment
    if update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ User deletion cancelled.")
