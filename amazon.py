import csv
from datetime import datetime, timedelta
import os
from typing import Dict
from collections import defaultdict
import logging
import argparse
import sys

from dotenv import load_dotenv
from lunchable import TransactionUpdateObject

from deepinfra import get_suggested_category_id
from lunch import get_lunch_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("amz")


def parse_date_time(d: str) -> datetime:
    try:
        return datetime.strptime(d, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return datetime.strptime(d, "%Y-%m-%dT%H:%M:%SZ")


def parse_csv_and_filter(
    file_path: str,
    target_date: str,
    target_price: float,
    target_currency: str,
    allow_days: int,
) -> Dict[str, str]:
    # Convert target_date string to a datetime object
    target_date = datetime.strptime(target_date, "%Y-%m-%d")

    # Define the date range for filtering
    start_date = target_date - timedelta(days=allow_days)
    end_date = target_date + timedelta(days=allow_days)

    closest_result = None
    closest_date_diff = timedelta.max
    order_data = defaultdict(
        lambda: {"total_owed": 0.0, "currency": "", "product_names": [], "rows": []}
    )

    margin_of_error = 0.5

    # Read and parse the CSV file
    with open(file_path, mode="r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            # Convert the "Order Date" in the row to a datetime object
            order_date = parse_date_time(row["Order Date"])

            # Remove commas from the "Total Owed" string and convert to float
            total_owed = float(row["Total Owed"].replace(",", ""))
            currency = row["Currency"]
            order_id = row["Order ID"]
            product_name = row["Product Name"]

            # Aggregate data by order ID
            if start_date <= order_date <= end_date:
                order_data[order_id]["total_owed"] += total_owed
                order_data[order_id]["currency"] = currency
                order_data[order_id]["product_names"].append(product_name)
                order_data[order_id]["rows"].append(row)

    # Check aggregated data against target price and currency
    for order_id, data in order_data.items():
        if (
            abs(data["total_owed"] - target_price) <= margin_of_error
            and data["currency"].lower() == target_currency.lower()
        ):
            date_diff = abs(
                target_date - parse_date_time(data["rows"][0]["Order Date"])
            )
            if date_diff < closest_date_diff:
                closest_date_diff = date_diff
                closest_result = {
                    "Order ID": order_id,
                    "Total Owed": str(data["total_owed"]),
                    "Currency": data["currency"],
                    "Product Name": ", ".join(data["product_names"]),
                }
        else:
            # Check individual rows if the aggregated total does not match
            for row in data["rows"]:
                total_owed = float(row["Total Owed"].replace(",", ""))
                currency = row["Currency"]
                if (
                    abs(total_owed - target_price) <= margin_of_error
                    and currency.lower() == target_currency.lower()
                ):
                    date_diff = abs(target_date - parse_date_time(row["Order Date"]))
                    if date_diff < closest_date_diff:
                        closest_date_diff = date_diff
                        closest_result = {
                            "Order ID": row["Order ID"],
                            "Total Owed": row["Total Owed"],
                            "Currency": row["Currency"],
                            "Product Name": row["Product Name"],
                        }

    return closest_result


def get_amazon_transactions_summary(file_path: str):
    """Just return a summary of the transactions in the CSV file."""
    logger.info("Getting summary of transactions in %s", file_path)
    summary = defaultdict(int)
    summary["total_transactions"] = 0
    date_ranges = {"start_date": None, "end_date": None}
    with open(file_path, mode="r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        transactions = list(reader)
        summary["total_transactions"] = len(transactions)

        if transactions:
            dates = [parse_date_time(row["Order Date"]) for row in transactions]
            date_ranges["start_date"] = min(dates).strftime("%Y-%m-%d")
            date_ranges["end_date"] = max(dates).strftime("%Y-%m-%d")

    summary.update(date_ranges)
    logger.info(
        "Found %d transactions from %s to %s",
        summary["total_transactions"],
        summary["start_date"],
        summary["end_date"],
    )
    return summary


def process_amazon_transactions(
    file_path: str,
    days_back: int,
    dry_run: bool,
    allow_days: int,
    auto_categorize: True,
    lunch_money_token: str = None,
) -> dict:
    logger.info(
        f"Processing Amazon transactions in {file_path} with {days_back} days back and {allow_days} days threshold"
    )
    load_dotenv()
    if not lunch_money_token:
        lunch_money_token = os.getenv("LUNCH_MONEY_TOKEN")
        if not lunch_money_token:
            logger.error("LUNCH_MONEY_TOKEN environment variable not set")
            sys.exit(1)

    lunch = get_lunch_client(lunch_money_token)
    categories = lunch.get_categories()
    today = datetime.now()
    today = today.replace(hour=0, minute=0, second=0, microsecond=0)

    start_date = today - timedelta(days=days_back)
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    amz = lunch.get_transactions(start_date=start_date, end_date=today)

    logger.info(
        "Pulled transactions for range %s to %s, got %d transactions",
        start_date,
        today,
        len(amz),
    )
    amz = [a for a in amz if a.payee == "Amazon" and a.amount > 0]

    amz_cnt = len(amz)
    found_cnt = 0
    will_update = 0
    report = {
        "processed_transactions": amz_cnt,
        "updates": [],
    }
    for a in amz:
        found = parse_csv_and_filter(
            file_path, a.date.strftime("%Y-%m-%d"), a.amount, a.currency, allow_days
        )
        if not found:
            a.plaid_metadata = None
            logger.info("🚫 Amazon transaction not found for %s", a)
            continue

        found_cnt += 1
        if a.notes is None:
            logger.info(
                "Will update tx %s %s %s %s with %s",
                a.date,
                a.amount,
                a.currency,
                a.notes,
                found,
            )

            category_id = a.category_id
            previous_category_name = [c.name for c in categories if c.id == category_id]
            previous_category_name = (
                previous_category_name[0] if previous_category_name else None
            )

            product_name = found["Product Name"]
            if auto_categorize:
                _, cat_id = get_suggested_category_id(
                    tx_id=a.id, lunch=lunch, override_notes=product_name
                )
                # make sure the category exists, since LLMs hallucinate
                if cat_id not in [c.id for c in categories]:
                    category_id = a.category_id  # just leave it as is
                else:
                    category_id = cat_id

            if not dry_run:
                if len(product_name) > 350:
                    product_name = product_name[:350]

                logger.info(
                    lunch.update_transaction(
                        a.id,
                        TransactionUpdateObject(
                            notes=product_name, category_id=category_id
                        ),
                    )
                )
            category_name = [c.name for c in categories if c.id == category_id]
            category_name = category_name[0] if category_name else None
            report["updates"].append(
                {
                    "transaction_id": a.id,
                    "date": a.date.strftime("%Y-%m-%d"),
                    "amount": a.amount,
                    "currency": a.currency,
                    "notes": found["Product Name"],
                    "account_name": a.account_display_name,
                    "category_id": category_id,
                    "previous_category_name": previous_category_name,
                    "new_category_name": category_name,
                }
            )
            will_update += 1
        else:
            logger.info(
                "Already has notes for %s %s %s %s",
                a.date,
                a.amount,
                a.currency,
                a.notes,
            )

    logger.info("Processed %d Amazon transactions", amz_cnt)
    logger.info("Will update %d Amazon transactions out of %d", will_update, found_cnt)
    report["found_transactions"] = found_cnt
    report["will_update_transactions"] = will_update
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process Amazon transactions.")
    parser.add_argument("file_path", type=str, help="Path to the orders CSV file")
    parser.add_argument(
        "--days-back",
        type=int,
        default=365,
        help="Number of days back to pull transactions (default: 365)",
    )
    parser.add_argument(
        "--allow-days",
        type=int,
        default=5,
        help="Number of days threshold for matching against the CSV (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show transactions to be updated without actually updating",
    )
    parser.add_argument(
        "--auto-categorize",
        action="store_true",
        help="Automatically categorize transactions using AI",
        default=False,
    )
    args = parser.parse_args()
    result = process_amazon_transactions(
        args.file_path,
        args.days_back,
        args.dry_run,
        args.allow_days,
        args.auto_categorize,
    )
    print(result)
