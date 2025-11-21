# Requirements Document

## Introduction

This feature migrates the existing AI-powered transaction categorization from a manual deepinfra implementation to the unified dspy agent system. Currently, the bot uses a separate deepinfra.py module with direct API calls to categorize transactions. This migration will consolidate all AI functionality under the dspy agent framework, improving maintainability, consistency, and leveraging the agent's existing capabilities.

## Glossary

- **Lonchera Bot**: The Telegram bot that integrates with Lunch Money for personal finance management
- **Transaction**: A financial transaction from Lunch Money that needs categorization
- **Category**: A Lunch Money category that can be assigned to transactions
- **Deepinfra Module**: The current deepinfra.py file that handles AI categorization via direct API calls
- **DSPy Agent**: The existing agent system in handlers/aitools/agent_engine.py that uses DSPy framework for AI operations
- **Auto-categorization**: The feature that automatically suggests and applies categories to transactions using AI
- **Manual Categorization**: The button-triggered categorization where users explicitly request AI to categorize a transaction

## Requirements

### Requirement 1

**User Story:** As a user, I want AI categorization to use the same agent system as other AI features, so that I have consistent AI behavior across all bot operations

#### Acceptance Criteria

1. WHEN the System receives a categorization request, THE Lonchera Bot SHALL use the DSPy Agent to determine the appropriate category
2. WHEN the DSPy Agent categorizes a transaction, THE Lonchera Bot SHALL apply the same category selection logic as the current deepinfra implementation
3. WHEN categorization completes, THE Lonchera Bot SHALL update the transaction with the suggested category in Lunch Money
4. WHEN the user has mark_reviewed_after_categorized enabled, THE Lonchera Bot SHALL mark the transaction as reviewed after categorization

### Requirement 2

**User Story:** As a user, I want the AI categorization button to continue working as before, so that I can manually trigger categorization when needed

#### Acceptance Criteria

1. WHEN the user clicks the "AI Categorize" button on a transaction, THE Lonchera Bot SHALL invoke the DSPy Agent with the transaction context
2. WHEN the DSPy Agent completes categorization, THE Lonchera Bot SHALL display the result to the user via callback answer
3. WHEN categorization succeeds, THE Lonchera Bot SHALL update the transaction message to reflect the new category
4. WHEN categorization fails, THE Lonchera Bot SHALL display an appropriate error message to the user

### Requirement 3

**User Story:** As a user, I want auto-categorization after adding notes to continue working, so that my workflow remains unchanged

#### Acceptance Criteria

1. WHEN the user adds notes to a transaction, THE Lonchera Bot SHALL check the auto_categorize_after_notes setting
2. WHEN auto_categorize_after_notes is enabled, THE Lonchera Bot SHALL automatically invoke the DSPy Agent to categorize the transaction
3. WHEN the DSPy Agent categorizes the transaction, THE Lonchera Bot SHALL update the transaction message with the new category
4. WHEN auto_categorize_after_notes is disabled, THE Lonchera Bot SHALL not perform automatic categorization

### Requirement 4

**User Story:** As a user, I want Amazon transaction processing to support AI categorization, so that my Amazon purchases are properly categorized

#### Acceptance Criteria

1. WHEN processing Amazon transactions with AI categorization enabled, THE Lonchera Bot SHALL use the DSPy Agent for category suggestions
2. WHEN the DSPy Agent suggests a category for an Amazon transaction, THE Lonchera Bot SHALL validate the category exists before applying it
3. WHEN the category is valid, THE Lonchera Bot SHALL update the Amazon transaction with the suggested category
4. WHEN the category is invalid, THE Lonchera Bot SHALL log the error and skip categorization for that transaction

### Requirement 5

**User Story:** As a developer, I want the deepinfra.py module to be completely removed, so that the codebase has a single AI implementation approach

#### Acceptance Criteria

1. WHEN the migration is complete, THE Lonchera Bot SHALL not import or use functions from deepinfra.py
2. WHEN all categorization features are migrated, THE deepinfra.py file SHALL be deleted from the codebase
3. WHEN the DSPy Agent handles categorization, THE Lonchera Bot SHALL maintain all existing metrics tracking for categorization operations
4. WHEN categorization occurs, THE Lonchera Bot SHALL track metrics using the existing ai_agent metrics instead of deepinfra metrics

### Requirement 6

**User Story:** As a user, I want categorization to respect special rules like Amazon category handling, so that my transactions are categorized intelligently

#### Acceptance Criteria

1. WHEN categorizing an Amazon transaction, THE DSPy Agent SHALL only suggest the Amazon category if the transaction notes cannot be categorized as a more specific category
2. WHEN the DSPy Agent receives transaction information, THE DSPy Agent SHALL consider payee, amount, currency, plaid metadata, and notes
3. WHEN selecting a category, THE DSPy Agent SHALL only suggest leaf categories (subcategories) and not parent categories
4. WHEN no appropriate category can be determined, THE DSPy Agent SHALL return an indication that categorization failed
