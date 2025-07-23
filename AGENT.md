Lonchera is a Telegram bot that interacts with the LunchMoney API to manage
and track expenses, income, and financial goals.

The package manager used is `uv`. All changes made to the code should be followed
by running:

```bash
uv run ruff format .
uv run ruff check .
```

Use type hints as much as possible.

# coding conventions

## logging

Avoid using print statements for logging. Use the `logging` package instead. Create a logger the
root of the file that makes sense for the context.

Prefer using `logger.exception` over `logger.error` when logging exceptions.

## imports

Avoid adding import statements mid-file. Import statements should be at the top of the file.
