from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..core.paths import get_db_path
from .tables import Base

DB_PATH = get_db_path()

engine = create_async_engine(
    f"sqlite+aiosqlite:///{DB_PATH}",
    echo=False,
    # Keep SQLite WAL mode on so reads don't block writes.
    connect_args={
        "check_same_thread": False,
        # Allow writers to wait briefly instead of immediately failing
        # with "database is locked" under concurrent activity.
        "timeout": 30,
    },
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    # WAL allows one writer and many readers concurrently.
    cursor.execute("PRAGMA journal_mode=WAL")
    # Keep wait budget aligned with connect timeout.
    cursor.execute("PRAGMA busy_timeout=30000")
    # Better fsync profile for desktop/local app workloads.
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

_session_factory = async_sessionmaker(engine, expire_on_commit=False)


def _ensure_dev_schema(sync_conn) -> None:
    email_table_info = sync_conn.execute(text("PRAGMA table_info(email_items)"))
    email_columns = {row[1] for row in email_table_info.fetchall()}
    if "conversation_id" not in email_columns:
        sync_conn.execute(text("ALTER TABLE email_items ADD COLUMN conversation_id VARCHAR"))
    if "from_name" not in email_columns:
        sync_conn.execute(text("ALTER TABLE email_items ADD COLUMN from_name VARCHAR"))

    notification_table_info = sync_conn.execute(text("PRAGMA table_info(notifications)"))
    notification_columns = {row[1] for row in notification_table_info.fetchall()}
    if "source_email_id" not in notification_columns:
        sync_conn.execute(text("ALTER TABLE notifications ADD COLUMN source_email_id VARCHAR"))
    if "details_json" not in notification_columns:
        sync_conn.execute(text("ALTER TABLE notifications ADD COLUMN details_json JSON"))


async def init_db() -> None:
    """Create all tables that don't exist yet.

    NOTE: This uses create_all which is fine for early-stage development.
    Add Alembic for proper migrations before shipping to users.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_dev_schema)


@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager that yields a database session."""
    async with _session_factory() as session:
        yield session
