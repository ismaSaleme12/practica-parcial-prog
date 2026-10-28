"""Medición de consultas y aviso post-confirmación (change C-12, US-025/US-026).

Este archivo **no agrega comportamiento**: demuestra contra la base real que las
lecturas y la asincronía que ya existen cumplen el contrato.

- **C-15 (US-025 CA-1/CA-2)**: el detalle de una orden se resuelve con un número
  **fijo** de consultas, que no crece con la cantidad de ítems (2 vs 4) ni con
  las líneas de historial. La medición usa un contador ``before_cursor_execute``
  registrado sobre ``motor.sync_engine``; no hay mocks de base ni dependencias
  nuevas.
- **Ficha y «lo propio»**: ``GET /clientes/{id}``, ``GET /mis-vehiculos`` y
  ``GET /mis-ordenes`` mantienen el mismo conteo con más filas hijas.
- **C-12 (US-026 CA-2)**: el aviso que el router agenda con ``BackgroundTasks``
  corre **después** del commit. Se demuestra abriendo una **sesión nueva** desde
  la tarea de fondo: si corriera dentro de la transacción, el aislamiento de
  PostgreSQL (READ COMMITTED) le mostraría ``EN_REPARACION``; ve ``TERMINADA``.
  El caso «un 409 no agenda la tarea» ya está cubierto por
  ``test_ordenes.py::test_terminar_rechazado_no_agenda_el_aviso`` y no se
  duplica acá.
- **US-026 CA-3**: todos los handlers son ``async def``.
- **``SQL_ECHO``**: se puede activar por entorno y su valor por defecto es
  ``false``; la suite lo mantiene apagado.

Las relaciones del esquema declaran ``lazy="raise_on_sql"``: un acceso perezoso
lanzaría en vez de emitir una consulta silenciosa, así que la igualdad de
conteos no puede esconder un N+1.

Números medidos (documentados en ``design.md`` del change):

======================  =========  ==========================================
Lectura                 Consultas  Composición
======================  =========  ==========================================
``GET /ordenes/{id}``   5          sesión + detalle (3) + roles vigentes
``GET /clientes/{id}``  4          sesión + roles + ficha + vehículos
``GET /mis-vehiculos``  3          sesión + ficha + vehículos
``GET /mis-ordenes``    5          sesión + ficha + vehículos + count + página
======================  =========  ==========================================

Los techos de la suite dejan un margen de una consulta sobre lo medido: el
criterio del caso C-15 es que el conteo **no crezca** con las filas hijas, no un
número mágico atado a las dependencias de autenticación.
"""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from typing import Iterator

from fastapi.routing import APIRoute
from sqlalchemy import event

from app.modules.ordenes.models import OrdenTrabajo

# Ids del seed (``RESTART IDENTITY``): clientes 1 (Laura, con cuenta) y 2
# (Jorge, sin cuenta); vehículos 1 AAA111 y 2 AAB222 (Laura), 3 BBB333 (Jorge);
# repuestos 1 FA-001, 2 PF-002, 3 BU-003 y 4 AC-004; orden 1 de Laura.
CLIENTE_LAURA = 1
CLIENTE_JORGE = 2
VEHICULO_LAURA = 1
VEHICULO_LAURA_2 = 2

REPUESTO_FILTRO = 1
REPUESTO_PASTILLAS = 2
REPUESTO_BUJIA = 3
REPUESTO_ACEITE = 4

# Techos medidos + 1 de margen (ver el docstring del módulo).
TECHO_DETALLE = 6
TECHO_FICHA = 5
TECHO_MIS_VEHICULOS = 4
TECHO_MIS_ORDENES = 6


# --- Contador de consultas ---------------------------------------------------


@contextmanager
def _contar_consultas(motor) -> Iterator[list[str]]:
    """Cuenta las sentencias que llegan al cursor durante el bloque.

    El evento se registra sobre ``motor.sync_engine`` y no sobre el motor
    asincrónico: ``AsyncEngine`` no es un target de eventos de SQLAlchemy, es un
    envoltorio cuyo ``sync_engine`` emite los mismos ``before_cursor_execute``.
    El listener se agrega **sólo** alrededor de la petición medida, así que el
    seed y el login no contaminan el conteo.
    """

    sentencias: list[str] = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        sentencias.append(statement)

    event.listen(motor.sync_engine, "before_cursor_execute", _listener)
    try:
        yield sentencias
    finally:
        event.remove(motor.sync_engine, "before_cursor_execute", _listener)


def _consulta_sobre(sentencias: list[str], tabla: str) -> int:
    """Cuántas sentencias del conteo tocan ``tabla`` (por nombre, en minúsculas)."""
    return sum(1 for sentencia in sentencias if tabla in sentencia.lower())


def _verificar_conteo(con_menos: list[str], con_mas: list[str], techo: int) -> None:
    """El conteo no cambia con las filas hijas y no supera el techo documentado.

    El piso de tres evita que un listener que no dispara haga pasar la igualdad
    con ``0 == 0``: toda lectura medida pasa por sesión + roles + al menos una
    consulta de dominio.
    """
    assert len(con_menos) >= 3, con_menos
    assert len(con_menos) == len(con_mas), (con_menos, con_mas)
    assert len(con_mas) <= techo, con_mas


