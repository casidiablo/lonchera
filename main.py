import asyncio
import logging
import os
import signal

from dotenv import load_dotenv
from telegram import Update
from telegram.error import Conflict, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from handlers.amz import (
    handle_amazon_sync,
    handle_preview_process_amazon_transactions,
    handle_process_amazon_transactions,
    handle_update_amz_settings,
)
from handlers.analytics import handle_stats, handle_status
from handlers.lunch_money_agent import handle_generic_message_with_ai
from handlers.audio import handle_audio_transcription
from handlers.balances import handle_btn_accounts_balances, handle_done_balances, handle_show_balances
from handlers.budget import (
    handle_btn_hide_budget_categories,
    handle_btn_show_budget_categories,
    handle_btn_show_budget_for_category,
    handle_done_budget,
    handle_show_budget,
)
from handlers.general import (
    clear_cache,
    handle_cancel,
    handle_errors,
    handle_file_upload,
    handle_generic_message,
    handle_start,
)
from handlers.settings.ai import (
    handle_ai_settings,
    handle_btn_toggle_ai_agent,
    handle_btn_toggle_show_transcription,
    handle_set_ai_language,
    handle_set_language,
)
from handlers.settings.general import handle_btn_done_settings, handle_settings, handle_settings_menu
from handlers.settings.schedule_rendering import (
    handle_btn_cancel_poll_interval_change,
    handle_btn_change_poll_interval,
    handle_btn_change_timezone,
    handle_btn_toggle_poll_pending,
    handle_btn_toggle_show_datetime,
    handle_btn_toggle_tagging,
    handle_schedule_rendering_settings,
)
from handlers.settings.session import (
    handle_btn_set_token_from_button,
    handle_btn_trigger_plaid_refresh,
    handle_logout,
    handle_logout_cancel,
    handle_logout_confirm,
    handle_session_settings,
)
from handlers.settings.transactions_handling import (
    handle_btn_toggle_auto_categorize_after_notes,
    handle_btn_toggle_auto_mark_reviewed,
    handle_btn_toggle_mark_reviewed_after_categorized,
    handle_transactions_handling_settings,
)
from handlers.syncing import handle_resync
from handlers.transactions import (
    check_pending_transactions,
    handle_btn_ai_categorize,
    handle_btn_apply_category,
    handle_btn_cancel_categorization,
    handle_btn_collapse_transaction,
    handle_btn_dump_plaid_details,
    handle_btn_mark_tx_as_reviewed,
    handle_btn_mark_tx_as_unreviewed,
    handle_btn_show_categories,
    handle_btn_show_subcategories,
    handle_btn_skip_transaction,
    handle_check_transactions,
    handle_edit_notes,
    handle_expand_tx_options,
    handle_rename_payee,
    handle_set_tags,
    handle_message_reply,
    poll_transactions_on_schedule,
)
from manual_tx import handle_manual_tx, handle_web_app_data
from web_server import run_web_server, set_bot_instance, update_bot_status

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(name)s] %(levelname%s: %(message)s")
logger = logging.getLogger("lonchera")

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.ExtBot").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.Updater").setLevel(logging.WARNING)


def add_command_handlers(app):
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("add_transaction", handle_manual_tx))
    app.add_handler(CommandHandler("review_transactions", handle_check_transactions))
    app.add_handler(CommandHandler("pending_transactions", check_pending_transactions))
    app.add_handler(CommandHandler("show_budget", handle_show_budget))
    app.add_handler(CommandHandler("clear_cache", clear_cache))
    app.add_handler(CommandHandler("settings", handle_settings))
    app.add_handler(CommandHandler("stats", handle_stats))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("amazon_sync", handle_amazon_sync))
    app.add_handler(CommandHandler("resync", handle_resync))
    app.add_handler(CommandHandler("balances", handle_show_balances))


