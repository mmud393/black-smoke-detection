from alembic import context
from smoke_shared.config import load_settings
from smoke_shared.db import Base, make_engine

target_metadata = Base.metadata


def _url() -> str:
    return context.config.get_main_option("sqlalchemy.url") or load_settings().effective_database_url


def run_migrations_online() -> None:
    engine = make_engine(_url())
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
