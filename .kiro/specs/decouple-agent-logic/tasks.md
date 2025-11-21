# Implementation Plan

- [x] 1. Create lunch_money_agent_core.py with core agent logic
  - Create new file handlers/lunch_money_agent_core.py
  - Add necessary imports (dspy, datetime, logging, os, dataclasses)
  - Define AgentConfig dataclass with chat_id, language, timezone, model_name, is_admin fields
  - Move LunchMoneyAgentResponse class from lunch_money_agent.py to core
  - Move LunchMoneyAgentSignature class from lunch_money_agent.py to core
  - _Requirements: 1.1, 1.3, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1_

- [x] 2. Implement get_dspy_lm function in core module
  - Move get_dspy_lm function from lunch_money_agent.py to core
  - Refactor to accept AgentConfig instead of chat_id
  - Use config.model_name if provided, otherwise use default
  - Use config.is_admin to determine if advanced models are allowed
  - Remove all get_db() calls for settings
  - Remove all get_db().inc_metric() calls
  - Keep logging statements
  - _Requirements: 3.3, 3.5, 4.1, 4.2_

- [x] 3. Implement execute_agent function in core module
  - Create execute_agent function that accepts user_prompt, AgentConfig, tx_id, telegram_message_id
  - Call get_dspy_lm with config
  - Define tools list (same as current implementation)
  - Create DSPy ReAct agent with LunchMoneyAgentSignature and tools
  - Execute agent with user prompt and config parameters
  - Return LunchMoneyAgentResponse
  - Remove all database calls and metrics tracking
  - Let exceptions propagate to caller
  - _Requirements: 1.1, 1.3, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3_

- [x] 4. Add standalone testing main function to core module
  - Add if __name__ == "__main__": block
  - Create sample AgentConfig with test values
  - Call execute_agent with sample prompts
  - Print results
  - Include MLflow integration (optional, commented out by default)
  - _Requirements: 1.1, 1.4_

- [x] 5. Refactor lunch_money_agent.py to use core module
  - Add import for lunch_money_agent_core module
  - Import AgentConfig, LunchMoneyAgentResponse, and execute_agent from core
  - Remove LunchMoneyAgentResponse (now in core)
  - Remove LunchMoneyAgentSignature (now in core)
  - Remove get_dspy_lm function (now in core)
  - _Requirements: 2.1, 2.2, 2.3, 5.1_

- [x] 6. Update get_agent_response to use core module
  - Uncomment all get_db().get_current_settings(chat_id) calls
  - Fetch user settings from database at the start
  - Extract language, timezone, model from settings
  - Determine is_admin based on ADMIN_USER_ID environment variable
  - Create AgentConfig with fetched settings
  - Call execute_agent from core module with config
  - Uncomment all metrics tracking (inc_metric calls)
  - Wrap execute_agent call in try/except
  - Track success/failure metrics
  - Track response characteristics (processing time, response length, status)
  - Return LunchMoneyAgentResponse on success or error
  - _Requirements: 2.1, 2.2, 2.4, 3.1, 3.2, 3.3, 4.3, 4.4, 5.2, 5.3_

- [x] 7. Verify Telegram handler functions remain unchanged
  - Confirm handle_generic_message_with_ai is unchanged
  - Confirm handle_ai_response is unchanged
  - Ensure all existing functionality is preserved (reactions, markdown, transaction updates)
  - _Requirements: 2.3, 2.5, 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 8. Remove temporary testing code from lunch_money_agent.py
  - Remove or comment out the if __name__ == "__main__": block in lunch_money_agent.py
  - Keep only the core module's main function for standalone testing
  - _Requirements: 1.1, 1.4_

- [x] 9. Fix DSPy LM provider format for LiteLLM compatibility
  - Update get_dspy_lm function in lunch_money_agent_core.py to use provider/company/model format
  - Change default Llama model to use openrouter/ prefix: "openrouter/meta-llama/Llama-4-Scout-17B-16E-Instruct"
  - Update OpenAI model names in openai_models list to include company prefix (openai/)
  - Update model name mappings in handlers/settings/ai.py to use company/model format
  - Update get_model_display_name function to handle new format with company prefix
  - Ensure all models passed to dspy.LM follow format: provider/company/model_name
  - _Requirements: 3.3, 4.1, 4.2_

- [ ] 10. Test standalone core execution
  - Run python handlers/lunch_money_agent_core.py directly
  - Verify agent executes without database dependencies
  - Test with different AgentConfig values (language, timezone, model)
  - Verify responses are returned correctly
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.1, 3.2, 3.3, 4.1, 4.2_

- [ ] 11. Verify full integration with Telegram bot
  - Test message handling through Telegram
  - Verify settings are fetched from database
  - Verify metrics are tracked correctly
  - Verify transaction creation and updates work
  - Verify error handling works as expected
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5_
