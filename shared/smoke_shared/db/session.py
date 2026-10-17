"""Engine/session helpers. SQLite WAL + FK enforcement + busy timeout.

Each operation uses its own short-lived session (`session_scope`)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

_clock = None  # injectable for tests


def utcnow() -> datetime:
    return _clock() if _clock else datetime.now(UTC)


def set_clock(fn) -> None:
    global _clock
    _clock = fn


def make_engine(url: str, busy_timeout_ms: int = 5000) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": busy_timeout_ms / 1000})
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _pragmas(conn, _):  # noqa: ANN001
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return engine


_factories: dict[int, sessionmaker] = {}


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """One session per operation; commit on success, roll back on error."""
    factory = _factories.setdefault(id(engine), sessionmaker(engine, expire_on_commit=False))
    s = factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
