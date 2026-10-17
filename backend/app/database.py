from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker


def get_db(request: Request) -> Iterator[Session]:
    """One short-lived session per request. Commit is explicit in services."""
    factory: sessionmaker = request.app.state.session_factory
    s = factory()
    try:
        yield s
    finally:
        s.close()
