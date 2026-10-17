from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Request, Response
from smoke_shared.db import models as m
from smoke_shared.db import utcnow
from smoke_shared.enums import Role
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import Principal, client_ip, current_principal
from ..errors import ApiError
from ..schemas.auth import ChangePasswordIn, InitialAdminIn, LoginIn, LoginOut, SetupStatus, UserOut
from ..security import sessions
from ..security.password import check_strength, hash_password, verify_password
from ..services.audit import audit

router = APIRouter(prefix="/api/v1", tags=["auth"])

# Hash used to equalize timing for unknown usernames.
_DUMMY = hash_password("dummy-password-for-timing")


def _set_cookie(request: Request, response: Response, token: str) -> None:
    s = request.app.state.settings
    response.set_cookie(sessions.COOKIE, token, httponly=True, secure=s.session_cookie_secure,
                        samesite="lax", max_age=s.session_ttl_hours * 3600, path="/")


@router.get("/setup/status", response_model=SetupStatus)
def setup_status(db: Session = Depends(get_db)) -> SetupStatus:
    n = db.execute(select(func.count()).select_from(m.User)).scalar_one()
    return SetupStatus(needs_initial_admin=n == 0)


@router.post("/setup/initial-admin", response_model=UserOut, status_code=201)
def initial_admin(body: InitialAdminIn, request: Request, db: Session = Depends(get_db)) -> m.User:
    s = request.app.state.settings
    # Bootstrap requires a locally-known token; with none configured it is disabled entirely.
    if not s.setup_token or not hmac.compare_digest(body.setup_token, s.setup_token):
        raise ApiError(403, "SETUP_FORBIDDEN", "Invalid or unconfigured setup token.")
    if body.password != body.password_confirm:
        raise ApiError(422, "VALIDATION_ERROR", "Passwords do not match.")
    if (msg := check_strength(body.password)):
        raise ApiError(422, "WEAK_PASSWORD", msg)
    # Race-safety: a single-row guard table-less approach — insert user with fixed id guard.
    user = m.User(id="00000000-0000-0000-0000-000000000001", username=body.username,
                  password_hash=hash_password(body.password), role=Role.ADMIN.value)
    if db.execute(select(func.count()).select_from(m.User)).scalar_one() > 0:
        raise ApiError(409, "SETUP_DONE", "An administrator already exists.")
    db.add(user)
    audit(db, user.id, "setup.initial_admin", "user", user.id, ip=client_ip(request))
    try:
        db.commit()  # PK collision makes concurrent bootstrap attempts fail atomically
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "SETUP_DONE", "An administrator already exists.") from None
    return user


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> LoginOut:
    throttle = request.app.state.throttle
    key = f"{body.username.lower()}|{client_ip(request)}"
    if throttle.blocked(key):
        raise ApiError(429, "RATE_LIMITED", "Too many failed attempts. Try again later.")
    user = db.execute(select(m.User).where(m.User.username == body.username)).scalar_one_or_none()
    ok = verify_password(user.password_hash if user else _DUMMY, body.password)
    if not (user and ok and user.active):
        throttle.fail(key)
        audit(db, None, "auth.login_failed", "user", None, {"username": body.username}, client_ip(request))
        db.commit()
        raise ApiError(401, "INVALID_CREDENTIALS", "Invalid username or password.")
    throttle.success(key)
    user.last_login_at = utcnow()
    token, csrf = sessions.create_session(db, user.id, request.app.state.settings.session_ttl_hours)
    audit(db, user.id, "auth.login", "user", user.id, ip=client_ip(request))
    db.commit()
    _set_cookie(request, response, token)
    return LoginOut(user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/auth/logout", status_code=204)
def logout(response: Response, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> None:
    sessions.revoke(db, db.merge(p.session))
    response.delete_cookie(sessions.COOKIE, path="/")


@router.get("/auth/me", response_model=UserOut)
def me(p: Principal = Depends(current_principal)) -> m.User:
    return p.user


@router.post("/auth/change-password", status_code=204)
def change_password(body: ChangePasswordIn, request: Request, p: Principal = Depends(current_principal),
                    db: Session = Depends(get_db)) -> None:
    user = db.get(m.User, p.user.id)
    if not verify_password(user.password_hash, body.current_password):
        raise ApiError(403, "INVALID_CREDENTIALS", "Current password is incorrect.")
    if body.new_password != body.new_password_confirm:
        raise ApiError(422, "VALIDATION_ERROR", "Passwords do not match.")
    if (msg := check_strength(body.new_password)):
        raise ApiError(422, "WEAK_PASSWORD", msg)
    user.password_hash = hash_password(body.new_password)
    sessions.revoke_all_for_user(db, user.id, except_id=p.session.id)
    audit(db, user.id, "auth.change_password", "user", user.id, ip=client_ip(request))
    db.commit()
