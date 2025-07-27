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

        async def safe_delete_message(self, answer_text: str | None = None, show_alert: bool = False, **kwargs) -> bool:
            """
            Safely delete message with automatic callback query handling.

            This method provides a safe way to delete a message that:
            - Does nothing if callback_query is None
            - Automatically calls answer() on the callback query
            - Deletes the message safely

            Args:
                answer_text: Text to show in the callback query answer
                show_alert: Whether to show the answer as an alert
                **kwargs: Additional arguments passed to delete

            Returns:
                True if successful, False otherwise
            """
            ...

        @property
        def callback_data_suffix(self) -> str:
            """
            Property to safely extract the substring after the first underscore in callback_query.data.

            Returns:
                The substring after the first underscore in callback_query.data.

            Raises:
                ValueError: If callback_query, callback_query.data is None, or no substring after '_'.
            """
            ...

        @property
        def message_id(self) -> int:
            """
            Property to safely extract the message ID from a Telegram update.

            Returns:
                The chat ID as an integer

            Raises:
                ValueError: if callback_query or any other required attribute is None.
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

        # Edit the message text and return the result
        result = await self.callback_query.edit_message_text(
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
            **kwargs,
        )

        # Answer the callback query first
        try:
            await self.callback_query.answer()
        except Exception:
            # does not matter much
            ...

        return result

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

        # Edit the message reply markup and return the result
        result = await self.callback_query.edit_message_reply_markup(reply_markup=reply_markup, **kwargs)

        # Answer the callback query first
        try:
            await self.callback_query.answer(text=answer_text, show_alert=show_alert)
        except Exception:
            # does not matter much
            ...

        return result

    async def _safe_delete_message(
        self: TelegramUpdate, answer_text: str | None = None, show_alert: bool = False, **kwargs
    ) -> bool:
        """
        Safely delete message with automatic callback query handling.

        This method provides a safe way to delete a message that:
        - Does nothing if callback_query is None
        - Automatically calls answer() on the callback query
        - Deletes the message safely

        Args:
            answer_text: Text to show in the callback query answer
            show_alert: Whether to show the answer as an alert
            **kwargs: Additional arguments passed to delete

        Returns:
            True if successful, False otherwise
        """
        # Do nothing if callback_query is None
        if self.callback_query is None:
            return False

        # Delete the message and return the result
        try:
            await self.callback_query.message.delete(**kwargs)

            # Answer the callback query first
            try:
                await self.callback_query.answer(text=answer_text, show_alert=show_alert)
            except Exception:
                # does not matter much
                ...
        except Exception:
            return False
        else:
            return True

    def _callback_data_suffix_property(self: TelegramUpdate) -> str:
        """
        Property to safely extract the substring after the first underscore in callback_query.data.

        Returns:
            The substring after the first underscore in callback_query.data.

        Raises:
            ValueError: If callback_query, callback_query.data is None, or no substring after '_'.
        """
        if self.callback_query is None or self.callback_query.data is None:
            raise ValueError("No callback_query or callback_query.data found in update")

        parts = self.callback_query.data.split("_", 1)
        if not parts[1]:
            raise ValueError("No substring after '_' in callback_query.data")

        return parts[1]

    def _message_id_property(self: TelegramUpdate) -> int:
        """
        Property to safely extract the message ID from a Telegram update's callback query.

        Returns:
            The message ID as an integer

        Raises:
            ValueError: If callback_query or message is None, or message_id is not available
        """
        if self.callback_query is None or self.callback_query.message is None:
            raise ValueError("No callback_query or message found in update")

        message_id = self.callback_query.message.message_id
        if message_id is None:
            raise ValueError("Message ID is None")

        return message_id

    # Add the property and methods to the Update class
    TelegramUpdate.chat_id = property(_chat_id_property)
    TelegramUpdate.safe_edit_message_text = _safe_edit_message_text
    TelegramUpdate.safe_edit_message_reply_markup = _safe_edit_message_reply_markup
    TelegramUpdate.safe_delete_message = _safe_delete_message
    TelegramUpdate.callback_data_suffix = property(_callback_data_suffix_property)
    TelegramUpdate.message_id = property(_message_id_property)

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
