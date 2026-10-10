"""SQLite engine. One Database object lives on app.state."""

from __future__ import annotations

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine


class Database:
    def __init__(self, path: str) -> None:
        # check_same_thread=False: endpoints run in Starlette's worker threadpool.
        self.engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", _tune_sqlite)
        SQLModel.metadata.create_all(self.engine)

    def session(self) -> Session:
        return Session(self.engine, expire_on_commit=False)


def _tune_sqlite(dbapi_connection, _record) -> None:
    """Hooks and API requests write concurrently, so make SQLite cope.

    WAL lets a reader (the laptop's SSE/manifest calls) run while a hook is writing.
    busy_timeout makes the second writer wait for the lock instead of raising
    "database is locked", which would surface as a 500.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
