"""Opaque random session tokens, stored only as SHA-256 hashes."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from smoke_shared.db import models as m
from smoke_shared.db import utcnow
from sqlalchemy import select
from sqlalchemy.orm import Session

COOKIE = "sm_session"


def _h(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


def create_session(db: Session, user_id: str, ttl_hours: int) -> tuple[str, str]:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(
        m.Session(
            token_hash=_h(token),
            csrf_token_hash=_h(csrf),
            user_id=user_id,
            expires_at=utcnow() + timedelta(hours=ttl_hours),
        )
    )
    db.commit()
    return token, csrf


def lookup(db: Session, token: str) -> tuple[m.Session, m.User] | None:
    row = db.execute(select(m.Session).where(m.Session.token_hash == _h(token))).scalar_one_or_none()
    if not row or row.revoked_at or row.expires_at <= utcnow():
        return None
    user = db.get(m.User, row.user_id)
    if not user or not user.active:
        return None
    return row, user


def csrf_ok(sess: m.Session, supplied: str | None) -> bool:
    return bool(supplied) and secrets.compare_digest(_h(supplied), sess.csrf_token_hash)


def revoke(db: Session, sess: m.Session) -> None:
    sess.revoked_at = utcnow()
    db.commit()


def revoke_all_for_user(db: Session, user_id: str, except_id: str | None = None) -> None:
    for s in db.execute(select(m.Session).where(m.Session.user_id == user_id, m.Session.revoked_at.is_(None))).scalars():
        if s.id != except_id:
            s.revoked_at = utcnow()
    db.commit()
