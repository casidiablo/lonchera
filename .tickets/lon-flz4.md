---
id: lon-flz4
status: closed
deps: []
links: []
created: 2026-03-27T17:07:23Z
type: feature
priority: 2
assignee: Cristian
tags: [settings, transactions, lunchmoney, api]
---
# Add 'Sync delete with Lunch Money' setting

Add a new boolean setting 'sync_delete_with_lunchmoney' (disabled by default) under the Transactions Handling settings panel. When enabled, deleting a Telegram transaction message will also delete the corresponding transaction from Lunch Money via the new v2 DELETE /transactions/{id} API endpoint.

## Design


## API
- New endpoint: DELETE https://dev.lunchmoney.app/v2/transactions/{id}
- No native lunchable method — call via LunchMoney.amake_request('DELETE', ['v2', 'transactions', tx_id])
- Determine the correct base URL for v2 (may differ from v1 base URL used by lunchable)

## Files to change
1. persistence.py — add 'sync_delete_with_lunchmoney: Mapped[bool] = mapped_column(Boolean, default=False)' column + 'update_sync_delete_with_lunchmoney(chat_id, value)' method
2. handlers/settings/transactions_handling.py — add ➎ setting entry to text/buttons, add toggle handler
3. handlers/transactions.py — in the skip/delete button handler, check setting and call Lunch Money API when enabled
4. main.py — register the new toggle callback handler


## Acceptance Criteria


- Setting appears in the Transactions Handling settings panel, disabled by default
- Toggling the setting persists across bot restarts
- When disabled (default): deleting a Telegram transaction message has no effect on Lunch Money
- When enabled: deleting a Telegram transaction message also calls DELETE /v2/transactions/{id} on Lunch Money
- If the Lunch Money API call fails, user sees an alert; the Telegram message is NOT deleted (atomic behavior)


