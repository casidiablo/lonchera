from typing import Dict, Optional


EXPECTING_TOKEN = "token"
EXPECTING_TIME_ZONE = "time_zone"
RENAME_PAYEE = "rename_payee"
EDIT_NOTES = "edit_notes"
SET_TAGS = "set_tags"
AMAZON_EXPORT = "amazon_export"

expectations: Dict[int, Optional[Dict[str, str]]] = {}


def get_expectation(chat_id: int) -> Optional[Dict[str, str]]:
    return expectations.get(chat_id, None)


def set_expectation(chat_id: int, expectation: Dict[str, str]):
    expectations[chat_id] = expectation


def clear_expectation(chat_id: int) -> Dict[str, str]:
    prev = expectations[chat_id]
    expectations[chat_id] = None
    return prev
