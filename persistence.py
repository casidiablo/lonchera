import logging
import os
from typing import List, Optional, Union
from datetime import datetime

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    update,
    delete,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func

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


class Persistence:
    def __init__(self, db_path: str):
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def save_token(self, chat_id: int, token: str):
        with self.Session() as session:
            stmt = (
                update(Settings).where(Settings.chat_id == chat_id).values(token=token)
            )
            result = session.execute(stmt)
            if result.rowcount == 0:
                new_setting = Settings(chat_id=chat_id, token=token)
                session.add(new_setting)
            session.commit()

    def get_token(self, chat_id) -> Union[str, None]:
        with self.Session() as session:
            setting = session.query(Settings).filter_by(chat_id=chat_id).first()
            return setting.token if setting else None

    def get_all_registered_chats(self) -> List[int]:
        with self.Session() as session:
            return [chat.chat_id for chat in session.query(Settings.chat_id).all()]

    def was_already_sent(self, tx_id: int, pending: bool = False) -> bool:
        with self.Session() as session:
            return (
                session.query(Transaction.message_id)
                .filter_by(tx_id=tx_id, pending=pending)
                .first()
                is not None
            )

    def mark_as_sent(
        self,
        tx_id: int,
        chat_id: int,
        message_id: int,
        recurring_type: Optional[str],
        pending=False,
        reviewed=False,
        plaid_id: Optional[str] = None,
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

    def get_tx_associated_with(self, message_id: int, chat_id: int) -> Optional[int]:
        with self.Session() as session:
            transaction = (
                session.query(Transaction.tx_id)
                .filter_by(message_id=message_id, chat_id=chat_id)
                .first()
            )
            return transaction.tx_id if transaction else None

    def get_tx_by_id(self, tx_id: int) -> Optional[Transaction]:
        with self.Session() as session:
            return session.query(Transaction).filter_by(tx_id=tx_id).first()

    def get_all_tx_by_chat_id(self, chat_id: int) -> List[Transaction]:
        with self.Session() as session:
            return session.query(Transaction).filter_by(chat_id=chat_id).all()

    def get_message_id_associated_with(self, tx_id: int, chat_id: int) -> Optional[int]:
        with self.Session() as session:
            transaction = (
                session.query(Transaction)
                .filter_by(tx_id=tx_id, chat_id=chat_id)
                .order_by(Transaction.created_at.desc())
                .first()
            )
            return transaction.message_id if transaction else None

    def nuke(self, chat_id: int):
        with self.Session() as session:
            stmt = delete(Transaction).where(Transaction.chat_id == chat_id)
            session.execute(stmt)
            session.commit()
            logger.info(f"Transactions deleted for chat {chat_id}")

    def mark_as_reviewed(self, message_id: int, chat_id: int):
        with self.Session() as session:
            stmt = (
                update(Transaction)
                .where(
                    (Transaction.message_id == message_id)
                    & (Transaction.chat_id == chat_id)
                )
                .values(reviewed_at=datetime.now())
            )
            session.execute(stmt)
            session.commit()

    def mark_as_unreviewed(self, message_id: int, chat_id: int):
        with self.Session() as session:
            stmt = (
                update(Transaction)
                .where(
                    (Transaction.message_id == message_id)
                    & (Transaction.chat_id == chat_id)
                )
                .values(reviewed_at=None)
            )
            session.execute(stmt)
            session.commit()

    def get_current_settings(self, chat_id: int) -> Settings:
        with self.Session() as session:
            return session.query(Settings).filter_by(chat_id=chat_id).first()

    def update_poll_interval(self, chat_id: int, interval: int) -> None:
        with self.Session() as session:
            stmt = (
                update(Settings)
                .where(Settings.chat_id == chat_id)
                .values(poll_interval_secs=interval)
            )
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
            stmt = (
                update(Settings)
                .where(Settings.chat_id == chat_id)
                .values(auto_mark_reviewed=auto_mark_reviewed)
            )
            session.execute(stmt)
            session.commit()

    def update_poll_pending(self, chat_id: int, poll_pending: bool) -> None:
        with self.Session() as session:
            stmt = (
                update(Settings)
                .where(Settings.chat_id == chat_id)
                .values(poll_pending=poll_pending)
            )
            session.execute(stmt)
            session.commit()

    def update_show_datetime(self, chat_id: int, show_datetime: bool) -> None:
        with self.Session() as session:
            stmt = (
                update(Settings)
                .where(Settings.chat_id == chat_id)
                .values(show_datetime=show_datetime)
            )
            session.execute(stmt)
            session.commit()

    def update_tagging(self, chat_id: int, tagging: bool) -> None:
        with self.Session() as session:
            stmt = (
                update(Settings)
                .where(Settings.chat_id == chat_id)
                .values(tagging=tagging)
            )
            session.execute(stmt)
            session.commit()

    def update_mark_reviewed_after_categorized(self, chat_id: int, value: bool) -> None:
        with self.Session() as session:
            stmt = (
                update(Settings)
                .where(Settings.chat_id == chat_id)
                .values(mark_reviewed_after_categorized=value)
            )
            session.execute(stmt)
            session.commit()

    def update_timezone(self, chat_id: int, timezone: str) -> None:
        with self.Session() as session:
            stmt = (
                update(Settings)
                .where(Settings.chat_id == chat_id)
                .values(timezone=timezone)
            )
            session.execute(stmt)
            session.commit()

    def update_auto_categorize_after_notes(self, chat_id: int, value: bool) -> None:
        with self.Session() as session:
            stmt = (
                update(Settings)
                .where(Settings.chat_id == chat_id)
                .values(auto_categorize_after_notes=value)
            )
            session.execute(stmt)
            session.commit()


db = None


def get_db() -> Persistence:
    global db
    if db is None:
        db = Persistence(os.getenv("DB_PATH", "lonchera.db"))
    return db
