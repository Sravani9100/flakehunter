from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    # SQLite connections are shared with FastAPI's threadpool and background tasks.
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)
