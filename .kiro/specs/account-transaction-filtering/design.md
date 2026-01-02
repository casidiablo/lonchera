# Design Document: Account Transaction Filtering

## Overview

This feature adds the ability for users to filter out transaction notifications from specific Lunch Money accounts. Users can configure which accounts to ignore through the existing Settings → Transactions Handling menu. The system will store ignored account IDs as a comma-separated string in the database and filter transactions during the polling process.

## Architecture

The feature integrates into the existing Lonchera bot architecture by:

1. **Database Layer**: Adding a new `ignored_accounts` column to the Settings table
2. **Settings UI Layer**: Extending the transactions handling settings menu with account filtering options
3. **Transaction Processing Layer**: Modifying the transaction polling logic to respect account filtering preferences
4. **API Integration Layer**: Using the Lunch Money API to fetch account information for the settings UI

## Components and Interfaces

### Database Schema Changes

**Settings Table Extension**:
```python
class Settings(Base):
    # ... existing fields ...
    ignored_accounts: Mapped[str | None] = mapped_column(String, nullable=True)
```

**New Database Methods**:
```python
def update_ignored_accounts(self, chat_id: int, ignored_account_ids: list[int]) -> None
def get_ignored_accounts_list(self, chat_id: int) -> list[int]
```

### Settings Menu Extension

**New Handler Module**: `handlers/settings/account_filtering.py`

**Core Functions**:
- `get_account_filtering_text(chat_id: int) -> str`: Renders the account filtering menu text
- `get_account_filtering_buttons(chat_id: int) -> InlineKeyboardMarkup`: Creates toggle buttons for each account
- `handle_account_filtering_settings(update, context)`: Main menu handler
- `handle_btn_toggle_account_ignore(update, context)`: Toggle handler for individual accounts

**Integration Points**:
- Add "Account Filtering" button to `handlers/settings/transactions_handling.py`
- Register new callback handlers in main application

### Transaction Filtering Logic

**Modified Functions**:
- `check_transactions_and_telegram_them()`: Add account filtering before processing transactions

**Filtering Implementation**:
```python
# Filter out transactions from ignored accounts
ignored_accounts = get_db().get_ignored_accounts_list(chat_id)
if ignored_accounts:
    transactions_to_process = [tx for tx in transactions_to_process if tx.account_id not in ignored_accounts]
```

### Lunch Money API Integration

**Account Data Fetching**:
- Use `lunch.get_accounts()` to retrieve user's account list
- Handle API errors gracefully with user-friendly messages

## Data Models

### Settings Table Schema

```python
class Settings(Base):
    # ... existing fields ...
    ignored_accounts: Mapped[str | None] = mapped_column(String, nullable=True)
    # Format: "123,456,789" (comma-separated account IDs)
```

### Account Data Structure

```python
@dataclass
class AccountInfo:
    id: int
    name: str
    type: str
    is_ignored: bool
```

### Ignored Accounts Data Handling

The system will handle ignored accounts as a comma-separated string in the database:
- **Storage Format**: "123,456,789" (comma-separated account IDs)
- **Parsing**: `[int(id.strip()) for id in ignored_accounts_str.split(",") if id.strip()]` 
- **Formatting**: `",".join(str(id) for id in account_ids)`

## Correctness Properties

Let me analyze the acceptance criteria for testable properties:
*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

After analyzing the acceptance criteria, I identified several properties that can be consolidated:
- Properties 1.4 and 1.5 (display indicators) can be combined into one comprehensive display property
- Properties 2.2 and 2.3 (toggle behaviors) can be combined into one toggle state property  
- Properties 3.2 and 3.3 (filtering behaviors) can be combined into one filtering property
- Properties 4.2 and 4.4 (serialization/deserialization) can be combined into one round-trip property

### Core Properties

**Property 1: Account Display Format**
*For any* account list displayed in the filtering menu, each account should show its name with the correct status indicator ("🔕 Ignored" for ignored accounts, "🔔 Active" for active accounts)
**Validates: Requirements 1.3, 1.4, 1.5**

**Property 2: Toggle State Consistency**
*For any* account toggle operation, the account's ignore status should be updated in the database and the UI should reflect the new state immediately
**Validates: Requirements 2.1, 2.2, 2.3**

**Property 3: Transaction Filtering Logic**
*For any* transaction and ignored accounts list, transactions from ignored accounts should be skipped while transactions from non-ignored accounts should be processed normally
**Validates: Requirements 3.1, 3.2, 3.3**

**Property 4: Ignored Accounts Serialization Round-trip**
*For any* list of account IDs, serializing to comma-separated string then deserializing should produce an equivalent list
**Validates: Requirements 2.4, 4.2, 4.4**

**Property 5: UI State Persistence**
*For any* changes made to account filtering preferences, returning to the menu should display the current state correctly
**Validates: Requirements 2.5, 5.5**

**Property 6: User Feedback Consistency**
*For any* successful account toggle operation, the system should provide confirmation feedback and update the account count summary
**Validates: Requirements 5.1, 5.2**

## Error Handling

### API Error Handling
- **Lunch Money API failures**: Display user-friendly error messages and suggest retry
- **Network timeouts**: Graceful degradation with cached account data when possible
- **Authentication errors**: Redirect to token refresh flow

### Data Validation
- **Malformed ignored accounts strings**: Parse gracefully, ignore invalid entries, log warnings
- **Invalid account IDs**: Filter out non-numeric or negative values during parsing
- **Database errors**: Rollback changes and display error messages to user

### Edge Cases
- **Empty account lists**: Display "No accounts available" message
- **All accounts ignored**: Show warning about missing all notifications
- **Account deletion**: Handle references to deleted accounts gracefully

The property tests will validate that the core correctness properties hold across all generated input combinations, providing comprehensive coverage through randomized testing.