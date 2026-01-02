# Implementation Plan: Account Transaction Filtering

## Overview

This implementation plan breaks down the account transaction filtering feature into discrete coding tasks. The approach follows the existing Lonchera bot patterns: database schema extension, settings UI integration, and transaction processing modification.

## Tasks

- [x] 1. Extend database schema and add persistence methods
  - Add `ignored_accounts` column to Settings table
  - Implement `update_ignored_accounts()` method to store list of account IDs as comma-separated string
  - Implement `get_ignored_accounts_list()` method to parse comma-separated string into list of integers
  - Handle edge cases: empty/null values, malformed strings, invalid account IDs
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 2. Create account filtering settings handler
  - Create `handlers/settings/account_filtering.py` module
  - Implement `get_account_filtering_text()` to render menu with account list and ignore status
  - Implement `get_account_filtering_buttons()` to create toggle buttons for each account
  - Implement `handle_account_filtering_settings()` main menu handler
  - Fetch user accounts from Lunch Money API and display with current ignore status
  - Show account count summary and handle empty account lists
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 5.2, 5.3_

- [x] 3. Implement account toggle functionality
  - Implement `handle_btn_toggle_account_ignore()` callback handler
  - Toggle account ignore status in database using account ID from callback data
  - Update UI immediately to reflect new ignore status
  - Provide confirmation feedback to user
  - Handle callback data parsing and validation
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 5.1_

- [x] 4. Integrate account filtering into settings menu
  - Add "Account Filtering" button to `handlers/settings/transactions_handling.py`
  - Update `get_transactions_handling_text()` and `get_transactions_handling_buttons()`
  - Register new callback handlers in main application
  - Ensure navigation flow works correctly between menus
  - _Requirements: 1.1_

- [x] 5. Implement transaction filtering logic
  - Modify `check_transactions_and_telegram_them()` in `handlers/transactions.py`
  - Add account filtering before processing transactions
  - Filter out transactions where `transaction.account_id` is in ignored accounts list
  - Ensure filtering works for both pending and posted transactions
  - Handle empty ignored accounts list (process all transactions normally)
  - _Requirements: 3.1, 3.2, 3.3, 3.5_

- [x] 6. Add error handling and edge cases
  - Handle Lunch Money API errors when fetching accounts
  - Display user-friendly error messages and suggest retry
  - Handle malformed ignored accounts data gracefully
  - Add logging for account filtering operations
  - Handle account deletion scenarios (references to deleted accounts)
  - _Requirements: 3.4, 5.4_

- [ ] 7. Ensure UI state persistence and consistency
  - Verify that account filtering preferences persist across bot restarts
  - Ensure UI reflects current state when returning to account filtering menu
  - Test navigation between different settings menus maintains state
  - Verify changes are immediately visible in transaction processing
  - _Requirements: 2.5, 5.5_

- [ ] 8. Final integration and testing
  - Test complete workflow: settings navigation → account filtering → transaction processing
  - Verify database migrations work correctly
  - Ensure all callback handlers are properly registered
  - Test with various account configurations and ignore states
  - Validate that ignored accounts don't generate notifications
  - _Requirements: All_

## Notes

- Each task builds incrementally on previous tasks
- Database changes in task 1 are required for all subsequent tasks
- Settings UI (tasks 2-4) can be developed and tested independently of transaction filtering (task 5)
- Error handling (task 6) should be integrated throughout development
- Final integration (task 8) validates the complete feature works end-to-end
- **EVERY CHANGE must be checked for errors by running: `uv run ruff check .`**