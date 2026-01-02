"""
Admin command handlers for managing blocked users and database backup.
"""

import asyncio
import logging
import os
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from persistence import get_db
from telegram_extensions import Update
from utils import clean_md_v2, is_admin_user

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


async def create_database_backup(db_path: str, backup_path: str) -> bool:
    """Create SQLite database backup using .backup command.

    Args:
        db_path: Path to source database file
        backup_path: Path where backup should be created

    Returns:
        True if backup successful, False otherwise
    """
    try:
        # Validate source database exists
        if not os.path.exists(db_path):
            logger.error(f"Source database does not exist: {db_path}")
            return False

        # Ensure backup directory exists
        backup_dir = os.path.dirname(backup_path)
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)

        # Execute SQLite backup command with timeout
        cmd = ["sqlite3", db_path, f".backup {backup_path}"]
        logger.info(f"Executing backup command: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
        except TimeoutError:
            logger.exception("Database backup timed out after 30 seconds")
            process.kill()
            await process.wait()
            return False

        # Check if process completed successfully
        if process.returncode != 0:
            error_msg = stderr.decode("utf-8") if stderr else "Unknown error"
            logger.error(f"SQLite backup failed with return code {process.returncode}: {error_msg}")
            return False

        # Validate backup file was created and has reasonable size
        if not os.path.exists(backup_path):
            logger.error(f"Backup file was not created: {backup_path}")
            return False

        backup_size = os.path.getsize(backup_path)
        if backup_size == 0:
            logger.error(f"Backup file is empty: {backup_path}")
            os.remove(backup_path)  # Clean up empty file
            return False

        # Get original database size for comparison
        original_size = os.path.getsize(db_path)
        logger.info(
            f"Backup created successfully: {backup_path} ({backup_size} bytes, original: {original_size} bytes)"
        )

    except Exception:
        logger.exception("Unexpected error during database backup")
        # Clean up partial backup file if it exists
        if os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except Exception:
                logger.exception("Failed to clean up partial backup file")
        return False
    else:
        return True


async def upload_backup_to_s3(local_path: str, s3_key: str) -> bool:
    """Upload backup file to S3 bucket.

    Args:
        local_path: Path to local backup file
        s3_key: S3 object key (filename in bucket)

    Returns:
        True if upload successful, False otherwise
    """
    bucket_name = "lonchera-backups"

    try:
        # Validate local file exists
        if not os.path.exists(local_path):
            logger.error(f"Local backup file does not exist: {local_path}")
            return False

        file_size = os.path.getsize(local_path)
        if file_size == 0:
            logger.error(f"Local backup file is empty: {local_path}")
            return False

        logger.info(f"Starting S3 upload: {local_path} -> s3://{bucket_name}/{s3_key} ({file_size} bytes)")

        # Create S3 client with default credential chain
        s3_client = boto3.client("s3")

        # Upload file directly to S3
        s3_client.upload_file(local_path, bucket_name, s3_key)

        # Verify upload completion with HEAD request
        try:
            response = s3_client.head_object(Bucket=bucket_name, Key=s3_key)
            uploaded_size = response.get("ContentLength", 0)

            if uploaded_size != file_size:
                logger.error(f"Upload size mismatch: expected {file_size}, got {uploaded_size}")
                return False

        except ClientError:
            logger.exception("Failed to verify S3 upload")
            return False
        else:
            logger.info(f"S3 upload completed successfully: s3://{bucket_name}/{s3_key}")
            return True

    except (ClientError, BotoCoreError) as e:
        error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "Unknown")
        logger.exception(f"S3 upload failed: {error_code}")
        return False
    except Exception:
        logger.exception("Unexpected error during S3 upload")
        return False


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


async def handle_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /backup command - create database backup and upload to S3."""
    if not update.message:
        return

    chat_id = update.chat_id

    # Check if user is admin
    if not is_admin_user(chat_id):
        await update.message.reply_text("Unauthorized")
        return

    # Send initial progress message
    progress_message = await update.message.reply_text("Creating database backup...")

    try:
        # Generate timestamp and paths
        timestamp = datetime.now().strftime("%y%m%d_%H")
        backup_filename = f"lonchera_{timestamp}.db"
        backup_path = f"/tmp/{backup_filename}"

        # Get database path from environment or default
        db_path = os.getenv("DB_PATH", "lonchera.db")

        logger.info(f"Starting backup process: {db_path} -> {backup_path}")

        # Create database backup
        backup_success = await create_database_backup(db_path, backup_path)
        if not backup_success:
            error_msg = "❌ Database backup creation failed. Check logs for details."
            await progress_message.edit_text(error_msg)
            logger.error("Database backup creation failed")
            return

        # Upload to S3
        s3_key = backup_filename
        upload_success = await upload_backup_to_s3(backup_path, s3_key)

        if upload_success:
            # Clean up local file after successful upload
            try:
                os.remove(backup_path)
                logger.info(f"Local backup file cleaned up: {backup_path}")
            except Exception:
                logger.exception("Failed to clean up local backup file")

            # Send success message with S3 location
            success_msg = (
                f"✅ *Backup completed successfully*\n\n"
                f"*Filename:* `{clean_md_v2(backup_filename)}`\n"
                f"*S3 Location:* `s3://lonchera-backups/{clean_md_v2(s3_key)}`"
            )
            print(success_msg)
            await progress_message.edit_text(success_msg, parse_mode=ParseMode.MARKDOWN_V2)
            logger.info(f"Backup process completed successfully: {s3_key}")
        else:
            # S3 upload failed, retain local file for manual recovery
            error_msg = (
                f"⚠️ *Backup created but S3 upload failed*\n\n"
                f"Local backup retained at: `{clean_md_v2(backup_path)}`\n"
                f"Please check AWS credentials and try again."
            )
            await progress_message.edit_text(error_msg, parse_mode=ParseMode.MARKDOWN_V2)
            logger.error(f"S3 upload failed, local backup retained: {backup_path}")

    except Exception:
        logger.exception("Unexpected error during backup process")
        error_msg = "❌ Backup process failed due to unexpected error. Check logs for details."
        await progress_message.edit_text(error_msg)
