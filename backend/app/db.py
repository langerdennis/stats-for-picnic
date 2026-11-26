from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def _configure_sqlite_connection(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def create_sqlite_engine(database_url: str) -> Engine:
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_db_engine(settings: Settings | None = None) -> Engine:
    global _engine, _session_factory
    cfg = settings or get_settings()
    _engine = create_sqlite_engine(cfg.database_url)
    _session_factory = sessionmaker(bind=_engine, autocommit=False, autoflush=False, class_=Session)
    return _engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        return init_db_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        init_db_engine()
    assert _session_factory is not None
    return _session_factory


def get_db() -> Generator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def create_all_tables(engine: Engine | None = None) -> None:
    # Ensure models are imported before creating metadata
    import app.models  # noqa: F401

    target_engine = engine or get_engine()
    Base.metadata.create_all(bind=target_engine)
