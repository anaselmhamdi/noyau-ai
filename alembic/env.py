import asyncio
import ssl
from logging.config import fileConfig
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.config import get_settings
from app.models import Base

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the database URL from environment
settings = get_settings()


def _fix_neon_url(url: str) -> tuple[str, dict]:
    """Fix Neon connection URL for asyncpg compatibility.

    - For Neon (*.neon.tech): Use SSL with default context
    - For local dev (localhost/127.0.0.1): No SSL
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    # Remove unsupported asyncpg params
    for param in ["sslmode", "channel_binding", "options"]:
        params.pop(param, None)

    new_query = urlencode(params, doseq=True)
    clean_url = urlunparse(parsed._replace(query=new_query))

    # Only use SSL for Neon (production), not for local dev
    hostname = parsed.hostname or ""
    is_local = hostname in ("localhost", "127.0.0.1", "db")

    if is_local:
        return clean_url, {}
    else:
        ssl_context = ssl.create_default_context()
        return clean_url, {"ssl": ssl_context}


db_url, connect_args = _fix_neon_url(settings.database_url)
config.set_main_option("sqlalchemy.url", db_url)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(
        db_url,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
