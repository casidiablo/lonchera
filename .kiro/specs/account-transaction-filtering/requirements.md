# Requirements Document

## Introduction

This feature enables users to filter out transactions from specific accounts so that the Lonchera Bot will not send notifications for transactions from those accounts. Users can configure this through the settings menu by toggling accounts to ignore, and the system will store these preferences as a comma-separated list of account IDs in the database.

## Glossary

- **Lonchera Bot**: The Telegram bot application that integrates with Lunch Money
- **Lunch Money Account**: A financial account (bank account, credit card, etc.) connected to the user's Lunch Money profile
- **Account ID**: The unique identifier for a Lunch Money account
- **Settings Table**: Database table storing per-chat configuration including ignored account preferences
- **Ignored Accounts**: Comma-separated string of account IDs for which transaction notifications should be suppressed
- **Transaction Polling**: The process where the bot checks for new transactions and sends notifications
- **Settings Menu**: The Telegram bot interface for configuring user preferences
- **Transactions Handling Menu**: Sub-menu within Settings for transaction-related preferences

## Requirements

### Requirement 1

**User Story:** As a user, I want to access account filtering settings through the settings menu, so that I can configure which accounts should be ignored for transaction notifications.

#### Acceptance Criteria

1. WHEN a user navigates to Settings → Transactions Handling, THEN the Lonchera Bot SHALL display an "Account Filtering" option
2. WHEN a user selects "Account Filtering", THEN the Lonchera Bot SHALL fetch and display a list of all their Lunch Money accounts
3. WHEN displaying accounts, THEN the Lonchera Bot SHALL show each account name with a toggle button indicating current ignore status
4. WHEN an account is currently ignored, THEN the Lonchera Bot SHALL display "🔕 Ignored" next to the account name
5. WHEN an account is not ignored, THEN the Lonchera Bot SHALL display "🔔 Active" next to the account name

### Requirement 2

**User Story:** As a user, I want to toggle the ignore status of individual accounts, so that I can control which accounts generate transaction notifications.

#### Acceptance Criteria

1. WHEN a user clicks on an account toggle button, THEN the Lonchera Bot SHALL update the ignore status for that account
2. WHEN toggling from active to ignored, THEN the Lonchera Bot SHALL add the account ID to the ignored accounts list and update the button to show "🔕 Ignored"
3. WHEN toggling from ignored to active, THEN the Lonchera Bot SHALL remove the account ID from the ignored accounts list and update the button to show "🔔 Active"
4. WHEN updating ignore status, THEN the Lonchera Bot SHALL save the changes to the Settings Table as a comma-separated string of account IDs
5. WHEN the user returns to the account filtering menu, THEN the Lonchera Bot SHALL display the current ignore status for all accounts

### Requirement 3

**User Story:** As a user, I want the system to respect my account filtering preferences during transaction polling, so that I don't receive notifications for transactions from ignored accounts.

#### Acceptance Criteria

1. WHEN the Lonchera Bot polls for new transactions, THEN the Lonchera Bot SHALL check each transaction's account ID against the user's ignored accounts list
2. WHEN a transaction's account ID is in the ignored accounts list, THEN the Lonchera Bot SHALL skip sending a notification for that transaction
3. WHEN a transaction's account ID is not in the ignored accounts list, THEN the Lonchera Bot SHALL process and send the transaction notification normally
4. WHEN parsing the ignored accounts list, THEN the Lonchera Bot SHALL handle empty strings, whitespace, and malformed data gracefully
5. WHEN no accounts are ignored (empty or null ignored accounts field), THEN the Lonchera Bot SHALL process all transactions normally

### Requirement 4

**User Story:** As a system administrator, I want the ignored accounts data to be stored persistently in the database, so that user preferences are maintained across bot restarts.

#### Acceptance Criteria

1. WHEN storing ignored account preferences, THEN the Lonchera Bot SHALL add a new "ignored_accounts" column to the Settings Table
2. WHEN multiple accounts are ignored, THEN the Lonchera Bot SHALL store them as a comma-separated string of account IDs (e.g., "123,456,789")
3. WHEN no accounts are ignored, THEN the Lonchera Bot SHALL store an empty string or NULL in the ignored_accounts field
4. WHEN retrieving ignored accounts, THEN the Lonchera Bot SHALL parse the comma-separated string into a list of account IDs
5. WHEN the ignored_accounts field is NULL or empty, THEN the Lonchera Bot SHALL treat it as an empty list of ignored accounts

### Requirement 5

**User Story:** As a user, I want clear feedback when managing account filtering settings, so that I understand the current state and any changes I make.

#### Acceptance Criteria

1. WHEN a user successfully toggles an account's ignore status, THEN the Lonchera Bot SHALL display a confirmation message indicating the change
2. WHEN displaying the account filtering menu, THEN the Lonchera Bot SHALL show a summary of how many accounts are currently ignored
3. WHEN there are no accounts to display, THEN the Lonchera Bot SHALL show a message indicating no accounts are available
4. WHEN there's an error fetching account data, THEN the Lonchera Bot SHALL display an appropriate error message and suggest trying again
5. WHEN returning to the main settings menu, THEN the Lonchera Bot SHALL reflect any changes made to account filtering preferences