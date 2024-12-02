from datetime import timedelta
import pytz
from textwrap import dedent
from telegram import InlineKeyboardMarkup, LinkPreviewOptions, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from handlers.expectations import EXPECTING_TIME_ZONE, set_expectation
from utils import Keyboard
from persistence import Settings, get_db
from typing import Optional


def get_schedule_rendering_text(chat_id: int) -> Optional[str]:
    settings = get_db().get_current_settings(chat_id)
    if settings is None:
        return None

    poll_interval = settings.poll_interval_secs
    next_poll_at = ""
    if poll_interval is None or poll_interval == 0:
        poll_interval = "Disabled"
    else:
        if poll_interval < 3600:
            poll_interval = f"`{poll_interval // 60} minutes`"
        elif poll_interval < 86400:
            if poll_interval // 3600 == 1:
                poll_interval = "`1 hour`"
            else:
                poll_interval = f"`{poll_interval // 3600} hours`"
        else:
            if poll_interval // 86400 == 1:
                poll_interval = "`1 day`"
            else:
                poll_interval = f"`{poll_interval // 86400} days`"

        last_poll = settings.last_poll_at
        if last_poll:
            next_poll_at = last_poll + timedelta(seconds=settings.poll_interval_secs)
            next_poll_at = next_poll_at.astimezone(
                pytz.timezone(settings.timezone or "UTC")
            )
            next_poll_at = (
                f"> Next poll at `{next_poll_at.strftime('%a, %b %d at %I:%M %p %Z')}`"
            )

    return dedent(
        f"""
        🛠️ 🆂🅴🆃🆃🅸🅽🅶🆂 \\- *Schedule & Rendering*

        ➊ *Poll interval*: {poll_interval}
        > This is how often we check for new transactions\\.
        {next_poll_at}
        > Trigger now: /review\\_transactions

        ➋ *Polling mode*: {"`pending`" if settings.poll_pending else "`posted`"}
        > When `posted` is enabled, the bot will poll for transactions that are already posted\\.
        > This is the default mode and, because of the way Lunch Money/Plaid work, will allow categorizing
        > the transactions and mark them as reviewed from Telegram\\.
        >
        > When `pending` the bot will only poll for pending transactions\\.
        > This sends you more timely notifications, but you would need to either manually review them or
        > enable auto\\-mark transactions as reviewed\\.


        ➌ *Show full date/time*: {"🟢 ᴏɴ" if settings.show_datetime else "🔴 ᴏꜰꜰ"}
        > When enabled, shows the full date and time for each transaction\\.
        > When disabled, shows only the date without the time\\.
        > _We allow disabling time because more often than it is not reliable\\._


        ➍ *Tagging*: {"🟢 ᴏɴ" if settings.tagging else "🔴 ᴏꜰꜰ"}
        > When enabled, renders categories as Telegram tags\\.
        > Useful for filtering transactions\\.


        ➎ *Timezone*: `{settings.timezone}`
        > This is the timezone used for displaying dates and times\\.
        """
    )


def get_schedule_rendering_buttons(settings: Settings) -> InlineKeyboardMarkup:
    kbd = Keyboard()
    kbd += ("➊ Change interval", "changePollInterval")
    kbd += ("➋ Toggle polling mode", f"togglePollPending_{settings.poll_pending}")
    kbd += ("➌ Show date/time?", f"toggleShowDateTime_{settings.show_datetime}")
    kbd += ("➍ Toggle tagging", f"toggleTagging_{settings.tagging}")
    kbd += ("➎ Change timezone", "changeTimezone")
    kbd += ("Back", "settingsMenu")
    return kbd.build()


async def handle_schedule_rendering_settings(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    settings_text = get_schedule_rendering_text(update.effective_chat.id)
    settings = get_db().get_current_settings(update.effective_chat.id)
    await update.callback_query.edit_message_text(
        text=settings_text,
        reply_markup=get_schedule_rendering_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_change_poll_interval(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Changes the poll interval for the chat."""
    if "_" in update.callback_query.data:
        poll_interval = int(update.callback_query.data.split("_")[1])
        get_db().update_poll_interval(update.effective_chat.id, poll_interval)
        settings = get_db().get_current_settings(update.effective_chat.id)
        await update.callback_query.edit_message_text(
            text=f"_Poll interval updated_\n\n{get_schedule_rendering_text(update.effective_chat.id)}",
            reply_markup=get_schedule_rendering_buttons(settings),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        kbd = Keyboard()
        kbd += ("5 minutes", "changePollInterval_300")
        kbd += ("30 minutes", "changePollInterval_1800")
        kbd += ("1 hour", "changePollInterval_3600")
        kbd += ("4 hours", "changePollInterval_14400")
        kbd += ("24 hours", "changePollInterval_86400")
        kbd += ("Disable", "changePollInterval_0")
        kbd += ("Cancel", "cancelPollIntervalChange")
        await update.callback_query.edit_message_text(
            text="Please choose the new poll interval in minutes...",
            reply_markup=kbd.build(),
        )


async def handle_btn_cancel_poll_interval_change(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    settings_text = get_schedule_rendering_text(update.effective_chat.id)
    settings = get_db().get_current_settings(update.effective_chat.id)
    await update.callback_query.edit_message_text(
        text=settings_text,
        reply_markup=get_schedule_rendering_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_toggle_poll_pending(update: Update, _: ContextTypes.DEFAULT_TYPE):
    settings = get_db().get_current_settings(update.effective_chat.id)
    get_db().update_poll_pending(update.effective_chat.id, not settings.poll_pending)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=get_schedule_rendering_text(update.effective_chat.id),
        reply_markup=get_schedule_rendering_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_toggle_show_datetime(update: Update, _: ContextTypes.DEFAULT_TYPE):
    settings = get_db().get_current_settings(update.effective_chat.id)

    get_db().update_show_datetime(update.effective_chat.id, not settings.show_datetime)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=get_schedule_rendering_text(update.effective_chat.id),
        reply_markup=get_schedule_rendering_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_toggle_tagging(update: Update, _: ContextTypes.DEFAULT_TYPE):
    settings = get_db().get_current_settings(update.effective_chat.id)

    get_db().update_tagging(update.effective_chat.id, not settings.tagging)

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text=get_schedule_rendering_text(update.effective_chat.id),
        reply_markup=get_schedule_rendering_buttons(settings),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def handle_btn_change_timezone(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Changes the timezone for the chat."""
    msg = await update.callback_query.edit_message_text(
        text=dedent(
            """
            Please provide a time zone\\.

            The timezone must be specified in tz database format\\.

            Examples:
            \\- `UTC`
            \\- `US/Eastern`
            \\- `Europe/Berlin`
            \\- `Asia/Tokyo`

            For a full list of time zones,
            see [this link](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)\\.
            """
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    set_expectation(
        update.effective_chat.id,
        {
            "expectation": EXPECTING_TIME_ZONE,
            "msg_id": msg.message_id,
        },
    )