def add_callback_query_handlers(app):
    app.add_handler(CallbackQueryHandler(handle_settings_menu, pattern=r"^settingsMenu$"))
    app.add_handler(CallbackQueryHandler(handle_schedule_rendering_settings, pattern=r"^scheduleRenderingSettings$"))
    app.add_handler(
        CallbackQueryHandler(handle_transactions_handling_settings, pattern=r"^transactionsHandlingSettings$")
    )
    app.add_handler(CallbackQueryHandler(handle_ai_settings, pattern=r"^aiSettings$"))
    app.add_handler(CallbackQueryHandler(handle_session_settings, pattern=r"^sessionSettings$"))
    app.add_handler(CallbackQueryHandler(handle_btn_skip_transaction, pattern=r"^skip_"))
    app.add_handler(CallbackQueryHandler(handle_btn_collapse_transaction, pattern=r"^collapse_"))
    app.add_handler(CallbackQueryHandler(handle_btn_show_budget_categories, pattern=r"^showBudgetCategories_"))
    app.add_handler(CallbackQueryHandler(handle_btn_hide_budget_categories, pattern=r"^exitBudgetDetails_"))
    app.add_handler(CallbackQueryHandler(handle_btn_show_budget_for_category, pattern=r"^showBudgetDetails_"))
    app.add_handler(CallbackQueryHandler(handle_show_budget, pattern=r"^showBudget_"))
    app.add_handler(CallbackQueryHandler(handle_btn_change_poll_interval, pattern=r"^changePollInterval"))
    app.add_handler(CallbackQueryHandler(handle_btn_set_token_from_button, pattern=r"^registerToken$"))
    app.add_handler(CallbackQueryHandler(handle_logout, pattern=r"^logout$"))
    app.add_handler(CallbackQueryHandler(handle_logout_confirm, pattern=r"^logout_confirm$"))
    app.add_handler(CallbackQueryHandler(handle_btn_toggle_auto_mark_reviewed, pattern=r"^toggleAutoMarkReviewed"))
    app.add_handler(CallbackQueryHandler(handle_logout_cancel, pattern=r"^logout_cancel$"))
    app.add_handler(CallbackQueryHandler(handle_btn_done_settings, pattern=r"^doneSettings$"))
    app.add_handler(CallbackQueryHandler(handle_btn_cancel_categorization, pattern=r"^cancelCategorization_"))
    app.add_handler(CallbackQueryHandler(handle_btn_show_categories, pattern=r"^categorize_"))
    app.add_handler(CallbackQueryHandler(handle_btn_ai_categorize, pattern=r"^aicategorize_"))
    app.add_handler(CallbackQueryHandler(handle_btn_show_subcategories, pattern=r"^subcategorize_"))
    app.add_handler(CallbackQueryHandler(handle_btn_apply_category, pattern=r"^applyCategory_"))
    app.add_handler(CallbackQueryHandler(handle_btn_dump_plaid_details, pattern=r"^plaid_"))
    app.add_handler(CallbackQueryHandler(handle_btn_mark_tx_as_reviewed, pattern=r"^review_"))
    app.add_handler(CallbackQueryHandler(handle_btn_mark_tx_as_unreviewed, pattern=r"^unreview_"))
    app.add_handler(CallbackQueryHandler(handle_expand_tx_options, pattern=r"^moreOptions_"))
    app.add_handler(CallbackQueryHandler(handle_rename_payee, pattern=r"^renamePayee_"))
    app.add_handler(CallbackQueryHandler(handle_edit_notes, pattern=r"^editNotes_"))
    app.add_handler(CallbackQueryHandler(handle_set_tags, pattern=r"^setTags_"))
    app.add_handler(CallbackQueryHandler(handle_btn_accounts_balances, pattern=r"^accountsBalances_"))
    app.add_handler(CallbackQueryHandler(handle_done_balances, pattern=r"^doneBalances$"))
    app.add_handler(CallbackQueryHandler(handle_btn_trigger_plaid_refresh, pattern=r"^triggerPlaidRefresh$"))
    app.add_handler(CallbackQueryHandler(handle_btn_toggle_poll_pending, pattern=r"^togglePollPending"))
    app.add_handler(CallbackQueryHandler(handle_btn_toggle_show_datetime, pattern=r"^toggleShowDateTime"))
    app.add_handler(CallbackQueryHandler(handle_btn_toggle_tagging, pattern=r"^toggleTagging"))
    app.add_handler(
        CallbackQueryHandler(
            handle_btn_toggle_mark_reviewed_after_categorized, pattern=r"^toggleMarkReviewedAfterCategorized$"
        )
    )
    app.add_handler(CallbackQueryHandler(handle_btn_change_timezone, pattern=r"^changeTimezone"))
    app.add_handler(
        CallbackQueryHandler(handle_btn_toggle_auto_categorize_after_notes, pattern=r"^toggleAutoCategorizeAfterNotes")
    )
    app.add_handler(CallbackQueryHandler(handle_btn_toggle_ai_agent, pattern=r"^toggleAIAgent"))
    app.add_handler(CallbackQueryHandler(handle_btn_toggle_show_transcription, pattern=r"^toggleShowTranscription"))
    app.add_handler(CallbackQueryHandler(handle_set_ai_language, pattern=r"^setAILanguage"))
    app.add_handler(CallbackQueryHandler(handle_set_language, pattern=r"^setLanguage_"))
    app.add_handler(CallbackQueryHandler(handle_btn_cancel_poll_interval_change, pattern=r"^cancelPollIntervalChange$"))
    app.add_handler(CallbackQueryHandler(handle_done_budget, pattern=r"^doneBudget$"))
    app.add_handler(CallbackQueryHandler(handle_update_amz_settings, pattern=r"^update_amz_settings_"))
    app.add_handler(
        CallbackQueryHandler(
            handle_preview_process_amazon_transactions, pattern=r"^preview_process_amazon_transactions$"
        )
    )
    app.add_handler(CallbackQueryHandler(handle_process_amazon_transactions, pattern=r"^process_amazon_transactions$"))
    # Add a generic cancel handler for any leftover cancel buttons
    app.add_handler(CallbackQueryHandler(handle_cancel, pattern=r"^cancel$"))

    # Catch any other unknown buttons
    async def handle_unknown_btn(update: Update, _: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer(text=f"Unknown command {query.data}", show_alert=True)

    app.add_handler(CallbackQueryHandler(handle_unknown_btn))


def setup_handlers(config):
    app = Application.builder().token(config["TELEGRAM_BOT_TOKEN"]).build()

    add_command_handlers(app)
    add_callback_query_handlers(app)

    app.add_error_handler(handle_errors)

    app.job_queue.run_repeating(poll_transactions_on_schedule, interval=60, first=5)

    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, handle_message_reply))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.REPLY, handle_generic_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))
    app.add_handler(MessageHandler((filters.VOICE | filters.AUDIO), handle_audio_transcription))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

    logger.info("Telegram handlers set up successfully")

    return app


