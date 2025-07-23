"""
Extensions for the telegram-python-bot library.

This module provides type-safe extensions to the telegram library classes
by monkey-patching them with additional properties while maintaining
full type safety through proper type annotations.
"""

from typing import TYPE_CHECKING

from telegram import Update as TelegramUpdate

if TYPE_CHECKING:
    from telegram._message import Message

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

        async def safe_edit_message_text(
            self,
            text: str | None = None,
            parse_mode: str | None = None,
            reply_markup=None,
            disable_web_page_preview: bool | None = None,
            **kwargs,
        ):
            """
            Safely edit message text with automatic callback query handling.

            This method provides a safe way to edit message text that:
            - Does nothing if callback_query is None
            - Automatically calls answer() on the callback query
            - Does nothing if text is None

            Args:
                text: New text of the message (does nothing if None)
                parse_mode: Send Markdown or HTML, if you want Telegram apps to show
                    bold, italic, fixed-width text or inline URLs in your bot's message.
                reply_markup: Additional interface options
                disable_web_page_preview: Disables link previews for links in this message
                **kwargs: Additional arguments passed to edit_message_text

            Returns:
                The edited message object if successful, None otherwise
            """
            ...

        async def safe_edit_message_reply_markup(
            self, reply_markup=None, answer_text: str | None = None, show_alert: bool = False, **kwargs
        ) -> Message | bool:
            """
            Safely edit message reply markup with automatic callback query handling.

            This method provides a safe way to edit message reply markup that:
            - Does nothing if callback_query is None
            - Automatically calls answer() on the callback query

            Args:
                reply_markup: New reply markup for the message
                answer_text: Text to show in the callback query answer
                show_alert: Whether to show the answer as an alert
                **kwargs: Additional arguments passed to edit_message_reply_markup

            Returns:
                The edited message object if successful, None otherwise
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

    async def _safe_edit_message_text(
        self: TelegramUpdate,
        text: str | None = None,
        parse_mode: str | None = None,
        reply_markup=None,
        disable_web_page_preview: bool | None = None,
        **kwargs,
    ):
        """
        Safely edit message text with automatic callback query handling.

        This method provides a safe way to edit message text that:
        - Does nothing if callback_query is None
        - Automatically calls answer() on the callback query
        - Does nothing if text is None

        Args:
            text: New text of the message (does nothing if None)
            parse_mode: Send Markdown or HTML, if you want Telegram apps to show
                bold, italic, fixed-width text or inline URLs in your bot's message.
            reply_markup: Additional interface options
            disable_web_page_preview: Disables link previews for links in this message
            **kwargs: Additional arguments passed to edit_message_text

        Returns:
            The edited message object if successful, None otherwise
        """
        # Do nothing if callback_query is None
        if self.callback_query is None:
            return True

        # Do nothing if text is None
        if text is None:
            return True

        # Answer the callback query first
        try:
            await self.callback_query.answer()
        except Exception:
            # does not matter much
            ...

        # Edit the message text and return the result
        return await self.callback_query.edit_message_text(
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
            **kwargs,
        )

    async def _safe_edit_message_reply_markup(
        self: TelegramUpdate, reply_markup=None, answer_text: str | None = None, show_alert: bool = False, **kwargs
    ):
        """
        Safely edit message reply markup with automatic callback query handling.

        This method provides a safe way to edit message reply markup that:
        - Does nothing if callback_query is None
        - Automatically calls answer() on the callback query

        Args:
            reply_markup: New reply markup for the message
            answer_text: Text to show in the callback query answer
            show_alert: Whether to show the answer as an alert
            **kwargs: Additional arguments passed to edit_message_reply_markup

        Returns:
            The edited message object if successful, None otherwise
        """
        # Do nothing if callback_query is None
        if self.callback_query is None:
            return None

        # Answer the callback query first
        try:
            await self.callback_query.answer(text=answer_text, show_alert=show_alert)
        except Exception:
            # does not matter much
            ...

        # Edit the message reply markup and return the result
        return await self.callback_query.edit_message_reply_markup(reply_markup=reply_markup, **kwargs)

    # Add the property and methods to the Update class
    TelegramUpdate.chat_id = property(_chat_id_property)
    TelegramUpdate.safe_edit_message_text = _safe_edit_message_text
    TelegramUpdate.safe_edit_message_reply_markup = _safe_edit_message_reply_markup

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
