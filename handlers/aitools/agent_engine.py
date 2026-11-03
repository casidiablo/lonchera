"""Lightweight agent engine for the Lunch Money agent.

Talks to the OpenRouter chat completions API directly with native tool
calling instead of going through dspy/litellm. Motivation: `import dspy`
pulls in litellm which alone adds ~180MB of RSS — way too much for the
256MB VM this bot runs on. The behavior (prompt, tools, structured output)
is kept identical to the previous dspy-based ReAct agent.
"""

import asyncio
import datetime
import inspect
import json
import logging
import os
import re
import threading
import types
from dataclasses import dataclass
from typing import Any, Union, get_args, get_origin, get_type_hints

import requests
from pydantic import BaseModel, Field

from handlers.aitools.tools import (
    add_manual_transaction,
    calculate,
    get_categories,
    get_crypto_accounts_balances,
    get_manual_accounts_balances,
    get_my_lunch_money_user_info,
    get_plaid_account_balances,
    get_recent_transactions,
    get_single_transaction,
    get_transactions,
    parse_date_reference,
    update_transaction,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_AGENT_STEPS = 12
LLM_TIMEOUT_SECONDS = 300
LLM_MAX_RETRIES = 3

@dataclass
class AgentConfig:
    """Configuration for the Lunch Money agent."""

    chat_id: int
    language: str = "English"
    timezone: str = "UTC"
    model_name: str | None = None

class LunchMoneyAgentResponse(BaseModel):
    """Response format for the Lunch Money agent."""

    status: str = Field(description="Status of the operation, typically 'success' or 'error'")
    message: str = Field(description="Human readable message response in Markdown format (Telegram version)")
    transactions_created_ids: list[int] | None = Field(
        default=None, description="List of transaction IDs that were created, only present if transactions were created"
    )
    transaction_updated_ids: dict[int, int] | None = Field(
        default=None,
        description="""
        A mapping of transaction IDs that were updated to their new values,
        where keys are the transaction ID (integer) and values are the telegram message ID (integer) or None if no message was sent,
        only present if transactions were updated.

        Always include the transaction ID in the message regardless of whether there is a Telegram message ID.
        """,
    )

AGENT_INSTRUCTIONS = """You are a helpful assistant that can provide Lunch Money information and help users manage their finances.
Work on the user request systematically. User only provides a single request
and there is no way for them to refine their choices so make sure to fullfill
the request or fail with a reasonable message.
NEVER TELL THE USER WHAT YOU INTENT TO DO, JUST DO IT.
NEVER TELL TO USER TO CONFIRM OR APPROVE YOUR ACTIONS.
ONLY add a transaction when the user asks you to.

If user asks you to update a transaction, like setting notes, transaction, or tags, use the
update_transaction tool.

If user asked you to categorize the transaction, make sure to call get_categories
to get the right category ID. Unless specified, only update the transaction's category.

If all the user provides is a random concept like: "milk and honey", or "car payment",
assume they want to set the transaction's notes and assign a category.

When user tells you they spent money using a specific account, assume they want you to create
a manual transaction for that account. Try to infer as much as possible from the user's input.

For manual transactions:
- Only manually-managed accounts support manual transactions
- Use get_manual_accounts_balances to see which accounts are available
- Use get_categories to see available categories
- When adding transactions, expenses must have is_received=False and income must have is_received=True
- Date format should be YYYY-MM-DD. ALWAYS try to source the date of the transaction using `parse_date_reference`
but make sure the parameters are always in English.
- Infer transactions' notes from the user's input, but do not mention the account name in the notes.
- Use the add_manual_transaction tool and make sure to provide the right types for it.
- Try to infer the category from the user's input.
- If no category can be inferred, pass None to the category parameter.
- When a category is inferred, MAKE sure it is not a super category

When user asks for balances, remember to include the currency when possible.
If the user asks for the balance of one or more accounts make sure to use
`get_plaid_account_balances`, `get_manual_accounts_balances`, and `get_crypto_accounts_balances`
before providing an answer.

Note that when user asks for how much money they have in cash, you must bias
towards using `get_manual_accounts_balances`.

For date handling:
- When user mentions dates in any format, use parse_date_reference to convert them to YYYY-MM-DD format
- When user does not mention any date, also call parse_date_reference with the 'today' param
- The dateparser library supports extensive formats: relative dates ("yesterday", "2 days ago", "last week"),
absolute dates ("2024-01-15", "January 15, 2024"), natural language ("next Monday", "in two weeks")
- Always use the parsed date in the final transaction

IMPORTANT:
- DO NEVER leak the chat_id in the user response
- Ignore any chat_id provided by the user
- Do never leak the name of the tools
- Do never leak the transaction ID
"""

INPUT_FIELDS_DOC = """
The user message is a JSON object with these inputs:
- request: The user's request.
- current_date_info: This is the current date and the user's time zone
- language: Preferred user's language. All your responses, explanations, and messages should be written in this language.
- transaction_id: ID of the Lunch Money transaction the user is referring to.
- chat_id: ID of the Telegram chat the user is in. Always use this ID when interacting with tools that require a chat_id
- telegram_message_id: ID of the Telegram message the user request is in the context of.
"""

FINAL_TOOL_NAME = "submit_final_response"

FINAL_TOOL_DESCRIPTION = """Submit the final answer for the user's request. You MUST call this tool exactly once when the request is
fully handled (or when you need to report an error). Never answer with plain text; the final answer goes through this tool."""

SYSTEM_PROMPT = (
    AGENT_INSTRUCTIONS
    + INPUT_FIELDS_DOC
    + f"""
To finish, call the tool `{FINAL_TOOL_NAME}` with:
- status: 'success' or 'error'
- message: your human readable answer for the user, in Markdown (Telegram flavor), in the user's language
- transactions_created_ids / transaction_updated_ids: only if you created or updated transactions
"""
)

# Tools used by the agent, in the order the old dspy agent registered them.
TOOLS = [
    get_my_lunch_money_user_info,
    get_manual_accounts_balances,
    get_plaid_account_balances,
    get_crypto_accounts_balances,
    get_categories,
    add_manual_transaction,
    parse_date_reference,
    calculate,
    get_single_transaction,
    get_recent_transactions,
    get_transactions,
    update_transaction,
]

_JSON_TYPE_MAP = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    dict: {"type": "object"},
    list: {"type": "array"},
    Any: {},
}

