"""
Extensions for the telegram-python-bot library.

This module provides type-safe extensions to the telegram library classes
by monkey-patching them with additional properties while maintaining
full type safety through proper type annotations.
"""

from typing import TYPE_CHECKING

from telegram import Update as TelegramUpdate

if TYPE_CHECKING:
    # For type checking, we create a proper class that extends Update
    class Update(TelegramUpdate):
        """Extended Update class with additional properties for type checking."""

        @property
        def chat_id(self) -> int:
            """
            Property to safely extract the chat ID from a Telegram update.

            Returns:
                The chat ID as an integer

            Raises:
                ValueError: If effective_chat is None or if the chat ID is not available
            """
            ...
else:
    # At runtime, we monkey patch the actual Update class
    def _chat_id_property(self: TelegramUpdate) -> int:
        """
        Property to safely extract the chat ID from a Telegram update.

        Returns:
            The chat ID as an integer

        Raises:
            ValueError: If effective_chat is None or if the chat ID is not available
        """
        if self.effective_chat is None:
            raise ValueError("No effective chat found in update")

        chat_id = self.effective_chat.id
        if chat_id is None:
            raise ValueError("Chat ID is None")

        return chat_id

    # Add the property to the Update class
    TelegramUpdate.chat_id = property(_chat_id_property)

    # For runtime, Update is just the monkey-patched original class
    Update = TelegramUpdate


def get_chat_id(update: TelegramUpdate) -> int:
    """
    Safely extracts the chat ID from a Telegram update.

    This function provides the same functionality as the chat_id property
    but as a standalone function for backward compatibility.

    Args:
        update: The Telegram update object

    Returns:
        The chat ID as an integer

    Raises:
        ValueError: If effective_chat is None or if the chat ID is not available
    """
    if update.effective_chat is None:
        raise ValueError("No effective chat found in update")

    chat_id = update.effective_chat.id
    if chat_id is None:
        raise ValueError("Chat ID is None")

    return chat_id


__all__ = ["Update", "get_chat_id"]
