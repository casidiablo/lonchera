"""
This module contains constants used throughout the application.
"""

# Transaction notes have a character limit of 350 in Lunch Money API
NOTES_MAX_LENGTH = 350

# Special token values for user status
TOKEN_REVOKED = "revoked"  # User's Lunch Money API token was revoked
TOKEN_BLOCKED = "blocked"  # User has blocked the Telegram bot
