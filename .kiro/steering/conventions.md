---
inclusion: always
---

# Coding Conventions

## Code Style

- **Line length**: 120 characters max
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: Double quotes only
- **Naming**:
  - `snake_case` for variables and functions
  - `PascalCase` for classes
  - `UPPER_CASE` for constants

## Type Hints

- **Required**: Use type hints for all function signatures
- Use Python 3.13+ features (e.g., `list[str]` instead of `List[str]`)
- Leverage `Mapped` types for SQLAlchemy models

## Imports

- **Location**: All imports at the top of file (never mid-file)
- **Order**: stdlib → third-party → local (ruff handles sorting)
- **Style**: Use ruff's isort rules (I rules enabled)

## Logging

- **Never use print()**: Use `logging` module instead
- **Logger creation**: Create module-level logger at top of file:
  ```python
  logger = logging.getLogger("module_name")
  ```
- **Exception logging**: Prefer `logger.exception()` over `logger.error()` when logging exceptions

## Error Handling

- Use specific exception types (avoid bare `except:`)
- Create custom exceptions in `errors.py` when needed
- Handle expected errors gracefully with user-friendly messages

## Async Patterns

- All Telegram handlers must be async functions
- Use `await` for all async operations
- Use `asyncio.run()` only in main entry point

## Database Access

- Always use `get_db()` singleton from `persistence.py`
- Use SQLAlchemy ORM patterns (no raw SQL unless necessary)
- Commit transactions explicitly in session context managers

## Before Committing

Always run these commands:

```bash
uv run ruff format .
uv run ruff check .
```

Pre-commit hooks will enforce these automatically if configured.
