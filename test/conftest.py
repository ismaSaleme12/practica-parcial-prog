"""Andén de pruebas automatizadas del proyecto (change ``C-05``).

``conftest.py`` se importa **antes** que cualquier test, así que es el único
lugar donde se pueden fijar las variables de entorno de test antes de que
``app.core.config`` construya ``Settings``: si la app se importara primero,
quedaría apuntando a la base de desarrollo y el primer test que escribiera
ensuciaría ``taller_mecanico``.

Reglas del andén:

- Todo vive dentro de ``test/``; la estructura obligatoria de la raíz no cambia.
- La suite corre contra **PostgreSQL real** (sin sqlite, sin repositorios falsos,
  sin testcontainers): lo que la consigna pide probar es la base de verdad.
- Cada test arranca del estado conocido que deja ``seed.py`` (vacía y recarga).
- La app se ejercita con ``httpx.AsyncClient`` + ``ASGITransport`` y su lifespan
  real (``app.router.lifespan_context``), sin ``TestClient`` síncrono y sin la
  dependencia ``asgi-lifespan``.

Corrida estándar, **desde la raíz del repo**::

    python -m pytest test/ -v
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 1. Variables de test, ANTES de importar cualquier módulo de la aplicación.
# ---------------------------------------------------------------------------
NOMBRE_BASE_TEST = "taller_mecanico_test"
PASSWORD_SEED = "secreto123"  # la misma que carga seed.py para los 7 usuarios

os.environ["POSTGRES_DB"] = NOMBRE_BASE_TEST
os.environ["SECRET_KEY"] = "clave-de-prueba-solo-para-la-suite-0123456789abcdef"
os.environ["COOKIE_SECURE"] = "false"
os.environ["SQL_ECHO"] = "false"
# El costo de bcrypt no aporta nada a la suite y multiplica el tiempo del seed:
# con 4 rondas el hash tarda milisegundos en vez de ~300 ms.
os.environ["BCRYPT_ROUNDS"] = "4"

# ---------------------------------------------------------------------------
# 2. Recién ahora se puede importar la app (Settings ya apunta a la base de test).
# ---------------------------------------------------------------------------
import asyncpg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

import seed as script_seed  # noqa: E402
from app.core.config import settings  # noqa: E402
from main import app  # noqa: E402


async def _crear_base_si_falta(nombre: str) -> None:
    """Crea la base de test si el servidor todavía no la tiene.

    Se conecta a la base administrativa ``postgres`` (``CREATE DATABASE`` no se
    puede ejecutar dentro de una transacción y necesita conectarse a otra base).
    El nombre es una constante del andén, nunca entrada del usuario.
    """
    conexion = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database="postgres",
    )
    try:
        existe = await conexion.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", nombre
        )
        if not existe:
            await conexion.execute(f'CREATE DATABASE "{nombre}"')
    finally:
        await conexion.close()


@pytest.fixture(scope="session")
def base_migrada() -> Iterator[None]:
    """Crea la base de test y aplica ``alembic upgrade head`` una sola vez.

    Es síncrona a propósito: ``migrations/env.py`` ya corre Alembic con su
    propio ``asyncio.run`` y así no se mezcla con el bucle de los tests. Si la
    base ya está migrada, ``upgrade head`` no hace nada y el costo es mínimo.
    """
    asyncio.run(_crear_base_si_falta(NOMBRE_BASE_TEST))

    configuracion = Config(str(RAIZ_REPO / "alembic.ini"))
    configuracion.set_main_option("script_location", str(RAIZ_REPO / "migrations"))
    command.upgrade(configuracion, "head")

    yield


@pytest.fixture(autouse=True)
async def base_limpia(base_migrada: None) -> AsyncIterator[None]:
    """Restaura el estado base antes de cada test re-corriendo ``seed.py``.

    ``seed.main()`` vacía las trece tablas con ``TRUNCATE ... RESTART IDENTITY
    CASCADE`` y las recarga en un solo Unit of Work. No se usan transacciones
    «trucadas» ni una segunda sesión que luego se revierte: el estado del test es
    el mismo que vería la aplicación después de ``python seed.py``.
    """
    await script_seed.main()
    yield


@pytest.fixture
async def app_viva() -> AsyncIterator[FastAPI]:
    """App con su lifespan ejecutado (motor y fábrica en ``app.state``).

    Starlette expone el lifespan como ``app.router.lifespan_context``; abrirlo
    acá evita la dependencia ``asgi-lifespan`` y garantiza que ``/health/ready``
    tenga un motor real cuando corre el test.
    """
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def client(app_viva) -> AsyncIterator[AsyncClient]:
    """Cliente ASGI asincrónico contra la app real."""
    transporte = ASGITransport(app=app_viva)
    async with AsyncClient(transport=transporte, base_url="http://test") as cliente:
        yield cliente


@pytest.fixture
async def motor(app_viva):
    """Motor asincrónico de la app, para inspecciones directas con SQL crudo."""
    return app_viva.state.engine


# ---------------------------------------------------------------------------
# 3. Autenticación: helper `login` y fixtures por rol (se ejercitan desde C-07).
# ---------------------------------------------------------------------------


async def _iniciar_sesion(
    cliente: AsyncClient, email: str, password: str = PASSWORD_SEED
) -> str:
    """Hace ``POST /auth/login`` y devuelve la cookie ``access_token``.

    El token viaja **sólo** en la cookie HttpOnly (nunca en el cuerpo ni en un
    header Bearer). La cookie queda además en el tarro del cliente, así que
    cualquier petición siguiente de ese ``client`` ya va autenticada.
    """
    respuesta = await cliente.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert respuesta.status_code == 200, (
        f"login de {email} devolvió {respuesta.status_code}: {respuesta.text}"
    )

    token = respuesta.cookies.get("access_token") or cliente.cookies.get("access_token")
    assert token, "el login no dejó la cookie access_token"
    return token


@pytest.fixture
def login(client: AsyncClient) -> Callable[..., Awaitable[str]]:
    """Helper ``await login(email, password)`` atado al cliente del test."""

    async def iniciar(email: str, password: str = PASSWORD_SEED) -> str:
        return await _iniciar_sesion(client, email, password)

    return iniciar


@pytest.fixture
async def token_admin(login) -> str:
    """Sesión de ``admin@example.com`` (rol ADMIN)."""
    return await login("admin@example.com")


@pytest.fixture
async def token_recepcion(login) -> str:
    """Sesión de ``recepcion@example.com`` (rol RECEPCION)."""
    return await login("recepcion@example.com")


@pytest.fixture
async def token_mecanico(login) -> str:
    """Sesión de ``mecanico@example.com`` (rol MECANICO)."""
    return await login("mecanico@example.com")


@pytest.fixture
async def token_cliente(login) -> str:
    """Sesión de ``cliente@example.com`` (rol CLIENTE, dueña de Laura)."""
    return await login("cliente@example.com")