# --- Helpers -----------------------------------------------------------------


async def _orden_con_repuestos(
    client, vehiculo_id: int, repuesto_ids: list[int]
) -> dict:
    """Alta de una orden con un ítem por repuesto (cantidad 1, no toca stock)."""
    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": vehiculo_id,
            "falla": "Medición de consultas",
            "items": [
                {"repuesto_id": repuesto_id, "cantidad": 1}
                for repuesto_id in repuesto_ids
            ],
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _vehiculo(client, cliente_id: int, patente: str) -> dict:
    """Alta de un vehículo vigente para el cliente indicado (ADMIN/RECEPCION)."""
    respuesta = await client.post(
        f"/clientes/{cliente_id}/vehiculos",
        json={
            "patente": patente,
            "marca": "Fiat",
            "modelo": "Cronos",
            "anio": 2021,
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _orden_en_vehiculo(client, vehiculo_id: int) -> dict:
    return await _orden_con_repuestos(client, vehiculo_id, [REPUESTO_FILTRO])


# --- C-15: el detalle no crece con los ítems ---------------------------------


async def test_c15_detalle_mantiene_el_conteo_con_2_y_4_items(client, login, motor):
    """Mismas consultas para una orden de 2 ítems y una de 4 (caso C-15)."""
    await login("recepcion@example.com")
    orden_2 = await _orden_con_repuestos(
        client, VEHICULO_LAURA, [REPUESTO_FILTRO, REPUESTO_PASTILLAS]
    )
    orden_4 = await _orden_con_repuestos(
        client,
        VEHICULO_LAURA,
        [REPUESTO_FILTRO, REPUESTO_PASTILLAS, REPUESTO_BUJIA, REPUESTO_ACEITE],
    )

    await login("admin@example.com")  # el login queda fuera de la medición

    with _contar_consultas(motor) as con_2:
        respuesta_2 = await client.get(f"/ordenes/{orden_2['id']}")
    with _contar_consultas(motor) as con_4:
        respuesta_4 = await client.get(f"/ordenes/{orden_4['id']}")

    assert respuesta_2.status_code == 200, respuesta_2.text
    assert respuesta_4.status_code == 200, respuesta_4.text
    assert len(respuesta_2.json()["items"]) == 2
    assert len(respuesta_4.json()["items"]) == 4

    _verificar_conteo(con_2, con_4, TECHO_DETALLE)

    # Las precargas realmente ocurrieron: los ítems y el historial se traen en
    # **una** consulta cada uno, nunca una por fila.
    assert _consulta_sobre(con_2, "item_orden") == 1
    assert _consulta_sobre(con_2, "historial_estado_orden") == 1
    assert _consulta_sobre(con_4, "item_orden") == 1


async def test_detalle_no_crece_con_las_lineas_de_historial(client, login, motor):
    """El historial se precarga con ``selectinload``: una consulta fija por orden."""
    await login("recepcion@example.com")
    orden = await _orden_en_vehiculo(client, VEHICULO_LAURA)

    await login("mecanico@example.com")

    with _contar_consultas(motor) as con_1_linea:
        respuesta_1 = await client.get(f"/ordenes/{orden['id']}")

    assert (await client.post(f"/ordenes/{orden['id']}/iniciar")).status_code == 200

    with _contar_consultas(motor) as con_2_lineas:
        respuesta_2 = await client.get(f"/ordenes/{orden['id']}")

    assert respuesta_1.status_code == 200, respuesta_1.text
    assert len(respuesta_1.json()["historial"]) == 1
    assert respuesta_2.status_code == 200, respuesta_2.text
    assert len(respuesta_2.json()["historial"]) == 2

    _verificar_conteo(con_1_linea, con_2_lineas, TECHO_DETALLE)
    assert _consulta_sobre(con_1_linea, "historial_estado_orden") == 1
    assert _consulta_sobre(con_2_lineas, "historial_estado_orden") == 1


# --- Ficha y «lo propio» ------------------------------------------------------


async def test_ficha_de_cliente_mantiene_el_conteo_con_1_y_3_vehiculos(
    client, login, motor
):
    """``GET /clientes/{id}`` precarga los vehículos en una consulta fija."""
    await login("recepcion@example.com")

    with _contar_consultas(motor) as con_1:
        ficha_1 = await client.get(f"/clientes/{CLIENTE_JORGE}")

    await _vehiculo(client, CLIENTE_JORGE, "MED001")
    await _vehiculo(client, CLIENTE_JORGE, "MED002")

    with _contar_consultas(motor) as con_3:
        ficha_3 = await client.get(f"/clientes/{CLIENTE_JORGE}")

    assert ficha_1.status_code == 200, ficha_1.text
    assert len(ficha_1.json()["vehiculos"]) == 1
    assert ficha_3.status_code == 200, ficha_3.text
    assert len(ficha_3.json()["vehiculos"]) == 3

    _verificar_conteo(con_1, con_3, TECHO_FICHA)
    assert _consulta_sobre(con_3, "vehiculo") == 1


async def test_mis_vehiculos_mantiene_el_conteo_con_2_y_3_vehiculos(
    client, login, motor
):
    """``GET /mis-vehiculos`` no agrega consultas por vehículo."""
    await login("cliente@example.com")
    with _contar_consultas(motor) as con_2:
        respuesta_2 = await client.get("/mis-vehiculos")

    await login("recepcion@example.com")
    await _vehiculo(client, CLIENTE_LAURA, "MED003")
    await login("cliente@example.com")
    with _contar_consultas(motor) as con_3:
        respuesta_3 = await client.get("/mis-vehiculos")

    assert respuesta_2.status_code == 200, respuesta_2.text
    assert len(respuesta_2.json()) == 2
    assert respuesta_3.status_code == 200, respuesta_3.text
    assert len(respuesta_3.json()) == 3

    _verificar_conteo(con_2, con_3, TECHO_MIS_VEHICULOS)


async def test_mis_ordenes_mantiene_el_conteo_con_1_y_2_ordenes(
    client, login, motor
):
    """``GET /mis-ordenes`` es count + página con vehículo precargado, siempre."""
    await login("cliente@example.com")
    with _contar_consultas(motor) as con_1:
        respuesta_1 = await client.get("/mis-ordenes")

    await login("recepcion@example.com")
    await _orden_en_vehiculo(client, VEHICULO_LAURA_2)
    await login("cliente@example.com")
    with _contar_consultas(motor) as con_2:
        respuesta_2 = await client.get("/mis-ordenes")

    assert respuesta_1.status_code == 200, respuesta_1.text
    assert respuesta_1.json()["total"] == 1
    assert respuesta_2.status_code == 200, respuesta_2.text
    assert respuesta_2.json()["total"] == 2

    _verificar_conteo(con_1, con_2, TECHO_MIS_ORDENES)
    assert _consulta_sobre(con_2, "orden_trabajo") == 2  # count + página


# --- C-12: el aviso corre después del commit ---------------------------------


async def test_c12_el_aviso_corre_despues_del_commit(
    client, login, app_viva, monkeypatch
):
    """La tarea de fondo ve el estado confirmado, no el de la transacción.

    Se reemplaza ``service.avisar_cliente`` por una corrutina que abre una
    **sesión nueva** desde ``app.state.session_maker`` y registra el estado que
    lee. Una sesión distinta sólo ve los cambios de otra transacción cuando esa
    transacción confirmó (READ COMMITTED): si el router agendara el aviso dentro
    del UoW, la tarea vería ``EN_REPARACION``. Ve ``TERMINADA``.
    """
    await login("recepcion@example.com")
    orden = await _orden_en_vehiculo(client, VEHICULO_LAURA)

    await login("mecanico@example.com")
    assert (await client.post(f"/ordenes/{orden['id']}/iniciar")).status_code == 200

    fabrica = app_viva.state.session_maker

    # Control: en este punto la orden está EN_REPARACION **confirmada**.
    async with fabrica() as sesion:
        antes = await sesion.get(OrdenTrabajo, orden["id"])
        assert antes is not None
        assert antes.estado == "EN_REPARACION"

    visto: list[str | None] = []

    async def _aviso_de_prueba(orden_id: int) -> None:
        async with fabrica() as sesion:
            fila = await sesion.get(OrdenTrabajo, orden_id)
            visto.append(fila.estado if fila is not None else None)

    monkeypatch.setattr(
        "app.modules.ordenes.service.avisar_cliente", _aviso_de_prueba
    )

    respuesta = await client.post(f"/ordenes/{orden['id']}/terminar")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "TERMINADA"
    assert visto == ["TERMINADA"]


# --- US-026 CA-3: handlers asincrónicos --------------------------------------


async def test_todos_los_handlers_son_coroutines(app_viva):
    """Ningún endpoint se declara con ``def`` (no bloquea el bucle de eventos)."""
    bloqueantes = [
        f"{route.path} ({route.endpoint.__module__})"
        for route in app_viva.routes
        if isinstance(route, APIRoute)
        and not inspect.iscoroutinefunction(route.endpoint)
    ]
    assert bloqueantes == []


# --- SQL_ECHO -----------------------------------------------------------------


async def test_sql_echo_se_habilita_por_entorno_y_esta_apagado_por_defecto(motor):
    """``SQL_ECHO`` es un booleano de entorno con default ``false``.

    ``pydantic-settings`` lee ``SQL_ECHO`` del entorno o del ``.env`` con el
    mismo nombre que el campo; el motor del lifespan lo pasa a
    ``create_async_engine(echo=...)``. La suite lo fija en ``false`` para no
    inundar la salida, pero activarlo es sólo ``SQL_ECHO=true``.
    """
    from app.core.config import Settings, settings

    assert Settings.model_fields["SQL_ECHO"].default is False
    assert Settings(SQL_ECHO="true").SQL_ECHO is True
    assert settings.SQL_ECHO is False
    assert motor.sync_engine.echo is False