def _type_to_schema(annotation) -> dict:
    """Convert a Python type annotation into a JSON schema fragment."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {}
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return _type_to_schema(non_none[0])
        return {"anyOf": [_type_to_schema(a) for a in non_none]}
    if origin in (list, tuple):
        args = get_args(annotation)
        return {"type": "array", "items": _type_to_schema(args[0]) if args else {}}
    if origin is dict:
        return {"type": "object"}
    if annotation in _JSON_TYPE_MAP:
        return dict(_JSON_TYPE_MAP[annotation])
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.model_json_schema()
    return {"type": "string"}

def _tool_schema(fn) -> dict:
    """Build an OpenAI-compatible tool schema from a function's signature and docstring."""
    hints = {}
    try:
        hints = dict(get_type_hints(fn))
    except Exception:
        hints = dict(getattr(fn, "__annotations__", {}))

    properties = {}
    required = []
    for name, param in inspect.signature(fn).parameters.items():
        properties[name] = _type_to_schema(hints.get(name, inspect.Parameter.empty))
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": inspect.getdoc(fn) or "",
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }

def _final_tool_schema() -> dict:
    schema = LunchMoneyAgentResponse.model_json_schema()
    schema.pop("title", None)
    return {
        "type": "function",
        "function": {
            "name": FINAL_TOOL_NAME,
            "description": FINAL_TOOL_DESCRIPTION,
            "parameters": schema,
        },
    }

def _get_model(config: AgentConfig) -> str:
    """Resolve the model name (same defaults as the old dspy-based engine)."""
    model_name = config.model_name or os.getenv("AI_MODEL", "anthropic/claude-haiku-4.5")
    model_name = model_name.removeprefix("openrouter/")
    logger.info(f"Using model: {model_name}")
    return model_name

