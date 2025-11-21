import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import Boolean, DateTime, Float, Integer, String, and_, create_engine, delete, func, update
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from constants import TOKEN_BLOCKED, TOKEN_REVOKED
from errors import NoLunchTokenError

logger = logging.getLogger("db")

Base = declarative_base()


class Transaction(Base):
    __tablename__ = "transactions"

    # The unique identifier for the transaction in the database
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The message ID of the Telegram message associated with this transaction
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # The ID of the transaction in the Lunch Money API
    tx_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # The ID of the Telegram chat where the transaction was sent
    chat_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # The timestamp when the transaction was created in the database
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # The timestamp when the transaction was marked as reviewed, if applicable
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # The type of recurring transaction, if applicable (e.g., cleared, suggested, dismissed)
    recurring_type: Mapped[str | None] = mapped_column(String)

    # The Plaid transaction ID associated with this transaction, if available
    plaid_id: Mapped[str | None] = mapped_column(String, default=None, nullable=True)


class Settings(Base):
    __tablename__ = "settings"

    # The unique identifier for the Telegram chat
    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The Lunch Money API token associated with the chat
    token: Mapped[str] = mapped_column(String, nullable=False)

    # The interval (in seconds) at which the bot polls for new transactions
    poll_interval_secs: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)

    # The timestamp when the settings were created
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # The timestamp of the last time the bot polled for transactions
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Indicates whether transactions should be automatically marked as reviewed
    auto_mark_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Indicates whether the bot should poll for pending transactions
    poll_pending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Whether to show full date/time for transactions or just the date
    show_datetime: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Whether to create tags using the make_tag function
    tagging: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Indicates whether transactions should be marked as reviewed after categorization
    mark_reviewed_after_categorized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # The timezone for displaying dates and times
    timezone: Mapped[str] = mapped_column(String, default="UTC", nullable=False)

    # Indicates whether transactions should be automatically categorized after notes are added
    auto_categorize_after_notes: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Indicates whether AI agent is enabled
    ai_agent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Indicates whether to show transcription message after processing audio
    show_transcription: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # The language for AI agent responses (None means auto-detect from user input)
    ai_response_language: Mapped[str | None] = mapped_column(String, nullable=True)

    # The AI model to use for agent responses (None means default model)
    ai_model: Mapped[str | None] = mapped_column(String, nullable=True)

    # Whether to use compact view for transaction messages
    compact_view: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Analytics(Base):
    __tablename__ = "analytics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class Persistence:
    def __init__(self, db_path: str):
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def save_token(self, chat_id: int, token: str):
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(token=token)
            result = session.execute(stmt)
            if result.rowcount == 0:
                new_setting = Settings(chat_id=chat_id, token=token)
                session.add(new_setting)
            session.commit()

    def get_token(self, chat_id) -> str | None:
        with self.Session() as session:
            setting = session.query(Settings).filter_by(chat_id=chat_id).first()
            return setting.token if setting else None

    def get_all_registered_chats(self) -> list[int]:
        with self.Session() as session:
            return [chat.chat_id for chat in session.query(Settings.chat_id).all()]

    def was_already_sent(self, tx_id: int) -> bool:
        with self.Session() as session:
            return session.query(Transaction.message_id).filter_by(tx_id=tx_id).first() is not None

    def mark_as_sent(
        self,
        tx_id: int,
        chat_id: int,
        message_id: int,
        recurring_type: str | None,
        reviewed=False,
        plaid_id: str | None = None,
    ) -> None:
        logger.info(f"Marking transaction {tx_id} as sent with message ID {message_id}")
        with self.Session() as session:
            new_transaction = Transaction(
                message_id=message_id,
                tx_id=tx_id,
                chat_id=chat_id,
                recurring_type=recurring_type,
                reviewed_at=datetime.now() if reviewed else None,
                plaid_id=plaid_id,
            )
            session.add(new_transaction)
            session.commit()

    def get_tx_associated_with(self, message_id: int, chat_id: int) -> int | None:
        with self.Session() as session:
            transaction = session.query(Transaction.tx_id).filter_by(message_id=message_id, chat_id=chat_id).first()
            return transaction.tx_id if transaction else None

    def get_tx_by_id(self, tx_id: int) -> Transaction | None:
        with self.Session() as session:
            return session.query(Transaction).filter_by(tx_id=tx_id).first()

    def get_all_tx_by_chat_id(self, chat_id: int) -> list[Transaction]:
        with self.Session() as session:
            return session.query(Transaction).filter_by(chat_id=chat_id).all()

    def get_message_id_associated_with(self, tx_id: int, chat_id: int) -> int | None:
        with self.Session() as session:
            transaction = (
                session.query(Transaction)
                .filter_by(tx_id=tx_id, chat_id=chat_id)
                .order_by(Transaction.created_at.desc())
                .first()
            )
            return transaction.message_id if transaction else None

    def delete_transactions_for_chat(self, chat_id: int):
        with self.Session() as session:
            stmt = delete(Transaction).where(Transaction.chat_id == chat_id)
            session.execute(stmt)
            session.commit()
            logger.info(f"Transactions deleted for chat {chat_id}")

    def mark_as_reviewed(self, message_id: int, chat_id: int):
        with self.Session() as session:
            stmt = (
                update(Transaction)
                .where((Transaction.message_id == message_id) & (Transaction.chat_id == chat_id))
                .values(reviewed_at=datetime.now())
            )
            session.execute(stmt)
            session.commit()

    def mark_as_reviewed_by_tx_id(self, tx_id: int, chat_id: int):
        with self.Session() as session:
            stmt = (
                update(Transaction)
                .where((Transaction.tx_id == tx_id) & (Transaction.chat_id == chat_id))
                .values(reviewed_at=datetime.now())
            )
            session.execute(stmt)
            session.commit()

    def mark_as_unreviewed(self, message_id: int, chat_id: int):
        with self.Session() as session:
            stmt = (
                update(Transaction)
                .where((Transaction.message_id == message_id) & (Transaction.chat_id == chat_id))
                .values(reviewed_at=None)
            )
            session.execute(stmt)
            session.commit()

    def get_current_settings(self, chat_id: str | int) -> Settings:
        with self.Session() as session:
            settings = session.query(Settings).filter_by(chat_id=chat_id).first()
            if settings is None:
                raise NoLunchTokenError("No settings found")
            return settings

    def update_poll_interval(self, chat_id: int, interval: int) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(poll_interval_secs=interval)
            session.execute(stmt)
            session.commit()

    def update_last_poll_at(self, chat_id: int, timestamp: str) -> None:
        with self.Session() as session:
            stmt = (
                update(Settings)
                .where(Settings.chat_id == chat_id)
                .values(last_poll_at=datetime.fromisoformat(timestamp))
            )
            session.execute(stmt)
            session.commit()

    def logout(self, chat_id: int) -> None:
        with self.Session() as session:
            session.query(Settings).filter_by(chat_id=chat_id).delete()
            session.query(Transaction).filter_by(chat_id=chat_id).delete()
            session.commit()

    def update_auto_mark_reviewed(self, chat_id: int, auto_mark_reviewed: bool) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(auto_mark_reviewed=auto_mark_reviewed)
            session.execute(stmt)
            session.commit()

    def update_poll_pending(self, chat_id: int, poll_pending: bool) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(poll_pending=poll_pending)
            session.execute(stmt)
            session.commit()

    def update_show_datetime(self, chat_id: int, show_datetime: bool) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(show_datetime=show_datetime)
            session.execute(stmt)
            session.commit()

    def update_tagging(self, chat_id: int, tagging: bool) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(tagging=tagging)
            session.execute(stmt)
            session.commit()

    def update_mark_reviewed_after_categorized(self, chat_id: int, value: bool) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(mark_reviewed_after_categorized=value)
            session.execute(stmt)
            session.commit()

    def update_timezone(self, chat_id: int, timezone: str) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(timezone=timezone)
            session.execute(stmt)
            session.commit()

    def update_auto_categorize_after_notes(self, chat_id: int, value: bool) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(auto_categorize_after_notes=value)
            session.execute(stmt)
            session.commit()

    def update_ai_agent(self, chat_id: int, ai_agent: bool) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(ai_agent=ai_agent)
            session.execute(stmt)
            session.commit()

    def update_show_transcription(self, chat_id: int, show_transcription: bool) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(show_transcription=show_transcription)
            session.execute(stmt)
            session.commit()

    def update_ai_response_language(self, chat_id: int, language: str | None) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(ai_response_language=language)
            session.execute(stmt)
            session.commit()

    def update_ai_model(self, chat_id: int, model: str | None) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(ai_model=model)
            session.execute(stmt)
            session.commit()

    def update_compact_view(self, chat_id: int, compact_view: bool) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(compact_view=compact_view)
            session.execute(stmt)
            session.commit()

    def set_api_token(self, chat_id: int, token: str | None) -> None:
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(token=token)
            session.execute(stmt)
            session.commit()

    def inc_metric(self, key: str, increment: float = 1.0, date: datetime | None = None):
        if date is None:
            date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            date = date.replace(hour=0, minute=0, second=0, microsecond=0)

        with self.Session() as session:
            metric = session.query(Analytics).filter_by(key=key, date=date).first()
            if metric:
                metric.value = metric.value + increment
            else:
                metric = Analytics(key=key, date=date, value=increment)
                session.add(metric)
            session.commit()

    def get_metric(self, key: str, start_date: datetime, end_date: datetime) -> float:
        with self.Session() as session:
            result = (
                session.query(func.sum(Analytics.value))
                .filter(
                    and_(
                        Analytics.key == key,
                        Analytics.date >= start_date.replace(hour=0, minute=0, second=0, microsecond=0),
                        Analytics.date <= end_date.replace(hour=23, minute=59, second=59, microsecond=999999),
                    )
                )
                .scalar()
            )
            return result or 0.0

    def get_all_metrics(self, start_date: datetime, end_date: datetime) -> dict:
        with self.Session() as session:
            results = (
                session.query(Analytics.key, Analytics.date, Analytics.value)
                .filter(
                    and_(
                        Analytics.date >= start_date.replace(hour=0, minute=0, second=0, microsecond=0),
                        Analytics.date <= end_date.replace(hour=23, minute=59, second=59, microsecond=999999),
                    )
                )
                .all()
            )
            metrics = {}
            for metric_key, metric_date, value in results:
                date_key = metric_date.replace(hour=0, minute=0, second=0, microsecond=0)
                if date_key not in metrics:
                    metrics[date_key] = {}
                metrics[date_key][metric_key] = value
            return metrics

    def get_specific_metrics(self, key: str, start_date: datetime, end_date: datetime) -> dict:
        with self.Session() as session:
            results = (
                session.query(Analytics.key, Analytics.date, Analytics.value)
                .filter(
                    and_(
                        Analytics.key == key,
                        Analytics.date >= start_date.replace(hour=0, minute=0, second=0, microsecond=0),
                        Analytics.date <= end_date.replace(hour=23, minute=59, second=59, microsecond=999999),
                    )
                )
                .all()
            )
            metrics = {}
            for metric_key, metric_date, value in results:
                date_key = metric_date.replace(hour=0, minute=0, second=0, microsecond=0)
                if date_key not in metrics:
                    metrics[date_key] = {}
                metrics[date_key][metric_key] = value
            return metrics

    def mark_user_as_blocked(self, chat_id: int) -> None:
        """Mark a user as blocked by setting token to TOKEN_BLOCKED constant value."""
        with self.Session() as session:
            stmt = update(Settings).where(Settings.chat_id == chat_id).values(token=TOKEN_BLOCKED)
            session.execute(stmt)
            session.commit()
            logger.info(f"User {chat_id} marked as blocked")

    def get_blocked_users(self) -> list[int]:
        """Get all blocked users' chat_ids.

        Returns:
            List of chat_ids for users with token == TOKEN_BLOCKED
        """
        with self.Session() as session:
            # Query Settings table for blocked users
            blocked_settings = session.query(Settings.chat_id).filter(Settings.token == TOKEN_BLOCKED).all()
            return [chat_id for (chat_id,) in blocked_settings]

    def get_user_transaction_count(self, chat_id: int) -> int:
        """Get count of transactions associated with a user.

        Args:
            chat_id: The chat ID to get transaction count for

        Returns:
            Number of transactions for this user
        """
        with self.Session() as session:
            return session.query(Transaction).filter(Transaction.chat_id == chat_id).count()

    def is_user_blocked(self, chat_id: int) -> bool:
        """Check if a user is blocked (token == TOKEN_BLOCKED).

        Args:
            chat_id: The chat ID to check

        Returns:
            True if token equals TOKEN_BLOCKED, False otherwise
        """
        with self.Session() as session:
            setting = session.query(Settings).filter(Settings.chat_id == chat_id).first()
            return setting is not None and setting.token == TOKEN_BLOCKED

    def delete_user_data(self, chat_id: int) -> dict[str, int]:
        """Delete all data for a user and return counts of deleted records.

        Args:
            chat_id: The chat ID whose data should be deleted

        Returns:
            Dictionary with counts of deleted records from each table:
            {"transactions": count, "settings": count, "analytics": count}
        """
        with self.Session() as session:
            # Count records before deletion
            transaction_count = session.query(Transaction).filter(Transaction.chat_id == chat_id).count()
            settings_count = session.query(Settings).filter(Settings.chat_id == chat_id).count()
            # Analytics don't have chat_id, so we can't delete them by chat_id
            analytics_count = 0

            # Delete all Transaction records for chat_id
            session.query(Transaction).filter(Transaction.chat_id == chat_id).delete()

            # Delete Settings record for chat_id
            session.query(Settings).filter(Settings.chat_id == chat_id).delete()

            # Commit the transaction
            session.commit()

            logger.info(
                f"Deleted user data for chat_id {chat_id}: {transaction_count} transactions, {settings_count} settings"
            )

            return {"transactions": transaction_count, "settings": settings_count, "analytics": analytics_count}

    def get_user_count(self) -> int:
        with self.Session() as session:
            return (
                session.query(Settings).filter(Settings.token != TOKEN_REVOKED, Settings.token != TOKEN_BLOCKED).count()
            )

    def get_db_size(self) -> int:
        db_path = self.engine.url.database
        if db_path is not None:
            return os.path.getsize(db_path)
        return 0

    def get_sent_message_count(self) -> int:
        with self.Session() as session:
            return session.query(Transaction).count()

    def get_sent_transactions(self, chat_id: int, since: datetime | None = None) -> list[Transaction]:
        """Get all previously sent transactions for a specific chat from a given date (defaults to last 3 months)."""
        with self.Session() as session:
            if since is None:
                since = datetime.now() - timedelta(days=90)  # Set default since date to 90 days ago
            return (
                session.query(Transaction).filter(Transaction.chat_id == chat_id, Transaction.created_at >= since).all()
            )

    def update_transaction_ids_by_plaid_id(self, old_plaid_id: str, new_tx_id: int, new_plaid_id: str | None) -> bool:
        """Update transaction tx_id and plaid_id by matching old plaid_id."""
        with self.Session() as session:
            stmt = (
                update(Transaction)
                .where(Transaction.plaid_id == old_plaid_id)
                .values(tx_id=new_tx_id, plaid_id=new_plaid_id)
            )
            result = session.execute(stmt)
            session.commit()
            return result.rowcount > 0


db = None


def get_db() -> Persistence:
    global db
    if db is None:
        db = Persistence(os.getenv("DB_PATH", "lonchera.db"))
    return db
