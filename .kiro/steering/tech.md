---
inclusion: always
---

# Tech Stack

## Language & Runtime

- **Python 3.13+**: Required version, use modern Python features
- **Package Manager**: `uv` (not pip)

## Core Dependencies

- **python-telegram-bot**: Telegram bot framework with job queue support
- **lunchable**: Lunch Money API client
- **SQLAlchemy**: ORM for SQLite database
- **aiohttp**: Async HTTP client
- **dspy**: AI framework for structured prompting
- **openai**: OpenAI API client
- **langchain-core/langchain-openai/langgraph**: LLM orchestration

## Development Tools

- **ruff**: Linting and formatting (replaces black, isort, flake8)
- **mypy**: Type checking (optional)

## Deployment

- **Docker**: Primary deployment method
- **fly.io**: Recommended hosting platform (free tier available)
- Local development supported

## Common Commands

### Code Quality

```bash
# Format code (always run before committing)
uv run ruff format .

# Lint code
uv run ruff check .

# Type check (optional)
python -m mypy .
```

### Running the Application

```bash
# Local development
python main.py

# Docker (daemon mode)
./run_using_docker.sh

# Deploy to fly.io
./run_using_fly.sh

# Stop Docker container
./stop_docker.sh
```

### Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_file.py::test_name -v
```

## Environment Variables

Required in `.env` file or environment:

- `TELEGRAM_BOT_TOKEN`: Bot token from BotFather
- `DB_PATH`: SQLite database path (default: `lonchera.db`)
- `OPENROUTER_API_KEY`: Optional, for AI agent features (categorization, natural language queries)
- `DEEPINFRA_API_KEY`: Optional, for audio transcription (Whisper API)
