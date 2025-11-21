# Design Document

## Overview

This design outlines the migration of AI-powered transaction categorization from the standalone deepinfra.py module to the unified DSPy agent system. The migration will consolidate all AI functionality under a single framework, improving code maintainability and consistency while preserving all existing categorization features.

The key insight is that categorization is fundamentally a specialized AI task that can be handled by the agent with a focused prompt, rather than requiring a separate implementation. By leveraging the agent's existing infrastructure, we gain access to better model selection, consistent error handling, and unified metrics tracking.

## Architecture

### Current Architecture

```
User Action (Button/Auto) → deepinfra.py → Direct API Call → LunchMoney Update
                                ↓
                         Manual Prompt Building
                         Direct HTTP Requests
                         Separate Metrics
```

### New Architecture

```
User Action (Button/Auto) → categorization.py → DSPy Agent → LunchMoney Update
                                                     ↓
                                              Unified Agent System
                                              Consistent Error Handling
                                              Shared Metrics
```

## Components and Interfaces

### 1. New Categorization Function in categorization.py

**Purpose**: Replace the current `auto_categorize` function with a new implementation that uses the DSPy agent.

**Interface**:
```python
def categorize_transaction_with_agent(tx_id: int, chat_id: int) -> str:
    """
    Categorize a transaction using the DSPy agent.
    
    Args:
        tx_id: Transaction ID to categorize
        chat_id: Chat ID for accessing Lunch Money data
        
    Returns:
        str: Human-readable result message
    """
```

**Implementation Details**:
- Fetch the transaction using `get_lunch_client_for_chat_id(chat_id).get_transaction(tx_id)`
- Build a focused prompt that asks the agent to categorize the transaction
- Call `get_agent_response()` from `handlers/ai_agent.py` with the categorization prompt
- Parse the agent's response to extract the suggested category
- Update the transaction in Lunch Money with the new category
- Respect the `mark_reviewed_after_categorized` setting
- Return a user-friendly status message

**Prompt Strategy**:
The prompt should be concise and directive:
```
"Categorize this transaction. Only respond with the category ID that best matches this transaction. 
Consider the payee, amount, and any notes. For Amazon transactions, only use the Amazon category 
if the notes don't indicate a more specific category."
```

The agent already has access to:
- `get_single_transaction(chat_id, transaction_id)` - to fetch transaction details
- `get_categories(chat_id)` - to see available categories
- `update_transaction(chat_id, transaction_id, category_id=X)` - to apply the category

### 2. Update ai_categorize_transaction in categorization.py

**Current Implementation**:
```python
async def ai_categorize_transaction(tx_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    response = auto_categorize(tx_id, chat_id)  # Uses deepinfra
    # ... update message
```

**New Implementation**:
```python
async def ai_categorize_transaction(tx_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    response = categorize_transaction_with_agent(tx_id, chat_id)  # Uses DSPy agent
    # ... update message (same as before)
```

### 3. Update Button Handler in transactions.py

**Current Implementation**:
```python
async def handle_btn_ai_categorize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tx_id = int(update.callback_data_suffix)
    chat_id = update.chat_id
    response = auto_categorize(tx_id, chat_id)  # Direct deepinfra call
    # ... show response
```

**New Implementation**:
```python
async def handle_btn_ai_categorize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tx_id = int(update.callback_data_suffix)
    chat_id = update.chat_id
    response = categorize_transaction_with_agent(tx_id, chat_id)  # Use new function
    # ... show response (same as before)
```

### 4. Update Amazon Transaction Processing

**File**: `amazon.py`

**Current Implementation**:
```python
from deepinfra import get_suggested_category_id

def update_amazon_transaction(..., auto_categorize):
    if auto_categorize:
        _, cat_id = get_suggested_category_id(tx_id=transaction.id, lunch=lunch, override_notes=product_name)
```

**New Implementation**:
```python
from handlers.categorization import categorize_transaction_with_agent

def update_amazon_transaction(..., auto_categorize):
    if auto_categorize:
        # Use the agent-based categorization
        categorize_transaction_with_agent(transaction.id, chat_id)
        # Fetch updated transaction to get the new category
        updated_tx = lunch.get_transaction(transaction.id)
        cat_id = updated_tx.category_id
```

**Note**: The Amazon processing will need access to `chat_id`, which should be passed through the call chain from the handler.

### 5. Remove deepinfra.py

Once all references are migrated:
1. Remove all imports of `deepinfra` module
2. Delete the `deepinfra.py` file
3. Update any remaining references to use the new categorization function

## Data Models

### Agent Response Format

The agent will be instructed to respond with a simple format that can be parsed:

**Success Response**:
```json
{
  "status": "success",
  "message": "Transaction categorized as [Category Name]",
  "transaction_updated_ids": {
    "123": 456  // tx_id: telegram_message_id
  }
}
```

**Failure Response**:
```json
{
  "status": "error",
  "message": "Could not determine appropriate category"
}
```

### Transaction Context

The agent will receive transaction context through its existing tools:
- Transaction details via `get_single_transaction(chat_id, tx_id)`
- Available categories via `get_categories(chat_id)`
- Update capability via `update_transaction(chat_id, tx_id, category_id=X)`

## Error Handling

### Agent Failures

