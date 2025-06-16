from lunchable.models import AssetsObject, CryptoObject, PlaidAccountObject
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from lunch import get_lunch_client_for_chat_id
from persistence import get_db
from utils import Keyboard, get_crypto_symbol, get_emoji_for_account_type, make_tag

# Constants for button states
SHOW_DETAILS = 1 << 0
SHOW_BALANCES = 1 << 1
SHOW_ASSETS = 1 << 2
SHOW_CRYPTO = 1 << 3


# Helper functions to check the state of each field given a mask
def is_show_details(mask: int) -> bool:
    return bool(mask & SHOW_DETAILS)


def is_show_balances(mask: int) -> bool:
    return bool(mask & SHOW_BALANCES)


def is_show_assets(mask: int) -> bool:
    return bool(mask & SHOW_ASSETS)


def is_show_crypto(mask: int) -> bool:
    return bool(mask & SHOW_CRYPTO)


def get_accounts_buttons(current_mask: int) -> InlineKeyboardMarkup:
    kbd = Keyboard()

    def emoji_for_field(field: int) -> str:
        return "☑️" if bool(current_mask & field) else "☐"

    # Toggle the state of each button's corresponding bit in the mask
    show_balances_mask = current_mask ^ SHOW_BALANCES
    kbd += (f"{emoji_for_field(SHOW_BALANCES)} Show accounts", f"accountsBalances_{show_balances_mask}")

    show_assets_mask = current_mask ^ SHOW_ASSETS
    kbd += (f"{emoji_for_field(SHOW_ASSETS)} Show assets", f"accountsBalances_{show_assets_mask}")

    show_crypto_mask = current_mask ^ SHOW_CRYPTO
    kbd += (f"{emoji_for_field(SHOW_CRYPTO)} Show crypto", f"accountsBalances_{show_crypto_mask}")

    show_details_mask = current_mask ^ SHOW_DETAILS
    kbd += (f"{emoji_for_field(SHOW_DETAILS)}  Show details", f"accountsBalances_{show_details_mask}")

    kbd += ("Done", "doneBalances")

    return kbd.build()


def get_plaid_account_summary_text(acct: PlaidAccountObject, show_details: bool) -> str:
    """Returns a message with the accounts and their balances."""
    if show_details:
        institution = ""
        if acct.institution_name and acct.institution_name != (acct.display_name or acct.name):
            institution = f" (_{acct.institution_name}_)"
        txt = f"*{acct.display_name or acct.name}* {institution}\n"
        txt += f"Balance: `${acct.balance:,.2f}` {acct.currency.upper()}"
        if acct.limit:
            txt += f" / `${acct.limit:,.2f}` {acct.currency.upper()}\n"
        else:
            txt += "\n"
        txt += f"Last update: {acct.balance_last_update.strftime('%a, %b %d at %I:%M %p')}\n"
        return txt + f"Status: {acct.status}\n\n"
    else:
        return f" • *{acct.display_name or acct.name}*: `${acct.balance:,.2f}` {acct.currency.upper()}\n"


def get_asset_summary_text(asset: AssetsObject, show_details: bool) -> str:
    """Returns a message with the assets and their balances."""
    if show_details:
        institution = ""
        if asset.institution_name and asset.institution_name != (asset.display_name or asset.name):
            institution = f" (_{asset.institution_name}_)"
        txt = f"*{asset.display_name or asset.name}* {institution}\n"
        txt += f"Balance: `${asset.balance:,.2f}` {asset.currency.upper()}\n"
        return txt + f"Last update: {asset.balance_as_of.strftime('%a, %b %d at %I:%M %p')}\n\n"
    else:
        return f" • *{asset.display_name or asset.name}*: `${asset.balance:,.2f}` {asset.currency.upper()}\n"


def get_crypto_summary_text(acct: CryptoObject, show_details: bool) -> str:
    if show_details:
        txt = f"*{acct.name}* _({acct.institution_name})_\n"
        txt += f"Balance: `${acct.balance:,.2f}` {get_crypto_symbol(acct.currency)}\n"
        txt += f"Last update: {acct.balance_as_of.strftime('%a, %b %d at %I:%M %p')}\n"
        return txt + f"Status: {acct.status}\n\n"
    else:
        return f" • *{acct.name}*: `${acct.balance:,.2f}` {get_crypto_symbol(acct.currency)}\n"


def get_accounts_summary_text(
    accts: list[PlaidAccountObject | AssetsObject | CryptoObject], show_details: bool, tagging: bool = True
) -> str:
    """Returns a message with the accounts and their balances."""
    by_group = {}
    for acct in accts:
        if isinstance(acct, PlaidAccountObject):
            by_group.setdefault(acct.type, []).append(acct)
        elif isinstance(acct, AssetsObject):
            by_group.setdefault(acct.type_name, []).append(acct)
        elif isinstance(acct, CryptoObject):
            by_group.setdefault("cryptocurrency", []).append(acct)

    txt = ""
    for acct_type, accts in by_group.items():
        txt += f"{get_emoji_for_account_type(acct_type)} {make_tag(acct_type, title=True, tagging=tagging)}\n\n"

        for acct in accts:
            if isinstance(acct, PlaidAccountObject):
                txt += get_plaid_account_summary_text(acct, show_details)
            elif isinstance(acct, AssetsObject):
                txt += get_asset_summary_text(acct, show_details)
            elif isinstance(acct, CryptoObject):
                txt += get_crypto_summary_text(acct, show_details)
        txt += "\n"

    return txt


async def handle_show_balances(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mask: int = SHOW_BALANCES, message_id: int | None = None
):
    """Shows all the Plaid accounts and its balances to the user."""
    lunch = get_lunch_client_for_chat_id(update.effective_chat.id)

    all_accounts = []
    if is_show_balances(mask):
        all_accounts += lunch.get_plaid_accounts()

    if is_show_assets(mask):
        all_accounts += lunch.get_assets()

    if is_show_crypto(mask):
        all_accounts += lunch.get_crypto()

    settings = get_db().get_current_settings(update.effective_chat.id)
    tagging = settings.tagging if settings else True

    msg = get_accounts_summary_text(all_accounts, is_show_details(mask), tagging=tagging)

    if message_id:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=message_id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_accounts_buttons(mask),
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_accounts_buttons(mask),
        )

        # delete the command message
        await update.message.delete()


async def handle_btn_accounts_balances(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the button press to show the balances of the accounts."""
    mask = int(update.callback_query.data.split("_")[1])
    if not is_show_balances(mask) and not is_show_assets(mask) and not is_show_crypto(mask):
        # do not allow to hide all of them
        return await update.callback_query.answer()

    await handle_show_balances(update, context, mask=mask, message_id=update.callback_query.message.message_id)


async def handle_done_balances(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Done' button press to delete the balances message."""
    await update.callback_query.message.delete()
