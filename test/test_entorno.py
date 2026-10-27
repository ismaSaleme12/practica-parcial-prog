"""El andén de pruebas mira a la raíz del repo y a la base de test.

Tres guardas baratas que evitan los errores más caros de la suite:

1. ``import app`` / ``import main`` funcionan aunque ``pytest.ini`` esté dentro
   de ``test/`` (el rootdir cae en esta carpeta; ver design.md del change).
2. ``Settings`` apunta a ``taller_mecanico_test``, no a la base de desarrollo:
   un test que escriba no debe poder tocar ``taller_mecanico``.
3. El esquema del test está migrado (trece tablas de dominio).
"""

from sqlalchemy import text

import main
from app.core.config import settings

TABLAS_DE_DOMINIO = 13


def test_la_app_se_importa_desde_la_raiz() -> None:
    """`import main` y `import app` resuelven contra la raíz del repo."""
    import app  # noqa: F401  (el paquete de la aplicación)

    assert main.app.title == "API Taller Mecánico"


def test_las_variables_de_test_ganan_sobre_el_entorno_local() -> None:
    """Las variables del andén se fijan antes de importar la app."""
    # El nombre exacto puede variar (``TEST_POSTGRES_DB`` permite correr dos
    # suites en paralelo), pero nunca puede ser la base de desarrollo.
    assert settings.POSTGRES_DB != "taller_mecanico"
    assert settings.POSTGRES_DB.startswith("taller_mecanico_")
    assert settings.COOKIE_SECURE is False
    assert settings.SQL_ECHO is False


async def test_el_esquema_de_test_esta_migrado(motor) -> None:
    """La fixture de sesión aplicó `alembic upgrade head` en la base de test."""
    async with motor.connect() as conexion:
        total = (
            await conexion.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
                )
            )
        ).scalar_one()

    assert total == TABLAS_DE_DOMINIO
