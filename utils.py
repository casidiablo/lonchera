from typing import List, Optional
from lunchable.models import TransactionObject
import emoji
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from persistence import Settings, get_db


def is_emoji(char):
    return char in emoji.EMOJI_DATA


def make_tag(t: str, title=False, tagging=True, no_emojis=False) -> str:
    result = ""
    if tagging:
        result = "".join([char for char in t if char not in emoji.EMOJI_DATA])
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
    emojis = "".join([char for char in t if char in emoji.EMOJI_DATA])
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


def find_related_tx(
    tx: TransactionObject, txs: List[TransactionObject]
) -> Optional[TransactionObject]:
    for t in txs:
        if t.amount == -tx.amount and (t.date == tx.date or t.payee == t.payee):
            return t
    return None


class Keyboard(list):
    def __iadd__(self, other):
        self.append(other)
        return self

    def build(self, columns: int = 2) -> InlineKeyboardMarkup:
        buttons = [
            InlineKeyboardButton(text, callback_data=data) for (text, data) in self
        ]
        buttons = [buttons[i : i + columns] for i in range(0, len(buttons), columns)]
        return InlineKeyboardMarkup(buttons)

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


def ensure_token(update: Update) -> Settings:
    # make sure the user has registered a token by trying to get the settings
    # which will raise an exception if the token is not set
    return get_db().get_current_settings(update.effective_chat.id)
