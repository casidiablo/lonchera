# Implementation Plan

- [x] 1. Create new agent-based categorization function
  - Create `categorize_transaction_with_agent()` function in `handlers/categorization.py`
  - Implement logic to fetch transaction details and build categorization prompt
  - Call `get_agent_response()` with focused categorization prompt
  - Parse agent response and extract category suggestion
  - Update transaction in Lunch Money with suggested category
  - Respect `mark_reviewed_after_categorized` setting from user preferences
  - Add comprehensive error handling for agent failures and invalid categories
  - Add logging for debugging and monitoring
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 6.1, 6.2, 6.3, 6.4_

- [ ] 2. Update existing categorization call sites
- [x] 2.1 Update ai_categorize_transaction function
  - Modify `ai_categorize_transaction()` in `handlers/categorization.py` to call new agent-based function
  - Ensure message update logic remains unchanged
  - _Requirements: 1.1, 3.3_

- [x] 2.2 Update button handler for manual categorization
  - Modify `handle_btn_ai_categorize()` in `handlers/transactions.py` to use new function
  - Remove import of `auto_categorize` from deepinfra
  - Import new `categorize_transaction_with_agent` function
  - Ensure callback answer and message update logic remains unchanged
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 2.3 Update auto-categorization after notes
  - Verify `handle_message_reply()` in `handlers/transactions.py` correctly calls `ai_categorize_transaction()`
  - Ensure auto-categorization flow works with new implementation
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 2.4 Update Amazon transaction processing
  - Modify `update_amazon_transaction()` in `amazon.py` to use agent-based categorization
  - Pass `chat_id` through the call chain from handler to Amazon processing function
  - Update `process_amazon_transactions()` signature to accept and pass `chat_id`
  - Update handler calls to `process_amazon_transactions()` to include `chat_id`
  - Remove import of `get_suggested_category_id` from deepinfra
  - Import new `categorize_transaction_with_agent` function
  - Fetch updated transaction after categorization to get new category ID
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 3. Remove deepinfra module
- [x] 3.1 Remove all deepinfra imports
  - Search codebase for all imports of deepinfra module
  - Remove import statements from `handlers/transactions.py`
  - Remove import statements from `amazon.py`
  - Remove any other remaining imports
  - _Requirements: 5.1, 5.2_

- [x] 3.2 Delete deepinfra.py file
  - Delete the `deepinfra.py` file from the project root
  - Verify no broken imports remain
  - _Requirements: 5.2_

- [x] 3.3 Verify metrics migration
  - Confirm that categorization operations increment `ai_agent_*` metrics
  - Verify no new `deepinfra_*` metrics are created after migration
  - Add logging to track metric changes during categorization
  - _Requirements: 5.3, 5.4_

- [ ]* 4. Add unit tests for new categorization function
  - Create test file `handlers/aitools/test_categorization.py`
  - Write test for successful categorization
  - Write test for categorization with mark_reviewed_after_categorized enabled
  - Write test for agent failure handling
  - Write test for invalid category handling
  - Write test for Amazon transaction categorization
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 4.1_

- [ ]* 5. Manual integration testing
  - Test button-triggered categorization on a real transaction
  - Test auto-categorization after adding notes
  - Test Amazon transaction processing with AI categorization enabled
  - Test error scenarios (invalid transaction, agent failure)
  - Verify metrics are being tracked correctly
  - Verify message updates work correctly after categorization
  - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.3_

- [ ] 6. Update environment variable checks for OpenRouter
- [x] 6.1 Replace DEEPINFRA_API_KEY checks with OPENROUTER_API_KEY
  - Update `tx_messaging.py` to check for `OPENROUTER_API_KEY` instead of `DEEPINFRA_API_KEY`
  - Update `web_server.py` to check for `OPENROUTER_API_KEY` and display appropriate AI status
  - Search codebase for any other `DEEPINFRA_API_KEY` references and update them
  - _Requirements: 5.1, 5.2_

- [x] 6.2 Update .env file documentation
  - Update `.env` file to add `OPENROUTER_API_KEY` alongside `DEEPINFRA_API_KEY`
  - Add comment explaining that OpenRouter API key is required for AI agent features
  - Add comment explaining that DeepInfra API key is required for audio transcription
  - _Requirements: 5.2_

- [x] 7. Update documentation
- [x] 7.1 Update SELFHOST.md
  - Update to explain both API keys are needed for full AI functionality
  - Add `OPENROUTER_API_KEY` documentation for AI agent features (categorization, natural language queries)
  - Keep `DEEPINFRA_API_KEY` documentation for audio transcription (Whisper)
  - Update instructions for setting `OPENROUTER_API_KEY` in fly.io secrets
  - Update instructions for setting `OPENROUTER_API_KEY` in Docker run command
  - Update instructions for setting `OPENROUTER_API_KEY` in local .env file
  - Clarify that `DEEPINFRA_API_KEY` is optional and only needed for voice message transcription
  - Clarify that `OPENROUTER_API_KEY` is optional and only needed for AI agent features
  - _Requirements: 5.2_

- [x] 7.2 Update README.md
  - Update AI categorization section to mention OpenRouter and DSPy agent-based categorization
  - Add note that DeepInfra is still used for audio transcription (Whisper API)
  - Update feature description to reflect new agent capabilities
  - Clarify the two API keys serve different purposes
  - _Requirements: 5.2_
