import os
import time
import logging
from typing import Optional
from aiohttp import web
from dataclasses import dataclass
from datetime import datetime, timedelta

# Initialize logger
logger = logging.getLogger("web_server")
logging.basicConfig(level=logging.INFO)


@dataclass
class BotStatus:
    last_error: str = ""
    last_error_time: Optional[datetime] = None
    is_running: bool = False


bot_status = BotStatus()
bot_instance = None  # Add this line to store bot instance

bot_info_cache = None


def set_bot_instance(bot):
    global bot_instance
    bot_instance = bot


async def get_bot_info():
    global bot_info_cache
    if bot_instance:
        if bot_info_cache:
            return bot_info_cache
        try:
            bot_data = await bot_instance.get_me()
            link = (
                f'<a href="https://t.me/{bot_data.username}">@{bot_data.username}</a>'
            )
            bot_info_cache = f"{link} ({bot_data.first_name})"
            return bot_info_cache
        except Exception as e:
            return f"Error getting bot info: {str(e)}"
    return "Bot instance not available. Did you set the token?"


def update_bot_status(is_running: bool, error: str = ""):
    bot_status.is_running = is_running
    if error:
        bot_status.last_error = error
        bot_status.last_error_time = datetime.now()


def get_db_size():
    db_path = os.getenv("DB_PATH", "lonchera.db")
    if os.path.exists(db_path):
        size_bytes = os.path.getsize(db_path)
        size_mb = size_bytes / (1024 * 1024)
        return f"{size_mb:.2f} MB"
    return "DB not found"


def format_relative_time(seconds):
    intervals = (
        ("weeks", 604800),  # 60 * 60 * 24 * 7
        ("days", 86400),  # 60 * 60 * 24
        ("hours", 3600),  # 60 * 60
        ("minutes", 60),
        ("seconds", 1),
    )

    result = []

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip("s")
            result.append(f"{int(value)} {name}")
        if len(result) == 2:
            break

    if not result:
        result.append("just started")

    return ", ".join(result) + " ago"


start_time = time.time()


def get_masked_token():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if len(token) > 8:
        return f"{token[:4]}...{token[-4:]}"
    return "not set"


def get_ai_status():
    api_key = os.getenv("DEEPINFRA_API_KEY", "")
    if not api_key:
        return "AI features disabled (no API key provided)"
    return f"AI enabled (key: {api_key[:4]}...{api_key[-4:]})"


async def handle_root(request):
    db_size = get_db_size()
    uptime_seconds = time.time() - start_time
    uptime = format_relative_time(uptime_seconds)
    bot_info = await get_bot_info()

    version = os.getenv("VERSION")
    version_info = f"version: {version}" if version else ""

    commit = os.getenv("COMMIT")
    commit_link = (
        f'<a href="https://github.com/casidiablo/lonchera/commit/{commit}">{commit}</a>'
        if commit
        else ""
    )
    commit_info = f"commit: {commit_link}" if commit else ""

    status_details = ""
    if bot_status.last_error and bot_status.last_error_time:
        time_since_error = datetime.now() - bot_status.last_error_time
        if time_since_error < timedelta(minutes=1):
            status_details = (
                f"Last error ({time_since_error.seconds}s ago): {bot_status.last_error}"
            )

    bot_status_text = "running" if application_running() else "crashing"
    bot_token = get_masked_token()
    ai_status = get_ai_status()

    app_name = os.getenv("FLY_APP_NAME", "lonchera")

    response = f"""
    <html>
    <head>
    <title>{app_name}</title>
    <link rel="stylesheet" href="https://unpkg.com/sakura.css/css/sakura.css" media="screen" />
    <link rel="stylesheet"
          href="https://unpkg.com/sakura.css/css/sakura-dark.css"
          media="screen and (prefers-color-scheme: dark)"
    />
    <style>
        body {{
            font-family: monospace;
            white-space: pre-wrap;
        }}
    </style>
    </head>
    <body>
        <strong>#status</strong>
        bot: {bot_info}
        db size: {db_size}
        uptime: {uptime}
        {version_info}
        {commit_info}
        bot token: {bot_token}
        ai status: {ai_status}
        bot status: {bot_status_text}
        {status_details}
    </body>
    </html>
    """
    return web.Response(text=response.strip(), content_type="text/html")


def application_running():
    if not bot_status.is_running:
        return False

    if bot_status.last_error_time:
        # Check if error happened in the last minute
        if datetime.now() - bot_status.last_error_time < timedelta(minutes=1):
            return False

    return True


async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle_root)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "", 8080)

    logger.info("Starting web server on port 8080")
    await site.start()
    return runner
