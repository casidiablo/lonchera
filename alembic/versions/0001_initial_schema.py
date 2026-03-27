"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-27

Baseline migration — treats the current schema (transactions, settings, analytics)
as already deployed to production. All CREATE TABLE statements use IF NOT EXISTS so
this migration is safe to run against an existing database without manual stamping.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            message_id  INTEGER NOT NULL,
            tx_id       INTEGER NOT NULL,
            chat_id     INTEGER NOT NULL,
            created_at  DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            reviewed_at DATETIME,
            recurring_type VARCHAR,
            plaid_id    VARCHAR
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            chat_id                         INTEGER NOT NULL PRIMARY KEY,
            token                           VARCHAR NOT NULL,
            poll_interval_secs              INTEGER NOT NULL DEFAULT 3600,
            created_at                      DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            last_poll_at                    DATETIME,
            auto_mark_reviewed              BOOLEAN NOT NULL DEFAULT 0,
            poll_pending                    BOOLEAN NOT NULL DEFAULT 0,
            show_datetime                   BOOLEAN NOT NULL DEFAULT 1,
            tagging                         BOOLEAN NOT NULL DEFAULT 1,
            mark_reviewed_after_categorized BOOLEAN NOT NULL DEFAULT 0,
            timezone                        VARCHAR NOT NULL DEFAULT 'UTC',
            auto_categorize_after_notes     BOOLEAN NOT NULL DEFAULT 0,
            ai_agent                        BOOLEAN NOT NULL DEFAULT 0,
            show_transcription              BOOLEAN NOT NULL DEFAULT 1,
            ai_response_language            VARCHAR,
            ai_model                        VARCHAR,
            compact_view                    BOOLEAN NOT NULL DEFAULT 0,
            ignored_accounts                VARCHAR
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS analytics (
            id    INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            key   VARCHAR NOT NULL,
            date  DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP),
            value FLOAT NOT NULL DEFAULT 0.0
        )
    """)


def downgrade() -> None:
    op.drop_table("analytics")
    op.drop_table("settings")
    op.drop_table("transactions")
