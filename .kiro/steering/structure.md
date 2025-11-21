---
inclusion: always
---

# Project Structure

## Root Level Files

- **main.py**: Application entry point, sets up Telegram handlers and event loop
- **persistence.py**: Database models and operations (SQLAlchemy)
- **lunch.py**: Lunch Money API client wrapper
- **utils.py**: Shared utilities (keyboard builders, emoji helpers, markdown utils)
- **telegram_extensions.py**: Custom Telegram types and extensions
- **tx_messaging.py**: Transaction message rendering and formatting
- **errors.py**: Custom exception classes
- **constants.py**: Application constants
- **manual_tx.py**: Manual transaction creation via web app
- **web_server.py**: Status monitoring web server

## Handler Organization

All handlers live in `handlers/` directory:

- **transactions.py**: Core transaction handling (polling, categorization, review)
- **budget.py**: Budget display and navigation
- **balances.py**: Account balance display
- **audio.py**: Voice message transcription
- **general.py**: Generic commands (start, cancel, file upload)
- **syncing.py**: Manual resync operations
- **analytics.py**: Stats and status reporting
- **categorization.py**: AI-powered categorization logic
- **expectations.py**: User input expectation management
- **lunch_money_agent.py**: AI agent for natural language interactions
- **amz.py**: Amazon transaction sync

### Settings Handlers

Settings are organized in `handlers/settings/`:

- **general.py**: Settings menu navigation
- **session.py**: Token management, logout, Plaid refresh
- **schedule_rendering.py**: Polling interval, timezone, display options
- **transactions_handling.py**: Auto-review, auto-categorize toggles
- **ai.py**: AI agent configuration (model, language, transcription)

### AI Tools

AI-related tools in `handlers/aitools/`:

- **tools.py**: DSPy tools for AI agent capabilities

## Handler Pattern

Handlers follow consistent naming:

- Commands: `handle_<command_name>` (e.g., `handle_start`, `handle_check_transactions`)
- Button callbacks: `handle_btn_<action>` (e.g., `handle_btn_skip_transaction`)
- Callback patterns match button data prefixes (e.g., `skip_` → `handle_btn_skip_transaction`)

## Database Schema

Three main tables (see `persistence.py`):

- **Transaction**: Links Telegram messages to Lunch Money transactions
- **Settings**: Per-chat configuration (tokens, preferences, AI settings)
- **Analytics**: Usage metrics and statistics

## Key Patterns

- **Async/await**: All handlers are async functions
- **Context passing**: Use `ContextTypes.DEFAULT_TYPE` for Telegram context
- **Update objects**: Custom `Update` class from `telegram_extensions`
- **Database access**: Use `get_db()` singleton from `persistence.py`
- **Lunch Money client**: Use `get_lunch_client_for_chat_id(chat_id)` from `lunch.py`
- **Logging**: Create module-level loggers: `logger = logging.getLogger("module_name")`
