"""Smoke tests del único endpoint de pie en este punto (caso C-01).

Se ejercitan con ``httpx.AsyncClient`` + ``ASGITransport`` y el lifespan real de
la app: los handlers son ``async`` y se prueban como tales, sin ``TestClient``
síncrono.
"""

from httpx import ASGITransport, AsyncClient

from app.core.database import get_session


async def test_live_responde_200_sin_tocar_la_base(client) -> None:
    respuesta = await client.get("/health/live")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "alive"}


async def test_ready_responde_200_contra_postgres_real(client) -> None:
    respuesta = await client.get("/health/ready")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ready", "database": "connected"}


async def test_ready_responde_503_si_la_base_no_contesta(app_viva) -> None:
    """Único doble del andén: simula una caída de infraestructura, no de datos."""

    class SesionCaida:
        async def execute(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("sin conexión a la base")

    async def sesion_caida():
        yield SesionCaida()

    app_viva.dependency_overrides[get_session] = sesion_caida
    try:
        transporte = ASGITransport(app=app_viva)
        async with AsyncClient(
            transport=transporte, base_url="http://test"
        ) as cliente:
            respuesta = await cliente.get("/health/ready")
    finally:
        app_viva.dependency_overrides.clear()

    assert respuesta.status_code == 503
