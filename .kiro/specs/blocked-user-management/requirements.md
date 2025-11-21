# Requirements Document

## Introduction

This feature enables automatic detection and management of users who have blocked the Lonchera Telegram bot. When a user blocks the bot, the system should mark them as disabled and provide admin commands to review and delete disabled users along with their associated data.

## Glossary

- **Lonchera Bot**: The Telegram bot application that integrates with Lunch Money
- **Lonchera Bot**: The Telegram bot application that integrates with Lunch Money
- **Blocked User**: A Telegram user who has blocked the Lonchera Bot, preventing message delivery
- **Admin User**: A user with elevated privileges to manage blocked users
- **User Data**: All database records associated with a user including settings, transactions, and analytics
- **Settings Table**: Database table storing per-chat configuration with a token field
- **Transaction Table**: Database table linking Telegram messages to Lunch Money transactions
- **Analytics Table**: Database table storing usage metrics
- **Token Field**: String field in Settings Table that stores API token or special values ("revoked", "blocked")

## Requirements

### Requirement 1

**User Story:** As the system, I want to automatically detect when a user blocks the bot, so that I can mark them as blocked and stop attempting to send messages.

#### Acceptance Criteria

1. WHEN the Lonchera Bot receives a `telegram.error.Forbidden` exception with message "bot was blocked by the user", THEN the Lonchera Bot SHALL set the Token Field to "blocked" for the associated chat_id in the Settings Table
2. WHEN a user is marked as blocked, THEN the Lonchera Bot SHALL log the event with the chat_id
3. WHEN the Lonchera Bot attempts to send a message to a blocked user, THEN the Lonchera Bot SHALL skip the message delivery without raising an exception
4. WHEN the Lonchera Bot polls for transactions, THEN the Lonchera Bot SHALL exclude users with Token Field equal to "blocked" from the polling process

### Requirement 2

**User Story:** As an admin user, I want to view a list of blocked users, so that I can review which users have blocked the bot and decide whether to delete their data.

#### Acceptance Criteria

1. WHEN an Admin User sends the `/blocked_users` command, THEN the Lonchera Bot SHALL respond with a list of all users where Token Field equals "blocked" including their chat_id
2. IF there are no blocked users, THEN the Lonchera Bot SHALL respond with a message indicating no blocked users exist
3. WHEN displaying blocked users, THEN the Lonchera Bot SHALL include the count of database records associated with each user (transactions, settings, analytics)
4. WHEN displaying blocked users, THEN the Lonchera Bot SHALL format the response with clear separation between each user entry

### Requirement 3

**User Story:** As an admin user, I want to delete a blocked user and their data, so that I can clean up the database and remove users who are no longer using the bot.

#### Acceptance Criteria

1. WHEN an Admin User sends the `/delete_user <chat_id>` command, THEN the Lonchera Bot SHALL respond with a confirmation message showing the user's chat_id and data count
2. WHEN the confirmation message is displayed, THEN the Lonchera Bot SHALL provide inline buttons for "Confirm Delete" and "Cancel"
3. WHEN an Admin User clicks "Confirm Delete", THEN the Lonchera Bot SHALL delete all records from the Transaction Table, Settings Table, and Analytics Table associated with the chat_id
4. WHEN an Admin User clicks "Cancel", THEN the Lonchera Bot SHALL dismiss the confirmation message without deleting any data
5. WHEN user deletion completes successfully, THEN the Lonchera Bot SHALL respond with a success message indicating the number of records deleted from each table
6. IF the specified chat_id does not exist or Token Field is not "blocked", THEN the Lonchera Bot SHALL respond with an error message indicating the user was not found or is not blocked

### Requirement 4

**User Story:** As an admin user, I want only authorized users to access blocked user management commands, so that regular users cannot view or delete other users' data.

#### Acceptance Criteria

1. WHEN a non-Admin User sends the `/blocked_users` command, THEN the Lonchera Bot SHALL respond with an "Unauthorized" message
2. WHEN a non-Admin User sends the `/delete_user` command, THEN the Lonchera Bot SHALL respond with an "Unauthorized" message
3. WHEN the Lonchera Bot starts, THEN the Lonchera Bot SHALL load the list of Admin User chat_ids from the ADMIN_USER_ID environment variable
4. WHEN checking admin privileges, THEN the Lonchera Bot SHALL verify the requesting user's chat_id is in the Admin User list
