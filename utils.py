import os

import regex
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from persistence import Settings, get_db
from telegram_extensions import Update
from telegram_extensions import get_chat_id as _get_chat_id

# Single-character emoji test, equivalent to `char in emoji.EMOJI_DATA` from the
# `emoji` package (which adds ~21MB of RSS for one dict lookup). Compared char by
# char against the package across all of Unicode; the only differences are regional
# indicator symbols (flag halves, deliberately not treated as standalone emoji here)
# and a handful of emoji newer than the Unicode data baked into the `regex` module,
# listed explicitly below.
_EMOJI_PRESENTATION = regex.compile(r"[\p{Emoji_Presentation}\p{Emoji_Modifier}]")
_EMOJI_PICTOGRAPHIC = regex.compile(r"[\p{Emoji}&\p{Extended_Pictographic}]")
_REGIONAL_INDICATOR = regex.compile(r"\p{Regional_Indicator}")
_EMOJI_NEWER_THAN_REGEX_DATA = "\U0001F6D8\U0001FA8A\U0001FA8E\U0001FAC8\U0001FACD\U0001FAEA\U0001FAEF"


def is_emoji(char):
    if len(char) != 1 or _REGIONAL_INDICATOR.match(char):
        return False
    return bool(_EMOJI_PRESENTATION.match(char) or _EMOJI_PICTOGRAPHIC.match(char) or char in _EMOJI_NEWER_THAN_REGEX_DATA)


def clean_md_v2(text: str) -> str:
    return (
        text.replace(" ", "")
        .replace(".", "\\.")
        .replace("!", "\\!")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("-", "\\_")
        .replace("/", "\\_")
        .strip()
    )


def make_tag(t: str, title=False, tagging=True, no_emojis=False) -> str:
    result = "".join([char for char in t if not is_emoji(char)])
    if tagging:
        result = (
            result.title()
            .replace(" ", "")
            .replace(".", "")
            .replace("*", "\\*")
            .replace("_", "\\_")
            .replace("-", "\\_")
            .replace("/", "\\_")
            .strip()
        )

    # find emojis so we can all put them at the beginning
    # otherwise tagging will break
    emojis = "".join([char for char in t if is_emoji(char)])
    if no_emojis:
        emojis = ""
    else:
        emojis += " "

    tag_char = "#" if tagging else ""

    if title:
        return f"{emojis}*{tag_char}{result}*"
    else:
        return f"{emojis}{tag_char}{result}"


def remove_emojis(text: str) -> str:
    return "".join([char for char in text if not is_emoji(char)]).strip()


class Keyboard(list):
    def __iadd__(self, other):
        self.append(other)
        return self

    def build(self, columns: int = 2) -> InlineKeyboardMarkup:
        buttons = [InlineKeyboardButton(text, callback_data=data) for (text, data) in self]
        buttons = [buttons[i : i + columns] for i in range(0, len(buttons), columns)]
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def build_from(*btns: tuple[str, str]) -> InlineKeyboardMarkup:
        if not btns:
            raise ValueError("At least one button must be provided.")

        kbd = Keyboard()
        for btn in btns:
            if btn:
                kbd += btn
        return kbd.build()


ACCOUNT_TYPE_EMOJIS = {
    "credit": "💳",
    "depository": "🏦",
    "investment": "📈",
    "cash": "💵",
    "loan": "💸",
    "real estate": "🏠",
    "vehicle": "🚗",
    "cryptocurrency": "₿",
    "employee compensation": "👨‍💼",
    "other liability": "📉",
    "other asset": "📊",
}


def get_emoji_for_account_type(acct_type: str) -> str:
    return ACCOUNT_TYPE_EMOJIS.get(acct_type, "❓")


CRYPTO_SYMBOLS = {
    "btc": "₿",
    "eth": "Ξ",
    "ltc": "Ł",
    "xrp": "X",
    "bch": "₿",
    "doge": "Ð",
    "xmr": "ɱ",
    "dash": "D",
    "xem": "ξ",
    "neo": "文",
    "xlm": "*",
    "zec": "ⓩ",
    "ada": "₳",
    "eos": "ε",
    "miota": "ι",
}


def get_crypto_symbol(crypto_symbol: str) -> str:
    return CRYPTO_SYMBOLS.get(crypto_symbol.lower(), crypto_symbol)


CONVERSATION_MSG_ID = "conversation_msg_id"


def clean_md(text: str) -> str:
    return text.replace("_", " ").replace("*", " ").replace("`", " ")


# Re-export the get_chat_id function from telegram_extensions module
get_chat_id = _get_chat_id


def ensure_token(update: Update) -> Settings:
    # make sure the user has registered a token by trying to get the settings
    # which will raise an exception if the token is not set
    chat_id = update.chat_id
    return get_db().get_current_settings(chat_id)


def is_admin_user(chat_id: int) -> bool:
    """Check if the given chat_id belongs to an admin user.

    Admin users are defined by the ADMIN_USER_ID environment variable,
    which can be a single ID or comma-separated list of IDs.

    Args:
        chat_id: The Telegram chat ID to check

    Returns:
        True if the chat_id is in the admin list, False otherwise
    """
    admin_ids = os.getenv("ADMIN_USER_ID", "")
    if not admin_ids:
        return False

    try:
        admin_id_list = [int(id.strip()) for id in admin_ids.split(",") if id.strip()]
    except ValueError:
        # Handle case where ADMIN_USER_ID contains non-integer values
        return False
    else:
        return chat_id in admin_id_list
