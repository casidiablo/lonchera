# Implementation Plan

- [x] 1. Add constants for special token values
  - Add `TOKEN_REVOKED` and `TOKEN_BLOCKED` constants to constants.py
  - These constants will be used throughout the codebase to check token status
  - _Requirements: 1.1, 1.4_

- [x] 2. Add database methods for blocked user management
  - [x] 2.1 Implement `mark_user_as_blocked` method in Persistence class
    - Set token field to TOKEN_BLOCKED constant value
    - Use SQLAlchemy update statement with chat_id filter
    - _Requirements: 1.1_
  
  - [x] 2.2 Implement `get_blocked_users` method in Persistence class
    - Query Settings table where token equals TOKEN_BLOCKED
    - Join with Transaction and Analytics tables to get counts
    - Return list of tuples with (chat_id, transaction_count, settings_count, analytics_count)
    - _Requirements: 2.1, 2.3_
  
  - [x] 2.3 Implement `is_user_blocked` method in Persistence class
    - Query Settings table for chat_id
    - Return True if token equals TOKEN_BLOCKED, False otherwise
    - _Requirements: 1.4_
  
  - [x] 2.4 Implement `delete_user_data` method in Persistence class
    - Delete all Transaction records for chat_id
    - Delete all Analytics records for chat_id
    - Delete Settings record for chat_id
    - Return dictionary with counts of deleted records from each table
    - Use transaction to ensure atomicity
    - _Requirements: 3.3_
  
  - [x] 2.5 Update `get_user_count` method to exclude blocked users
    - Modify existing query to filter out TOKEN_BLOCKED in addition to TOKEN_REVOKED
    - Use both constants in the filter condition
    - _Requirements: 1.4_

- [x] 3. Add exception handling for blocked users in messaging
  - [x] 3.1 Update `send_transaction_message` in tx_messaging.py
    - Import telegram.error.Forbidden exception
    - Wrap message sending in try-except block
    - Catch Forbidden exception and check for "bot was blocked by the user" message
    - Call `mark_user_as_blocked` when user blocks bot
    - Log warning with chat_id
    - Return -1 as sentinel value instead of raising exception
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 4. Update polling logic to skip blocked users
  - [x] 4.1 Modify `poll_transactions_on_schedule` in handlers/transactions.py
    - Import TOKEN_BLOCKED constant
    - Add check for TOKEN_BLOCKED after existing TOKEN_REVOKED check
    - Skip polling for users with token equal to TOKEN_BLOCKED
    - Log debug message when skipping blocked user
    - _Requirements: 1.4_

- [x] 5. Add admin authorization utility
  - [x] 5.1 Implement `is_admin_user` function in utils.py
    - Read ADMIN_USER_ID environment variable
    - Split by comma to support multiple admin IDs
    - Strip whitespace and convert to integers
    - Return True if chat_id is in admin list, False otherwise
    - Handle empty or missing environment variable gracefully
    - _Requirements: 4.3, 4.4_

- [x] 6. Create admin command handlers
  - [x] 6.1 Create handlers/admin.py file
    - Add necessary imports (logging, os, telegram, ContextTypes, Update)
    - Import constants, persistence, and utils modules
    - _Requirements: 2.1, 3.1, 4.1, 4.2_
  
  - [x] 6.2 Implement `handle_blocked_users` command handler
    - Check if user is admin using `is_admin_user` function
    - If not admin, send "Unauthorized" message and return
    - Call `get_blocked_users` from database
    - If no blocked users, send friendly message
    - Format response with chat_id and record counts for each user
    - Use markdown formatting with clear separation between entries
    - Send formatted message to admin
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.1_
  
  - [x] 6.3 Implement `handle_delete_user` command handler
    - Check if user is admin using `is_admin_user` function
    - If not admin, send "Unauthorized" message and return
    - Parse chat_id from command arguments
    - Validate chat_id format (must be integer)
    - Check if user exists and is blocked using `is_user_blocked`
    - If not blocked, send error message
    - Get record counts for confirmation message
    - Create inline keyboard with "Confirm Delete" and "Cancel" buttons
    - Send confirmation message with user info and buttons
    - _Requirements: 3.1, 3.2, 3.6, 4.2_
  
  - [x] 6.4 Implement `handle_btn_confirm_delete_user` callback handler
    - Extract chat_id from callback data
    - Call `delete_user_data` from database
    - Get counts of deleted records
    - Format success message with deletion counts
    - Edit original message to show success
    - _Requirements: 3.3, 3.5_
  
  - [x] 6.5 Implement `handle_btn_cancel_delete_user` callback handler
    - Delete the confirmation message
    - Send cancellation acknowledgment
    - _Requirements: 3.4_

- [ ] 7. Register admin command handlers in main.py
  - [x] 7.1 Import admin handlers
    - Add import statements for handle_blocked_users and handle_delete_user
    - Add import statements for button handlers
    - _Requirements: 2.1, 3.1_
  
  - [x] 7.2 Add command handlers to application
    - Add CommandHandler for "blocked_users" command
    - Add CommandHandler for "delete_user" command
    - Register in `add_command_handlers` function
    - _Requirements: 2.1, 3.1_
  
  - [x] 7.3 Add callback query handlers for confirmation buttons
    - Add CallbackQueryHandler for "confirmDeleteUser_" pattern
    - Add CallbackQueryHandler for "cancelDeleteUser" pattern
    - Register in `add_application_callback_query_handlers` function
    - _Requirements: 3.2, 3.3, 3.4_

- [x] 8. Update existing code to use constants
  - [x] 8.1 Replace hardcoded "revoked" strings with TOKEN_REVOKED constant
    - Update handlers/transactions.py polling logic
    - Update persistence.py get_user_count method
    - Import TOKEN_REVOKED constant in both files
    - _Requirements: 1.4_
