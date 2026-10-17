from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from smoke_shared.crypto import SecretBox
from smoke_shared.db import models as m
from smoke_shared.enums import Role
from sqlalchemy.orm import Session

from .database import get_db
from .errors import ApiError
from .security import sessions

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_RANK = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2}


@dataclass
class Principal:
    user: m.User
    session: m.Session


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    token = request.cookies.get(sessions.COOKIE)
    found = sessions.lookup(db, token) if token else None
    if not found:
        raise ApiError(401, "UNAUTHENTICATED", "Authentication required.")
    sess, user = found
    # CSRF: all state-changing cookie-authenticated requests need the per-session token.
    if request.method not in SAFE_METHODS and not sessions.csrf_ok(sess, request.headers.get("x-csrf-token")):
        raise ApiError(403, "CSRF_FAILED", "Missing or invalid CSRF token.")
    request.state.principal = Principal(user, sess)
    return Principal(user, sess)


def require_role(minimum: Role):  # noqa: ANN201
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if _RANK[Role(p.user.role)] < _RANK[minimum]:
            raise ApiError(403, "FORBIDDEN", "Your role does not permit this action.")
        return p

    return dep


viewer = require_role(Role.VIEWER)
operator = require_role(Role.OPERATOR)
admin = require_role(Role.ADMIN)


def get_box(request: Request) -> SecretBox:
    box = request.app.state.secret_box
    if box is None:
        raise ApiError(503, "SECRETS_NOT_CONFIGURED", "Encryption key is not configured on the server.")
    return box


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
