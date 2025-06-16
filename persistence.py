import logging
import os
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, and_, create_engine, delete, func, update
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from errors import NoLunchTokenError

logger = logging.getLogger("db")

Base = declarative_base()


class Transaction(Base):
    __tablename__ = "transactions"

    # The unique identifier for the transaction in the database
    id = Column(Integer, primary_key=True, autoincrement=True)

    # The message ID of the Telegram message associated with this transaction
    message_id = Column(Integer, nullable=False)

    # The ID of the transaction in the Lunch Money API
    tx_id = Column(Integer, nullable=False)

    # The ID of the Telegram chat where the transaction was sent
    chat_id = Column(Integer, nullable=False)

    # Indicates whether the transaction is pending or not
    pending = Column(Boolean, default=False, nullable=False)

    # The timestamp when the transaction was created in the database
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # The timestamp when the transaction was marked as reviewed, if applicable
    reviewed_at = Column(DateTime)

    # The type of recurring transaction, if applicable (e.g., cleared, suggested, dismissed)
    recurring_type = Column(String)

    # The Plaid transaction ID associated with this transaction, if available
    plaid_id = Column(String, default=None, nullable=True)


class Settings(Base):
    __tablename__ = "settings"

    # The unique identifier for the Telegram chat
    chat_id = Column(Integer, primary_key=True)

    # The Lunch Money API token associated with the chat
    token = Column(String, nullable=False)

    # The interval (in seconds) at which the bot polls for new transactions
    poll_interval_secs = Column(Integer, default=3600, nullable=False)

    # The timestamp when the settings were created
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # The timestamp of the last time the bot polled for transactions
    last_poll_at = Column(DateTime)

    # Indicates whether transactions should be automatically marked as reviewed
    auto_mark_reviewed = Column(Boolean, default=False, nullable=False)

    # Indicates whether the bot should poll for pending transactions
    poll_pending = Column(Boolean, default=False, nullable=False)

    # Whether to show full date/time for transactions or just the date
    show_datetime = Column(Boolean, default=True, nullable=False)

    # Whether to create tags using the make_tag function
    tagging = Column(Boolean, default=True, nullable=False)

    # Indicates whether transactions should be marked as reviewed after categorization
    mark_reviewed_after_categorized = Column(Boolean, default=False, nullable=False)

    # The timezone for displaying dates and times
    timezone = Column(String, default="UTC", nullable=False)

    # Indicates whether transactions should be automatically categorized after notes are added
    auto_categorize_after_notes = Column(Boolean, default=False, nullable=False)


class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False)
    date = Column(DateTime, default=func.now(), nullable=False)
    value = Column(Float, default=0.0, nullable=False)


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

    def was_already_sent(self, tx_id: int, pending: bool = False) -> bool:
        with self.Session() as session:
            return session.query(Transaction.message_id).filter_by(tx_id=tx_id, pending=pending).first() is not None

    def mark_as_sent(
        self,
        tx_id: int,
        chat_id: int,
        message_id: int,
        recurring_type: str | None,
        pending=False,
        reviewed=False,
        plaid_id: str | None = None,
    ) -> None:
        logger.info(f"Marking transaction {tx_id} as sent with message ID {message_id}")
        with self.Session() as session:
            new_transaction = Transaction(
                message_id=message_id,
                tx_id=tx_id,
                chat_id=chat_id,
                pending=pending,
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
                raise NoLunchTokenError("No settings found for this chat")
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
                metric.value += increment
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

    def get_user_count(self) -> int:
        with self.Session() as session:
            return session.query(Settings).filter(Settings.token != "revoked").count()

    def get_db_size(self) -> int:
        return os.path.getsize(self.engine.url.database)

    def get_sent_message_count(self) -> int:
        with self.Session() as session:
            return session.query(Transaction).count()


db = None


def get_db() -> Persistence:
    global db
    if db is None:
        db = Persistence(os.getenv("DB_PATH", "lonchera.db"))
    return db
