"""SQLite engine. One Database object lives on app.state."""

from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine


class Database:
    def __init__(self, path: str) -> None:
        # check_same_thread=False: endpoints run in Starlette's worker threadpool.
        self.engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False},
        )
        SQLModel.metadata.create_all(self.engine)

    def session(self) -> Session:
        return Session(self.engine, expire_on_commit=False)