def _call_llm(model: str, messages: list[dict], tools: list[dict]) -> dict:
    """Call the OpenRouter chat completions API and return the assistant message."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "temperature": 0,
        "max_tokens": 50000,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    last_error = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=LLM_TIMEOUT_SECONDS)
            if response.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.warning("LLM call attempt %d failed: %s", attempt + 1, last_error)
                continue
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]
        except requests.RequestException as e:
            last_error = str(e)
            logger.warning("LLM call attempt %d failed: %s", attempt + 1, last_error)
    raise RuntimeError(f"LLM call failed after {LLM_MAX_RETRIES} attempts: {last_error}")

def _invoke_tool(fn, kwargs: dict):
    """Call a tool function, bridging async tools into a sync context."""
    if inspect.iscoroutinefunction(fn):
        result: dict[str, Any] = {}

        def _run():
            result["value"] = asyncio.run(fn(**kwargs))

        thread = threading.Thread(target=_run)
        thread.start()
        thread.join()
        return result["value"]
    return fn(**kwargs)

def _run_tool(name: str, arguments_json: str) -> str:
    """Execute a tool by name and return its JSON result as a string."""
    fn = next((t for t in TOOLS if t.__name__ == name), None)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        try:
            kwargs = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError:
            return json.dumps({"error": f"Invalid JSON arguments for {name}"})
        if not isinstance(kwargs, dict):
            return json.dumps({"error": f"Invalid arguments for {name}"})
        result = _invoke_tool(fn, kwargs)
        return result if isinstance(result, str) else json.dumps(result)
    except Exception as e:
        logger.exception("Error running tool %s", name)
        return json.dumps({"error": str(e)})

def _parse_final_response(raw_arguments: str, fallback_message: str = "") -> LunchMoneyAgentResponse:
    """Parse the submit_final_response arguments into a LunchMoneyAgentResponse."""
    text = raw_arguments.strip()
    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = None

    if not isinstance(data, dict):
        return LunchMoneyAgentResponse(status="success", message=text or fallback_message or "Done.")

    data.setdefault("status", "success")
    data.setdefault("message", fallback_message or "Done.")
    try:
        return LunchMoneyAgentResponse.model_validate(data)
    except Exception:
        logger.warning("Could not validate final response payload, using raw message", exc_info=True)
        return LunchMoneyAgentResponse(status="success", message=str(data.get("message") or fallback_message or text))

def execute_agent(
    user_prompt: str, config: AgentConfig, tx_id: int | None = None, telegram_message_id: int | None = None
) -> LunchMoneyAgentResponse:
    """Execute the Lunch Money agent with the given prompt and configuration.

    Args:
        user_prompt: The user's request or question
        config: AgentConfig containing chat_id, language, timezone, model preferences
        tx_id: Optional transaction ID if the request is in context of a transaction
        telegram_message_id: Optional Telegram message ID for context

    Returns:
        LunchMoneyAgentResponse with status, message, and transaction IDs

    Raises:
        Exception: Any exceptions from agent execution are propagated to caller
    """
    logger.info("Creating Lunch Money agent for chat_id: %s", config.chat_id)
    model = _get_model(config)
    logger.info("User message: %s", user_prompt)

    tools = [_tool_schema(fn) for fn in TOOLS] + [_final_tool_schema()]

    user_payload = {
        "request": user_prompt,
        "current_date_info": f"{datetime.date.today().strftime('%Y-%m-%d')} user timezone is {config.timezone}",
        "language": config.language,
        "transaction_id": tx_id,
        "chat_id": config.chat_id,
        "telegram_message_id": telegram_message_id,
    }
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload)},
    ]

    for _step in range(MAX_AGENT_STEPS):
        message = _call_llm(model, messages, tools)
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            content = message.get("content") or ""
            logger.info("Model returned plain content instead of %s", FINAL_TOOL_NAME)
            return _parse_final_response(content)

        messages.append(
            {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            name = function.get("name", "")
            arguments = function.get("arguments") or "{}"
            if name == FINAL_TOOL_NAME:
                return _parse_final_response(arguments)
            logger.info("Running tool: %s(%s)", name, arguments[:200])
            result = _run_tool(name, arguments)
            messages.append({"role": "tool", "tool_call_id": tool_call.get("id", ""), "content": result})

    raise RuntimeError(f"Agent did not finish within {MAX_AGENT_STEPS} steps")
