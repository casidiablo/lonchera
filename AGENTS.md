# Lonchera — Agent Instructions

Lonchera is a Telegram bot (Python 3.13+, async) that integrates with the
[Lunch Money](https://lunchmoney.app) API to manage and track personal finances.

---

## Build / Lint / Test Commands

**Package manager:** `uv` (not pip, not poetry).

```bash
# Format + lint — always run both before committing
uv run ruff format .
uv run ruff check .

# Run all tests
python -m pytest tests/ -v

# Run a single test
python -m pytest tests/test_file.py::test_name -v

# Filter tests by keyword
python -m pytest -k "keyword" -v
```

> Note: `tests/` is currently empty. `handlers/aitools/test_agent.py` is a
> standalone CLI tool for manually testing the AI agent — not a pytest file.

---

## Project Structure

```
├── main.py               # Entry point: wires handlers, starts bot + web server
├── persistence.py        # SQLAlchemy ORM models + get_db() singleton
├── lunch.py              # Lunch Money API client factory (chat-level caching)
├── utils.py              # Keyboard builder, emoji helpers, ensure_token()
├── telegram_extensions.py# Monkey-patched Update class with safe_edit helpers
├── tx_messaging.py       # Transaction message rendering + buttons
├── budget_messaging.py   # Budget message rendering + buttons
├── errors.py             # Custom exceptions — constants.py: app-wide constants
├── handlers/
│   ├── transactions.py   # Polling, review, categorize, tags, notes
│   ├── budget.py         # Budget display and navigation
│   ├── general.py        # /start, cancel, file upload, message routing
│   ├── categorization.py # AI-powered categorization
│   ├── ai_agent.py       # Natural language AI agent handler
│   ├── admin.py          # Admin-only commands (backup, user mgmt)
│   ├── expectations.py   # Reply expectation system (notes, rename, tags)
│   ├── settings/         # Per-chat settings submenu handlers
│   └── aitools/          # DSPy agent engine, tools, and CLI test script
└── tests/                # Pytest tests (currently empty)
```

---

## Code Style

### Formatting (enforced by ruff — see `pyproject.toml`)

- **Line length:** 120 chars (`E501` ignored). **Indent:** 4 spaces. **Quotes:** double only.
- **Ruff rules:** `E`, `F`, `I`, `UP`, `N`, `W`, `C90`, `B`, `C4`, `TID`, `PIE`, `PL`, `RUF`, `TRY`, `TC`, `FURB`
- **Max cyclomatic complexity:** 12

### Naming Conventions

| Entity | Convention | Examples |
|---|---|---|
| Variables & functions | `snake_case` | `chat_id`, `fetch_transactions` |
| Command handlers | `handle_<command>` | `handle_start`, `handle_check_transactions` |
| Button callback handlers | `handle_btn_<action>` | `handle_btn_skip_transaction` |
| Classes | `PascalCase` | `Persistence`, `Settings`, `Keyboard` |
| Constants | `UPPER_CASE` | `NOTES_MAX_LENGTH`, `TOKEN_REVOKED` |
| Private/internal helpers | `_leading_underscore` | `_apply_account_filtering` |
| Module-level loggers | `logger` | `logger = logging.getLogger("module_name")` |

---

## Imports

All imports at the **top of the file**. Order: **stdlib → third-party → local** (ruff isort).
Use `TYPE_CHECKING` guards for type-only imports to avoid circular deps.

```python
import logging
from datetime import UTC, datetime

from lunchable.models import TransactionObject
from telegram.ext import ContextTypes

from constants import NOTES_MAX_LENGTH
from persistence import get_db
from telegram_extensions import Update  # NOT from telegram directly
```

## Type Hints

- **Required** for all function signatures.
- Use `str | None` (not `Optional[str]`), `list[str]` (not `List[str]`).
- Use `Mapped[...]` for SQLAlchemy columns, `pydantic.BaseModel` for AI responses.

## Logging & Error Handling

- **Never `print()`** — use `logging`. Every module: `logger = logging.getLogger("name")`
- Use `logger.exception()` in `except` blocks (auto-includes traceback).
- No bare `except:` — always specify a type. `except Exception` only as last resort.
- Custom exceptions go in `errors.py`.
- In handlers, surface errors as user-visible alerts:
```python
except Exception as e:
    await query.answer(text=f"Error: {e!s}", show_alert=True)
```

---

## Key Patterns

### Handler Registration (main.py)

Handlers are registered in `setup_handlers()` via three groups:
- `add_command_handlers(app)` — `CommandHandler` for `/start`, `/review_transactions`, etc.
- `add_settings_callback_query_handlers(app)` — regex-matched `CallbackQueryHandler` for settings
- `add_application_callback_query_handlers(app)` — regex-matched callbacks for tx/budget actions

### Telegram Update

Import `Update` from `telegram_extensions`, **not** `telegram`. It monkey-patches
`telegram.Update` at runtime with: `chat_id`, `message_id`, `callback_data_suffix`,
`safe_edit_message_text()`, `safe_edit_message_reply_markup()`, `safe_delete_message()`.

### Handler Signatures

```python
async def handle_<command>(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    ...

async def handle_btn_<action>(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    ...
```

### API Client & Database

- `get_lunch_client_for_chat_id(chat_id)` from `lunch.py` — cached per chat_id.
- `ensure_token(update)` from `utils.py` — validates token exists, returns `Settings`.
- `get_db()` from `persistence.py` returns the singleton `Persistence` instance.
- Use SQLAlchemy ORM — avoid raw SQL.

### Async Rules

- All handlers are `async def`. Use `await` for every async call.
- `asyncio.run()` only in `main.py` entry point — never inside handlers.
- Database ops (SQLAlchemy) are synchronous; don't `await` them.

### AI Agent Tools (handlers/aitools/tools.py)

Each tool takes `chat_id: int` as first param, calls `get_lunch_client_for_chat_id()`,
and returns JSON strings. Agent config uses `dspy.Signature` + `dspy.ReAct`.
