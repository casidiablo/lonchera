import logging

EXPECTING_TOKEN = "token"
EXPECTING_TIME_ZONE = "time_zone"
RENAME_PAYEE = "rename_payee"
EDIT_NOTES = "edit_notes"
SET_TAGS = "set_tags"
AMAZON_EXPORT = "amazon_export"

expectations: dict[int, dict[str, str] | None] = {}


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("expectations")


def get_expectation(chat_id: int) -> dict[str, str] | None:
    return expectations.get(chat_id, None)


def set_expectation(chat_id: int, expectation: dict[str, str]):
    logger.info(f"Setting expectation for chat_id {chat_id}: {expectation}")
    expectations[chat_id] = expectation


def clear_expectation(chat_id: int) -> dict[str, str] | None:
    prev = expectations.get(chat_id)
    expectations[chat_id] = None
    return prev
