# Requirements Document

## Introduction

This document outlines the requirements for decoupling the Lunch Money AI agent core logic from the Telegram bot integration code. The goal is to enable independent testing and development of the agent logic while maintaining full integration with the Telegram bot.

## Glossary

- **Agent Core**: The DSPy-based AI agent logic that processes user requests and interacts with Lunch Money API
- **Telegram Handler**: The Telegram bot integration code that handles messages, reactions, and UI interactions
- **User Settings**: Configuration data stored in the database including AI model preferences, language, and timezone
- **LM**: Language Model instance configured via DSPy
- **Agent Response**: Structured output from the agent containing status, message, and transaction IDs

## Requirements

### Requirement 1

**User Story:** As a developer, I want to test the AI agent logic independently from the Telegram bot, so that I can iterate faster during development

#### Acceptance Criteria

1. WHEN the agent core module is executed directly, THE Agent Core SHALL process user requests without requiring Telegram context
2. WHEN testing the agent core, THE Agent Core SHALL accept user settings as parameters instead of fetching from database
3. WHEN the agent core is invoked, THE Agent Core SHALL return structured responses that can be used by any client
4. WHERE standalone testing is needed, THE Agent Core SHALL provide a main function that demonstrates usage with sample data

### Requirement 2

**User Story:** As a developer, I want the Telegram handler to use the decoupled agent core, so that the bot continues to function with all existing features

#### Acceptance Criteria

1. WHEN a Telegram message is received, THE Telegram Handler SHALL fetch user settings from the database
2. WHEN invoking the agent core, THE Telegram Handler SHALL pass user settings as parameters
3. WHEN the agent returns a response, THE Telegram Handler SHALL process transaction updates and send Telegram messages
4. WHEN tracking metrics, THE Telegram Handler SHALL record analytics data to the database
5. THE Telegram Handler SHALL maintain all existing functionality including reactions, markdown formatting, and transaction message updates

### Requirement 3

**User Story:** As a developer, I want the agent core to be configurable via parameters, so that it can work in different contexts (testing, production, different users)

#### Acceptance Criteria

1. THE Agent Core SHALL accept language preference as a parameter
2. THE Agent Core SHALL accept timezone information as a parameter
3. THE Agent Core SHALL accept model selection as a parameter
4. THE Agent Core SHALL accept chat_id for tool invocations as a parameter
5. WHERE model selection is provided, THE Agent Core SHALL use the specified model instead of default

### Requirement 4

**User Story:** As a developer, I want clear separation between database operations and agent logic, so that the agent can be tested without database dependencies

#### Acceptance Criteria

1. THE Agent Core SHALL NOT directly call get_db() for user settings
2. THE Agent Core SHALL NOT directly call get_db() for metrics tracking
3. THE Telegram Handler SHALL handle all database operations for settings and metrics
4. THE Agent Core SHALL only use database operations within tool functions that require them
5. WHEN the agent core needs configuration, THE Agent Core SHALL receive it via function parameters

### Requirement 5

**User Story:** As a developer, I want the refactored code to maintain backward compatibility, so that existing bot functionality is not disrupted

#### Acceptance Criteria

1. THE Telegram Handler SHALL continue to support all existing message handling patterns
2. THE Telegram Handler SHALL continue to track all existing metrics
3. THE Telegram Handler SHALL continue to handle transaction creation and updates
4. THE Telegram Handler SHALL continue to support voice message transcription integration
5. WHEN errors occur, THE Telegram Handler SHALL handle them with the same error messages and logging
