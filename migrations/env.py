"""Configuración de Alembic con la plantilla asincrónica.

La base se versiona **sólo** desde acá: la aplicación nunca llama a
``create_all``.

Puntos que no se tocan sin leer:

- La URL sale de ``app.core.config.settings`` (entorno o ``.env``); ``alembic.ini``
  no guarda credenciales. ``configparser`` interpola ``%``, así que se escapa.
- Se importa ``app/models.py`` (el registro central): sin él, el metadata no
  conoce las relaciones entre módulos y la configuración de mappers falla con
  «expression 'Cliente' failed to locate a name».
- ``compare_type`` y ``compare_server_default`` hacen que las próximas
  migraciones detecten cambios de tipo y de default, no sólo de columnas.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

import app.models  # noqa: F401  registra las trece tablas
from app.core.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url", settings.ASYNC_DATABASE_URL.replace("%", "%%")
)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (``alembic upgrade head --sql``)."""
    context.configure(
        url=settings.ASYNC_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
