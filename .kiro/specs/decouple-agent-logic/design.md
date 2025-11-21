# Design Document

## Overview

This design separates the Lunch Money AI agent into two distinct modules:

1. **lunch_money_agent_core.py**: Pure agent logic with DSPy, configurable via parameters
2. **lunch_money_agent.py**: Telegram integration layer that handles bot-specific concerns

The core module will be testable independently while the handler module maintains all existing Telegram bot functionality.

## Architecture

```
┌─────────────────────────────────────┐
│   Telegram Bot (main.py)            │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  lunch_money_agent.py                │
│  - Fetch user settings from DB       │
│  - Track metrics                     │
│  - Handle Telegram reactions         │
│  - Format and send messages          │
│  - Update transaction messages       │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  lunch_money_agent_core.py           │
│  - DSPy agent configuration          │
│  - LM selection logic                │
│  - Agent execution                   │
│  - Pure business logic               │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  handlers/aitools/tools.py           │
│  - Lunch Money API interactions      │
│  - Tool implementations              │
└─────────────────────────────────────┘
```

## Components and Interfaces

### lunch_money_agent_core.py

#### AgentConfig (Dataclass)
Configuration object passed to the agent core:

```python
@dataclass
class AgentConfig:
    """Configuration for the Lunch Money agent."""
    chat_id: int
    language: str = "English"
    timezone: str = "UTC"
    model_name: str | None = None
    is_admin: bool = False
```

#### get_dspy_lm(config: AgentConfig) -> dspy.LM
- Accepts AgentConfig instead of just chat_id
- Uses config.model_name if provided, otherwise determines default
- Uses config.is_admin to decide if advanced models are allowed
- Returns configured DSPy LM instance
- No database calls

#### execute_agent(user_prompt: str, config: AgentConfig, tx_id: int | None = None, telegram_message_id: int | None = None) -> LunchMoneyAgentResponse
- Main entry point for agent execution
- Accepts all configuration via AgentConfig parameter
- Creates DSPy agent with tools
- Executes agent with user prompt
- Returns LunchMoneyAgentResponse
- No database calls for settings or metrics
- Raises exceptions for error handling by caller

#### if __name__ == "__main__": main()
- Demonstrates standalone usage
- Creates sample AgentConfig
- Executes agent with test prompts
- Prints results
- Optional MLflow integration for testing

### lunch_money_agent.py

#### get_agent_response(user_prompt: str, chat_id: int, tx_id: int | None = None, telegram_message_id: int | None = None, verbose: bool = True) -> LunchMoneyAgentResponse
- Fetches user settings from database (uncommented)
- Creates AgentConfig from settings
- Tracks metrics (start time, request count)
- Calls execute_agent() from core module
- Tracks success/failure metrics
- Tracks response characteristics
- Handles exceptions and returns error response
- Returns LunchMoneyAgentResponse

#### handle_generic_message_with_ai(update: Update, context: ContextTypes.DEFAULT_TYPE)
- Unchanged - handles Telegram message events
- Calls get_agent_response()
- Handles reactions and responses

#### handle_ai_response(update: Update, context: ContextTypes.DEFAULT_TYPE, response: LunchMoneyAgentResponse)
- Unchanged - processes agent response
- Sends Telegram messages
- Updates transaction messages
- Tracks metrics

## Data Models

### AgentConfig
```python
@dataclass
class AgentConfig:
    chat_id: int
    language: str = "English"
    timezone: str = "UTC"
    model_name: str | None = None
    is_admin: bool = False
```

### LunchMoneyAgentResponse
Remains unchanged - already defined in current code:
```python
class LunchMoneyAgentResponse(BaseModel):
    status: str
    message: str
    transactions_created_ids: list[int] | None = None
    transaction_updated_ids: dict[int, int] | None = None
```

### LunchMoneyAgentSignature
Moves to core module - DSPy signature definition remains unchanged.

## Error Handling

### Core Module
- Raises exceptions for caller to handle
- No try/except at execute_agent level
- Allows caller to decide error handling strategy

### Handler Module
- Wraps core execution in try/except
- Tracks failure metrics
- Returns error LunchMoneyAgentResponse
- Logs exceptions with full traceback

## Testing Strategy

### Core Module Testing
- Can be tested by running `python handlers/lunch_money_agent_core.py`
- Create AgentConfig with test values
- No database required
- Can use different models for testing
- Can test with different languages/timezones

### Handler Module Testing
- Integration tests with Telegram bot
- Requires database and settings
- Tests full flow including metrics tracking
- Tests message formatting and reactions

### Tool Testing
- Tools remain unchanged
- Continue to use database where needed
- Tested as part of agent execution

## Migration Path

1. Create lunch_money_agent_core.py with extracted logic
2. Move LunchMoneyAgentSignature to core
3. Move get_dspy_lm to core (refactored to use AgentConfig)
4. Create execute_agent function in core
5. Add AgentConfig dataclass to core
6. Update lunch_money_agent.py to use core module
7. Uncomment database calls in get_agent_response
8. Uncomment metrics tracking in get_agent_response
9. Test standalone core execution
10. Test full Telegram integration
