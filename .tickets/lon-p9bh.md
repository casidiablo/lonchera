---
id: lon-p9bh
status: closed
deps: []
links: []
created: 2026-03-27T17:23:58Z
type: task
priority: 2
assignee: Cristian
---
# Add Alembic SQL migration support

Replace Base.metadata.create_all() with Alembic-managed migrations. The existing schema (transactions, settings, analytics tables — including mark_reviewed_after_categorized already applied via alter_table.sql) is treated as the baseline initial migration.

## Design

**Dependency**
- Add alembic to pyproject.toml dependencies and regenerate uv.lock

**Layout (conventional, project root)**
- alembic.ini at project root
- alembic/env.py — imports persistence.Base, builds sqlite URL from os.getenv('DB_PATH', 'lonchera.db')
- alembic/versions/0001_initial_schema.py — baseline migration covering all 3 tables

**Initial migration**
- upgrade() creates all 3 tables using op.create_table() with CREATE TABLE IF NOT EXISTS guards (idempotent against existing prod DB)
- downgrade() drops all 3 tables
- Covers full column definitions for transactions, settings, analytics

**Persistence.__init__ change**
- Remove Base.metadata.create_all(self.engine) — schema management moves entirely to Alembic

**Dockerfile CMD change**
- FROM: CMD ["python", "main.py"]
- TO:   CMD alembic upgrade head && python main.py

**docker-compose.yml command change**
- FROM: command: ["python", "main.py"]
- TO:   command: ["sh", "-c", "alembic upgrade head && python main.py"]

**Cleanup**
- Delete handlers/alter_table.sql (superseded by initial migration)

## Acceptance Criteria

- uv run alembic upgrade head runs successfully on a fresh SQLite DB and creates all 3 tables
- Running alembic upgrade head against the existing prod DB is a no-op (idempotent)
- uv run alembic downgrade base drops all 3 tables on a fresh DB
- uv run alembic revision --autogenerate works for future schema changes (env.py wired to metadata)
- Docker container starts correctly: migration runs then main.py launches
- Base.metadata.create_all() is removed from Persistence.__init__
- handlers/alter_table.sql is deleted
- uv run ruff format . && uv run ruff check . passes with no errors

