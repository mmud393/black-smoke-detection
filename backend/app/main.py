from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from smoke_shared.config import load_settings
from smoke_shared.enums import AppEnv
from smoke_shared.logging import configure_logging

from sqlalchemy.orm import sessionmaker
from smoke_shared.crypto import SecretBox, SecretError
from smoke_shared.db import make_engine

from .api import alerts, auth, cameras, health, incidents, monitoring, settings as settings_api
from .security.throttle import LoginThrottle
from .errors import install_error_handlers
from .middleware import RequestIdMiddleware, SecurityHeadersMiddleware


def create_app(settings=None) -> FastAPI:  # noqa: ANN001
    settings = settings or load_settings()
    configure_logging("api", settings.log_level)
    docs = settings.expose_api_docs and settings.app_env is not AppEnv.PRODUCTION
    app = FastAPI(
        title="Black Smoke Monitor API",
        version="0.1.0",
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    app.state.settings = settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app.state.engine = make_engine(settings.effective_database_url)
    app.state.session_factory = sessionmaker(app.state.engine, expire_on_commit=False)
    try:
        app.state.secret_box = SecretBox(settings.encryption_key)
    except SecretError:
        app.state.secret_box = None  # endpoints needing secrets return 503 SECRETS_NOT_CONFIGURED
    app.state.throttle = LoginThrottle(settings.login_max_failures, settings.login_lockout_seconds)
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIdMiddleware)  # outermost: wraps CORS and errors
    app.add_middleware(SecurityHeadersMiddleware)
    for r in (health, auth, cameras, incidents, alerts, settings_api, monitoring):
        app.include_router(r.router)
    return app


def get_app() -> FastAPI:
    return create_app()
