"""Standalone testing script for the Lunch Money agent engine.

This allows testing the agent logic independently without Telegram bot integration.

Usage:
    python handlers/aitools/test_agent.py
    python handlers/aitools/test_agent.py --prompt "Show me my balances"
    python handlers/aitools/test_agent.py --mlflow https://mlflow.example.com --prompt "What are my recent transactions?"
    python handlers/aitools/test_agent.py --chat-id 987654321 --language Spanish --timezone "Europe/Madrid"
"""

import argparse
import logging
import sys
from pathlib import Path

import mlflow

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from handlers.aitools.agent_engine import AgentConfig, execute_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Run the agent with command-line arguments."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Test Lunch Money agent with optional MLflow tracking")
    parser.add_argument("--mlflow", type=str, help="MLflow tracking URI (e.g., https://mlflow.example.com)")
    parser.add_argument(
        "--prompt", type=str, default="What are my recent transactions?", help="Prompt to test with the agent"
    )
    parser.add_argument("--chat-id", type=int, default=123456789, help="Chat ID to use for testing")
    parser.add_argument("--language", type=str, default="English", help="Response language")
    parser.add_argument("--timezone", type=str, default="America/New_York", help="User timezone")
    parser.add_argument("--model", type=str, help="Model name to use (requires admin)")
    parser.add_argument("--admin", action="store_true", help="Enable admin mode for advanced models")
    args = parser.parse_args()

    # Setup MLflow if requested
    mlflow_enabled = args.mlflow is not None
    if mlflow_enabled:
        mlflow.set_tracking_uri(args.mlflow)
        mlflow.set_experiment("lonchera")
        mlflow.dspy.autolog()
        logger.info(f"MLflow tracking enabled: {args.mlflow}")

    # Create AgentConfig with command-line arguments
    test_config = AgentConfig(
        chat_id=args.chat_id, language=args.language, timezone=args.timezone, model_name=args.model, is_admin=args.admin
    )

    try:
        if mlflow_enabled:
            with mlflow.start_run():
                mlflow.log_param("prompt", args.prompt)
                mlflow.log_param("language", test_config.language)
                mlflow.log_param("timezone", test_config.timezone)
                mlflow.log_param("chat_id", test_config.chat_id)

                # Execute the agent
                response = execute_agent(
                    user_prompt=args.prompt, config=test_config, tx_id=None, telegram_message_id=None
                )

                # Log results to MLflow
                mlflow.log_metric("status", 1 if response.status == "success" else 0)
                mlflow.log_text(response.message, "response_message.txt")

                # Print results
                print(f"Status: {response.status}")
                print(f"\nMessage:\n{response.message}")

                if response.transactions_created_ids:
                    print(f"\nTransactions Created: {response.transactions_created_ids}")
                    mlflow.log_param("transactions_created", len(response.transactions_created_ids))

                if response.transaction_updated_ids:
                    print(f"\nTransactions Updated: {response.transaction_updated_ids}")
                    mlflow.log_param("transactions_updated", len(response.transaction_updated_ids))
        else:
            # Execute without MLflow
            response = execute_agent(user_prompt=args.prompt, config=test_config, tx_id=None, telegram_message_id=None)

            # Print results
            print(f"Status: {response.status}")
            print(f"\nMessage:\n{response.message}")

            if response.transactions_created_ids:
                print(f"\nTransactions Created: {response.transactions_created_ids}")

            if response.transaction_updated_ids:
                print(f"\nTransactions Updated: {response.transaction_updated_ids}")

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        logger.exception("Error executing agent")

        if mlflow_enabled:
            mlflow.log_param("error", str(e))


if __name__ == "__main__":
    main()