**Scenario**: Agent fails to respond or returns an error
**Handling**: 
- Catch exceptions from `get_agent_response()`
- Return user-friendly error message: "AI categorization failed. Please try again or categorize manually."
- Log the error with full context for debugging

### Invalid Category Selection

**Scenario**: Agent suggests a category that doesn't exist or is a parent category
**Handling**:
- Validate the category ID against the list of valid categories
- If invalid, return error message: "AI suggested an invalid category. Please categorize manually."
- Log the invalid suggestion for analysis

### Transaction Not Found

**Scenario**: Transaction ID doesn't exist in Lunch Money
**Handling**:
- Catch the exception from `get_transaction()`
- Return error message: "Transaction not found"
- This should be rare as we only categorize existing transactions

### Settings Handling

**Scenario**: User has `mark_reviewed_after_categorized` enabled
**Handling**:
- Fetch settings: `get_db().get_current_settings(chat_id)`
- If enabled, update transaction with both category and status: `TransactionUpdateObject(category_id=X, status="cleared")`
- If disabled, only update category: `TransactionUpdateObject(category_id=X)`

## Testing Strategy

### Unit Testing Approach

**Test File**: `handlers/aitools/test_categorization.py` (new file)

**Test Cases**:

1. **test_categorize_transaction_success**
   - Mock the agent response with a valid category
   - Verify transaction is updated with correct category
   - Verify success message is returned

2. **test_categorize_transaction_with_review**
   - Mock settings with `mark_reviewed_after_categorized=True`
   - Verify transaction is marked as reviewed after categorization

3. **test_categorize_transaction_agent_failure**
   - Mock agent to raise an exception
   - Verify error message is returned
   - Verify transaction is not modified

4. **test_categorize_transaction_invalid_category**
   - Mock agent to suggest non-existent category
   - Verify error handling
   - Verify transaction is not modified

5. **test_amazon_categorization_integration**
   - Test Amazon transaction processing with agent categorization
   - Verify product name is used in categorization context

### Integration Testing

**Manual Testing Checklist**:

1. **Button Categorization**
   - Send a transaction to Telegram
   - Click "AI Categorize" button
   - Verify category is applied
   - Verify message updates to show new category

2. **Auto-Categorization After Notes**
   - Enable `auto_categorize_after_notes` setting
   - Add notes to a transaction
   - Verify automatic categorization occurs
   - Verify message updates

3. **Amazon Transaction Processing**
   - Upload Amazon export file
   - Enable AI categorization
   - Process transactions
   - Verify categories are applied based on product names

4. **Error Scenarios**
   - Test with invalid transaction ID
   - Test with agent timeout/failure
   - Verify error messages are user-friendly

### Metrics Validation

**Before Migration**:
- Track `deepinfra_requests` count
- Track `deepinfra_prompt_tokens` and `deepinfra_completion_tokens`

**After Migration**:
- Verify `ai_agent_requests` increases appropriately
- Verify `ai_agent_transactions_updated` tracks categorizations
- Verify no new `deepinfra_*` metrics are created

## Migration Plan

### Phase 1: Create New Implementation
1. Create `categorize_transaction_with_agent()` function in `categorization.py`
2. Implement agent-based categorization logic
3. Add error handling and logging

### Phase 2: Update Call Sites
1. Update `ai_categorize_transaction()` to use new function
2. Update `handle_btn_ai_categorize()` in `transactions.py`
3. Update `handle_message_reply()` auto-categorization path
4. Update Amazon transaction processing in `amazon.py`

### Phase 3: Remove Old Implementation
1. Remove all imports of `deepinfra` module
2. Delete `deepinfra.py` file
3. Verify no remaining references

### Phase 4: Testing and Validation
1. Run unit tests
2. Perform manual integration testing
3. Monitor metrics in production
4. Verify no regressions in categorization accuracy

## Special Considerations

### Amazon Category Logic

The current implementation has special logic for Amazon transactions:
> "If the Payee is Amazon, then choose the Amazon category ONLY if the notes of the transaction can't be categorized as a specific non-Amazon category."

This logic should be preserved in the agent prompt. The agent's signature already includes guidance about transaction categorization, so we'll add this specific rule to the categorization prompt.

### Backwards Compatibility

The migration maintains full backwards compatibility:
- All existing settings continue to work
- Button labels and UI remain unchanged
- Auto-categorization triggers remain the same
- Error messages are similar in tone and content

### Performance Considerations

**Current**: Direct API call to DeepInfra with Llama model
**New**: Agent call through OpenRouter with configurable model

**Implications**:
- Agent calls may be slightly slower due to additional tool invocations
- However, agent has access to better models (for admin users)
- Agent provides better error handling and retry logic
- Overall user experience should be similar or improved

### Metrics Migration

**Deprecated Metrics** (will stop incrementing):
- `deepinfra_requests`
- `deepinfra_prompt_tokens`
- `deepinfra_completion_tokens`
- `deepinfra_estimated_cost`

**New Metrics** (will track categorization):
- `ai_agent_requests` (already exists)
- `ai_agent_transactions_updated` (already exists)
- `ai_agent_response_status_success` / `ai_agent_response_status_error` (already exists)

**Note**: Historical deepinfra metrics will remain in the database for analysis, but no new data will be added after migration.
