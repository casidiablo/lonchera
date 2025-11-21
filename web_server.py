import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import unquote

from aiohttp import web

from lunch import get_lunch_client_for_chat_id

# Initialize logger
logger = logging.getLogger("web_server")
logging.basicConfig(level=logging.INFO)


@dataclass
class BotStatus:
    last_error: str = ""
    last_error_time: datetime | None = None
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
            link = f'<a href="https://t.me/{bot_data.username}">@{bot_data.username}</a>'
            bot_info_cache = f"{link} ({bot_data.first_name})"
        except Exception as e:
            return f"Error getting bot info: {e!s}"
        else:
            return bot_info_cache
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
    max_time_components = 2

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            display_name = name.rstrip("s") if value == 1 else name
            result.append(f"{int(value)} {display_name}")
        if len(result) == max_time_components:
            break

    if not result:
        result.append("just started")

    return ", ".join(result) + " ago"


start_time = time.time()


MASKED_TOKEN_MIN_LENGTH = 8


def get_masked_token():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if len(token) > MASKED_TOKEN_MIN_LENGTH:
        return f"{token[:4]}..."
    return "not set"


def get_ai_status():
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return "AI features disabled (no API key provided)"
    return f"AI enabled (key: {api_key[:4]}...)"


async def handle_root(request):
    db_size = get_db_size()
    uptime_seconds = time.time() - start_time
    uptime = format_relative_time(uptime_seconds)
    bot_info = await get_bot_info()

    version = os.getenv("VERSION")
    version_info = f"version: {version}" if version else ""

    commit = os.getenv("COMMIT")
    commit_link = f'<a href="https://github.com/casidiablo/lonchera/commit/{commit}">{commit}</a>' if commit else ""
    commit_info = f"commit: {commit_link}" if commit else ""

    status_details = ""
    if bot_status.last_error and bot_status.last_error_time:
        time_since_error = datetime.now() - bot_status.last_error_time
        if time_since_error < timedelta(minutes=1):
            status_details = f"Last error ({time_since_error.seconds}s ago): {bot_status.last_error}"

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


async def handle_manual_tx_endpoint(request):
    chat_id = request.match_info.get("chat_id")
    logger.info("Serving manual tx page for chat id %s", chat_id)

    # Generate account options
    lunch = get_lunch_client_for_chat_id(int(chat_id))
    account_options = "<option value=''>Select account...</option>"
    assets = lunch.get_assets()
    only_accounts = [asset for asset in assets if asset.type_name in {"credit", "cash"}]
    if only_accounts:
        account_options += "<option disabled>Manually-managed accounts</option>"
        for asset in only_accounts:
            balance = f"{asset.balance:,.2f} {asset.currency.upper()}"
            account_options += f'<option value="{asset.id}">└ {asset.name} (${balance})</option>'

    # Generate category options
    categories = lunch.get_categories()
    super_categories = [cat for cat in categories if cat.is_group]
    subcategories = [cat for cat in categories if cat.group_id is not None]
    standalone_categories = [cat for cat in categories if not cat.is_group and cat.group_id is None]

    category_options = """
        <option value=''>Select category...</option>
        <option value='None'>Uncategorized</option>
    """
    for super_category in super_categories:
        category_options += f"<option disabled>{super_category.name}</option>"
        for subcategory in subcategories:
            if subcategory.group_id == super_category.id:
                category_options += f'<option value="{subcategory.id}">└ {subcategory.name}</option>'
    for category in standalone_categories:
        category_options += f'<option value="{category.id}">{category.name}</option>'

    html_path = os.path.join(os.path.dirname(__file__), "manual_tx.html")
    with open(html_path) as file:
        response = file.read().replace("{chat_id}", chat_id)
        response = response.replace("{account_options}", account_options)
        response = response.replace("{category_options}", category_options)
    return web.Response(text=response, content_type="text/html")


def application_running():
    if not bot_status.is_running:
        return False

    if bot_status.last_error_time:
        # Check if error happened in the last minute
        if datetime.now() - bot_status.last_error_time < timedelta(minutes=1):
            return False

    return True


def validate_init_data(init_data: str, bot_token: str):
    vals = {k: unquote(v) for k, v in [s.split("=", 1) for s in init_data.split("&")]}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(vals.items()) if k != "hash")
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256)
    return h.hexdigest() == vals["hash"]


async def handle_validate(request):
    data = await request.post()
    init_data = data.get("initData", "")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    is_valid = validate_init_data(init_data, bot_token)
    return web.json_response({"valid": is_valid})


async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/manual_tx/{chat_id}", handle_manual_tx_endpoint)
    app.router.add_post("/validate", handle_validate)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "", 8080)

    logger.info("Starting web server on port 8080")
    await site.start()
    return runner
