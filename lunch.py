from lunchable import LunchMoney

from errors import NoLunchTokenError
from persistence import get_db

lunch_clients_cache: dict[int, LunchMoney] = {}


def get_lunch_client(token: str) -> LunchMoney:
    return LunchMoney(access_token=token)


def get_lunch_client_for_chat_id(chat_id: int) -> LunchMoney:
    if chat_id in lunch_clients_cache:
        return lunch_clients_cache[chat_id]

    token = get_db().get_token(chat_id)
    if token is None:
        raise NoLunchTokenError("No token registered for this chat")

    lunch_clients_cache[chat_id] = get_lunch_client(token)
    return lunch_clients_cache[chat_id]


def get_lunch_money_token_for_chat_id(chat_id: int) -> str:
    token = get_db().get_token(chat_id)
    if token is None:
        raise NoLunchTokenError("No token registered for this chat")
    return token
