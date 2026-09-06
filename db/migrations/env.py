"""
Alembic environment configuration.

Reads the sync DATABASE_URL from pydantic-settings so the connection string
is never hardcoded.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# ── Import all models so metadata knows about them ───────────
from db.models import Base  # noqa: F401

# Alembic Config object
config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Override sqlalchemy.url from our Settings ────────────────
try:
    from config import get_settings
    settings = get_settings()
    config.set_main_option("sqlalchemy.url", settings.sync_database_url)
except Exception:
    pass  # Fall back to alembic.ini value

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL only)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (execute against the database)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Enable TimescaleDB extension before running migrations
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