def load_config():
    load_dotenv()

    return {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "PROMPT_FOR_NOTES": os.getenv("PROMPT_FOR_NOTES", "true").lower() == "true",
        "PROMPT_FOR_CATEGORIES": os.getenv("PROMPT_FOR_CATEGORIES", "true").lower() == "true",
    }


async def main():
    config = load_config()

    if not config["TELEGRAM_BOT_TOKEN"]:
        logger.warning("No TELEGRAM_BOT_TOKEN provided. Only running web server.")
        runner = await run_web_server()

        stop_signal = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_signal.set)
        try:
            await stop_signal.wait()
        finally:
            await runner.cleanup()
        return

    app = setup_handlers(config)

    # Set bot instance in web server
    set_bot_instance(app.bot)

    # Set up signal handlers
    loop = asyncio.get_running_loop()
    stop_signal = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: (update_bot_status(False), stop_signal.set()))

    def error_callback(exc: TelegramError):
        error_msg = str(exc)
        if isinstance(exc, Conflict):
            error_msg = (
                "Bot instance conflict detected. Look at the logs, but usually this "
                "means there are other instances of the bot running with the same token, "
                "which is not allowed."
            )
        logger.warning(f"Exception happened while polling for updates: {exc}", exc_info=exc)
        update_bot_status(True, error_msg)

    async with app:
        await app.initialize()
        await app.start()
        update_bot_status(True)  # Mark as running when started
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, error_callback=error_callback)

        # Start the web server
        runner = await run_web_server()

        try:
            await stop_signal.wait()
        finally:
            update_bot_status(False)  # Mark as stopped during cleanup
            await runner.cleanup()
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    logger.info("Starting Lonchera bot...")
    asyncio.run(main())

# TODO
# - Have the bot pin a message containing important info:
#  - Current networth
#  - current debt
#  - next recurring charges
