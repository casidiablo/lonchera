import logging
import os
from datetime import datetime, timedelta

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from persistence import get_db
from utils import Keyboard

logger = logging.getLogger(__name__)


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Received /stats command")
    admin_user_id = os.getenv("ADMIN_USER_ID")
    if not admin_user_id or update.effective_user.id != int(admin_user_id):
        await update.message.reply_text("You are not authorized to use this command.")
        return

    db = get_db()
    today = datetime.now()
    start_of_week = today - timedelta(days=6)
    end_of_week = today

    metric_name = context.args[0] if context.args else None
    if metric_name:
        metrics = db.get_specific_metrics(metric_name, start_of_week, end_of_week)
    else:
        metrics = db.get_all_metrics(start_of_week, end_of_week)

    message = "Analytics for the last 7 days:\n\n"
    has_data = False
    all_metrics = {}

    for day in range(7):
        date = start_of_week + timedelta(days=day)
        date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_metrics = metrics.get(date, {})
        if day_metrics:
            has_data = True
            for key, value in day_metrics.items():
                if key not in all_metrics:
                    all_metrics[key] = {}
                all_metrics[key][date.strftime("%a %b %d")] = value

    for metric_name, values in all_metrics.items():
        total_sum = sum(float(value) for value in values.values())
        if int(total_sum) == total_sum:
            total_sum = int(total_sum)
            message += f"`{metric_name}` (Total: {total_sum})\n"
        else:
            message += f"`{metric_name}` (Total: {total_sum:.4f})\n"
        for date, value in values.items():
            if int(value) == value:
                value = int(value)
            else:
                # truncate to the first 4 decimals
                value = f"{value:.4f}"
            message += f"  {date}: `{value}`\n"
        message += "\n"

    if not has_data:
        message += "No analytics data available for this week."

    await update.message.reply_text(
        text=message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=Keyboard.build_from(("Close", "cancel")),
    )


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_user_id = os.getenv("ADMIN_USER_ID")
    if not admin_user_id or update.effective_user.id != int(admin_user_id):
        await update.message.reply_text("You are not authorized to use this command.")
        return

    db = get_db()
    user_count = db.get_user_count()
    db_size = db.get_db_size()
    sent_message_count = db.get_sent_message_count()

    message = (
        f"Bot Status:\n\n"
        f"Number of users: {user_count}\n"
        f"Database size: {db_size / (1024 * 1024):.2f} MB\n"
        f"Messages sent: {sent_message_count}\n"
    )

    await update.message.reply_text(
        text=message,
        reply_markup=Keyboard.build_from(("Close", "cancel")),
    )
