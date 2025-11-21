---
inclusion: always
---

# Product Overview

Lonchera is a Telegram bot that integrates with the Lunch Money personal finance application. It enables users to manage financial transactions directly from Telegram.

## Core Features

- **Transaction monitoring**: Polls for new transactions and sends notifications
- **Transaction management**: Categorize, tag, add notes, rename payees, mark as reviewed
- **Manual transactions**: Add transactions for non-Plaid accounts (cash, etc.)
- **Budget tracking**: View current month's budget status
- **Account balances**: Display balances across all accounts
- **AI categorization**: Auto-categorize transactions using DeepInfra API
- **Audio transcription**: Process voice messages for transaction management
- **Multi-user support**: Single bot instance can serve multiple users

## Architecture

- Python-based Telegram bot using python-telegram-bot library
- Integrates with Lunch Money API via lunchable library
- SQLite database for persistence (transactions, settings, analytics)
- Optional AI features via DeepInfra and DSPy
- Async/await pattern throughout
- Web server for status monitoring
