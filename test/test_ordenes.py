"""Réplica automatizada de ``test/ordenes.http`` (change C-11).

Cubre la Épica 8 (US-023, US-024, US-025 y US-026):

- **C-09**: catálogo de estados vacío → ``POST /ordenes`` responde 409 y no
  crea nada (RN-19).
- **C-10**: un repuesto inexistente o dado de baja → 409 y la orden **no queda
  creada**; un vehículo dado de baja, lo mismo (RN-16).
- **C-11**: la orden 2 pide 4 bujías cuando hay 2. ``terminar`` responde 409 y
  el estado, el stock, los movimientos y el historial quedan exactamente como
  estaban (rollback total, RN-13).
- **SU-04**: la identidad se evalúa antes que el estado: un mecánico no
  asignado recibe 403, aunque la orden tampoco admita la transición.
- **C-13**: cancelar una orden TERMINADA responde 409; una ajena, 403; la
  propia PENDIENTE, 200.
- **C-17**: un estado no declarado en ``GET /ordenes`` responde 422 y
  ``GET /estados-orden`` devuelve el catálogo por posición.
- **C-06**: el cliente ve su orden (200) y no la ajena (403).
- **C-12 (aviso)**: ``terminar`` agenda el aviso simulado con
  ``BackgroundTasks`` después de confirmar; un ``terminar`` rechazado no lo
  agenda.

Usa los fixtures de ``test/conftest.py`` (``client``, ``login``, ``token_*``,
``motor``). El seed se re-ejecuta antes de cada test, así que los identificadores
son los del seed (``RESTART IDENTITY``):

- usuarios: admin 1, admin2 2, recepción 3, mecánico 4, mecánico2 5,
  cliente/Laura 6, nuevo 7;
- vehículos: 1 AAA111 (Laura), 2 AAB222 (Laura), 3 BBB333 (Jorge);
- repuestos: 1 FA-001 (8500.00, stock 10), 2 PF-002 (12000.00, stock 4),
  3 BU-003 (1500.00, stock 2), 4 AC-004 (2500.00, stock 20);
- órdenes: 1 PENDIENTE de AAA111 sin ítems; 2 EN_REPARACION de BBB333,
  mecánico 4, con 4 × BU-003.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

MENSAJE_VALIDACION = "La petición no cumple el contrato."
MENSAJE_SIN_PERMISO = "No tenés permiso para realizar esta operación."
MENSAJE_SIN_SESION = "No hay una sesión válida."

# Identificadores del seed (RESTART IDENTITY en seed.py).
ADMIN_ID = 1
RECEPCION_ID = 3
MECANICO_ID = 4
MECANICO2_ID = 5
CLIENTE_ID = 6

VEHICULO_LAURA = 1
VEHICULO_LAURA_2 = 2
VEHICULO_JORGE = 3

REPUESTO_FILTRO = 1
REPUESTO_PASTILLAS = 2
REPUESTO_BUJIA = 3
REPUESTO_ACEITE = 4

ORDEN_LAURA = 1
ORDEN_JORGE = 2


# --- Helpers ----------------------------------------------------------------


async def _filas(motor, sql: str, **parametros: Any) -> list[tuple]:
    """Ejecuta una consulta contra la base real de test y devuelve sus filas."""
    async with motor.connect() as conexion:
        resultado = await conexion.execute(text(sql), parametros)
        return list(resultado.all())


async def _escalar(motor, sql: str, **parametros: Any) -> Any:
    """Primera columna de la primera fila (o ``None`` si no hay filas)."""
    filas = await _filas(motor, sql, **parametros)
    return filas[0][0] if filas else None


def _campos(cuerpo: dict) -> str:
    """Concatena los campos del error de validación para poder buscarlos."""
    return " ".join(error.get("campo", "") for error in cuerpo.get("errores", []))


async def _usuario_id(client) -> int:
    """Id del usuario de la sesión actual (``GET /auth/yo``)."""
    respuesta = await client.get("/auth/yo")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["usuario"]["id"]


async def _crear_orden(
    client,
    *,
    vehiculo_id: int = VEHICULO_LAURA,
    repuesto_id: int = REPUESTO_FILTRO,
    cantidad: int = 1,
    falla: str = "Falla de prueba",
) -> dict:
    """Alta de una orden válida con un ítem (la sesión ya debe estar iniciada)."""
    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": vehiculo_id,
            "falla": falla,
            "items": [{"repuesto_id": repuesto_id, "cantidad": cantidad}],
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


async def _orden_terminada(client, login, *, vehiculo_id: int = VEHICULO_LAURA) -> dict:
    """Alta → iniciar → terminar con stock suficiente y devuelve la orden creada."""
    await login("recepcion@example.com")
    orden = await _crear_orden(client, vehiculo_id=vehiculo_id)

    await login("mecanico@example.com")
    iniciar = await client.post(f"/ordenes/{orden['id']}/iniciar")
    assert iniciar.status_code == 200, iniciar.text
    terminar = await client.post(f"/ordenes/{orden['id']}/terminar")
    assert terminar.status_code == 200, terminar.text
    return orden


# --- C-11: rollback total por stock insuficiente ----------------------------


async def test_c11_terminar_con_stock_insuficiente_no_escribe_nada(client, login, motor):
    """La orden 2 pide 4 bujías y hay 2: 409 y todo queda igual (RN-13)."""
    await login("mecanico@example.com")

    stock_antes = await _escalar(
        motor, "SELECT stock FROM repuesto WHERE codigo = 'BU-003'"
    )
    movimientos_antes = await _escalar(motor, "SELECT count(*) FROM movimiento_stock")
    movimientos_orden_antes = await _escalar(
        motor, "SELECT count(*) FROM movimiento_stock WHERE orden_id = 2"
    )
    historial_antes = await _escalar(
        motor, "SELECT count(*) FROM historial_estado_orden WHERE orden_id = 2"
    )
    estado_antes = await _escalar(
        motor, "SELECT estado FROM orden_trabajo WHERE id = 2"
    )

    respuesta = await client.post("/ordenes/2/terminar")

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]

    assert (
        await _escalar(motor, "SELECT stock FROM repuesto WHERE codigo = 'BU-003'")
        == stock_antes
        == 2
    )
    assert (
        await _escalar(motor, "SELECT count(*) FROM movimiento_stock")
        == movimientos_antes
    )
    assert (
        await _escalar(
            motor, "SELECT count(*) FROM movimiento_stock WHERE orden_id = 2"
        )
        == movimientos_orden_antes
        == 0
    )
    assert (
        await _escalar(
            motor, "SELECT count(*) FROM historial_estado_orden WHERE orden_id = 2"
        )
        == historial_antes
        == 2
    )
    assert (
        await _escalar(motor, "SELECT estado FROM orden_trabajo WHERE id = 2")
        == estado_antes
        == "EN_REPARACION"
    )


# --- SU-04: 403 (identidad) antes que 409 (estado) --------------------------


async def test_su04_mecanico_no_asignado_recibe_403_no_409(client, login):
    """El mecánico 5 no está asignado a la orden 2 (mecánico 4): 403."""
    await login("mecanico2@example.com")

    respuesta = await client.post("/ordenes/2/terminar")

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == MENSAJE_SIN_PERMISO


async def test_su04_terminar_terminada_por_mecanico_ajeno_es_403(client, login):
    """Con la orden ya TERMINADA, un mecánico ajeno sigue recibiendo 403 (no 409)."""
    orden = await _orden_terminada(client, login, vehiculo_id=VEHICULO_JORGE)

    await login("mecanico2@example.com")
    respuesta = await client.post(f"/ordenes/{orden['id']}/terminar")

    assert respuesta.status_code == 403


async def test_terminar_orden_inexistente_responde_404(client, login):
    await login("mecanico@example.com")

    respuesta = await client.post("/ordenes/999999/terminar")

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "No existe la orden con id 999999."


# --- C-09: catálogo vacío ---------------------------------------------------


async def test_c09_catalogo_vacio_al_crear_responde_409(client, login, motor):
    await login("recepcion@example.com")

    async with motor.begin() as conexion:
        await conexion.execute(text("TRUNCATE estado_orden CASCADE"))

    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Sin catálogo",
            "items": [{"repuesto_id": REPUESTO_FILTRO, "cantidad": 1}],
        },
    )

    assert respuesta.status_code == 409
    assert "catálogo" in respuesta.json()["detail"].lower()


# --- C-10 y RN-16: nada a medias -------------------------------------------


async def test_c10_repuesto_inexistente_responde_409_y_no_crea_la_orden(
    client, login, motor
):
    await login("recepcion@example.com")
    antes = await _escalar(motor, "SELECT count(*) FROM orden_trabajo")

    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Repuesto fantasma",
            "items": [{"repuesto_id": 999999, "cantidad": 1}],
        },
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"]
    assert await _escalar(motor, "SELECT count(*) FROM orden_trabajo") == antes


async def test_repuesto_dado_de_baja_responde_409_y_no_crea_la_orden(
    client, login, motor
):
    await login("admin@example.com")
    assert (await client.delete(f"/repuestos/{REPUESTO_FILTRO}")).status_code == 204

    await login("recepcion@example.com")
    antes = await _escalar(motor, "SELECT count(*) FROM orden_trabajo")

    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Repuesto dado de baja",
            "items": [{"repuesto_id": REPUESTO_FILTRO, "cantidad": 1}],
        },
    )

    assert respuesta.status_code == 409
    assert await _escalar(motor, "SELECT count(*) FROM orden_trabajo") == antes


async def test_vehiculo_dado_de_baja_responde_409_y_no_crea_la_orden(
    client, login, motor
):
    await login("recepcion@example.com")
    # El vehículo 2 (AAB222) es de Laura y no tiene órdenes abiertas.
    assert (await client.delete(f"/vehiculos/{VEHICULO_LAURA_2}")).status_code == 204
    antes = await _escalar(motor, "SELECT count(*) FROM orden_trabajo")

    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": VEHICULO_LAURA_2,
            "falla": "Vehículo dado de baja",
            "items": [{"repuesto_id": REPUESTO_FILTRO, "cantidad": 1}],
        },
    )

    assert respuesta.status_code == 409
    assert await _escalar(motor, "SELECT count(*) FROM orden_trabajo") == antes


async def test_vehiculo_inexistente_responde_409(client, login, motor):
    await login("recepcion@example.com")
    antes = await _escalar(motor, "SELECT count(*) FROM orden_trabajo")

    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": 999999,
            "falla": "Vehículo inexistente",
            "items": [{"repuesto_id": REPUESTO_FILTRO, "cantidad": 1}],
        },
    )

    assert respuesta.status_code == 409
    assert await _escalar(motor, "SELECT count(*) FROM orden_trabajo") == antes


# --- Alta válida (US-023, RN-10) -------------------------------------------


async def test_alta_valida_calcula_total_y_copia_precios_en_el_servidor(
    client, login, motor
):
    await login("recepcion@example.com")
    usuario_id = await _usuario_id(client)
    antes = await _escalar(motor, "SELECT count(*) FROM orden_trabajo")

    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Cambio de pastillas y aceite",
            "items": [
                {"repuesto_id": REPUESTO_PASTILLAS, "cantidad": 1},
                {"repuesto_id": REPUESTO_ACEITE, "cantidad": 3},
            ],
        },
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()

    assert cuerpo["estado"] == "PENDIENTE"
    assert cuerpo["mecanico_id"] is None
    assert cuerpo["patente"] == "AAA111"
    assert cuerpo["cliente"] == "Laura"
    assert cuerpo["falla"] == "Cambio de pastillas y aceite"
    assert cuerpo["total"] == "19500.00"  # 12000.00 + 3 × 2500.00
    assert isinstance(cuerpo["total"], str)

    items = cuerpo["items"]
    assert [item["repuesto_id"] for item in items] == [
        REPUESTO_PASTILLAS,
        REPUESTO_ACEITE,
    ]
    assert items[0]["precio_unitario"] == "12000.00"
    assert items[0]["subtotal"] == "12000.00"
    assert items[1]["precio_unitario"] == "2500.00"
    assert items[1]["subtotal"] == "7500.00"
    assert items[0]["codigo"] == "PF-002"
    assert items[1]["descripcion"] == "Aceite por litro"

    historial = cuerpo["historial"]
    assert len(historial) == 1
    assert historial[0]["desde_estado"] is None
    assert historial[0]["hasta_estado"] == "PENDIENTE"
    assert historial[0]["usuario_id"] == usuario_id

    assert await _escalar(motor, "SELECT count(*) FROM orden_trabajo") == antes + 1
    assert await _escalar(
        motor, "SELECT total FROM orden_trabajo WHERE id = :id", id=cuerpo["id"]
    ) == Decimal("19500.00")


async def test_alta_con_un_solo_item_calcula_bien(client, login):
    await login("recepcion@example.com")

    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Bujías",
            "items": [{"repuesto_id": REPUESTO_BUJIA, "cantidad": 2}],
        },
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["total"] == "3000.00"


@pytest.mark.parametrize(
    "cuerpo",
    [
        {
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Sin ítems",
            "items": [],
        },
        {
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Repuesto repetido",
            "items": [
                {"repuesto_id": REPUESTO_FILTRO, "cantidad": 1},
                {"repuesto_id": REPUESTO_FILTRO, "cantidad": 2},
            ],
        },
        {
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Cantidad cero",
            "items": [{"repuesto_id": REPUESTO_FILTRO, "cantidad": 0}],
        },
        {
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Cantidad negativa",
            "items": [{"repuesto_id": REPUESTO_FILTRO, "cantidad": -1}],
        },
        {
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Total inyectado",
            "total": "1.00",
            "items": [{"repuesto_id": REPUESTO_FILTRO, "cantidad": 1}],
        },
        {
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Estado inyectado",
            "estado": "TERMINADA",
            "items": [{"repuesto_id": REPUESTO_FILTRO, "cantidad": 1}],
        },
        {
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Mecánico inyectado",
            "mecanico_id": MECANICO_ID,
            "items": [{"repuesto_id": REPUESTO_FILTRO, "cantidad": 1}],
        },
        {
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Precio inyectado en el ítem",
            "items": [
                {
                    "repuesto_id": REPUESTO_FILTRO,
                    "cantidad": 1,
                    "precio_unitario": "1.00",
                }
            ],
        },
    ],
)
async def test_alta_invalida_responde_422(client, login, cuerpo):
    await login("recepcion@example.com")

    respuesta = await client.post("/ordenes", json=cuerpo)

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MENSAJE_VALIDACION


async def test_alta_con_repuestos_repetidos_nombra_el_campo_items(client, login):
    await login("recepcion@example.com")

    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Repetido",
            "items": [
                {"repuesto_id": REPUESTO_FILTRO, "cantidad": 1},
                {"repuesto_id": REPUESTO_FILTRO, "cantidad": 1},
            ],
        },
    )

    assert respuesta.status_code == 422
    assert "items" in _campos(respuesta.json())


async def test_alta_con_campo_no_declarado_nombra_el_campo(client, login):
    await login("recepcion@example.com")

    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Total inyectado",
            "total": "1.00",
            "items": [{"repuesto_id": REPUESTO_FILTRO, "cantidad": 1}],
        },
    )

    assert respuesta.status_code == 422
    assert "total" in _campos(respuesta.json())


# --- Iniciar (US-024 CA-1) --------------------------------------------------


async def test_iniciar_pendiente_asigna_mecanico_y_deja_historial(client, login):
    await login("mecanico@example.com")
    usuario_id = await _usuario_id(client)

    respuesta = await client.post(f"/ordenes/{ORDEN_LAURA}/iniciar")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "EN_REPARACION"
    assert cuerpo["mecanico_id"] == usuario_id == MECANICO_ID

    detalle = await client.get(f"/ordenes/{ORDEN_LAURA}")
    assert detalle.status_code == 200
    historial = detalle.json()["historial"]
    assert len(historial) == 2
    ultima = historial[-1]
    assert ultima["desde_estado"] == "PENDIENTE"
    assert ultima["hasta_estado"] == "EN_REPARACION"
    assert ultima["usuario_id"] == usuario_id


async def test_iniciar_una_orden_ya_en_reparacion_responde_409(client, login):
    await login("mecanico@example.com")

    respuesta = await client.post(f"/ordenes/{ORDEN_JORGE}/iniciar")

    assert respuesta.status_code == 409


async def test_iniciar_orden_inexistente_responde_404(client, login):
    await login("mecanico@example.com")

    respuesta = await client.post("/ordenes/999999/iniciar")

    assert respuesta.status_code == 404


async def test_iniciar_con_recepcion_responde_403(client, login):
    await login("recepcion@example.com")

    respuesta = await client.post(f"/ordenes/{ORDEN_LAURA}/iniciar")

    assert respuesta.status_code == 403


# --- Terminar con stock suficiente (RN-13, RN-14) --------------------------


async def test_terminar_descuenta_stock_y_deja_un_movimiento_por_item(
    client, login, motor
):
    await login("recepcion@example.com")
    orden = await _crear_orden(
        client, vehiculo_id=VEHICULO_LAURA, repuesto_id=REPUESTO_FILTRO, cantidad=2
    )

    await login("mecanico@example.com")
    mecanico_id = await _usuario_id(client)
    assert (await client.post(f"/ordenes/{orden['id']}/iniciar")).status_code == 200

    respuesta = await client.post(f"/ordenes/{orden['id']}/terminar")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "TERMINADA"
    assert (
        await _escalar(
            motor, "SELECT stock FROM repuesto WHERE id = :id", id=REPUESTO_FILTRO
        )
        == 8
    )

    # El historial nuevo queda en el detalle.
    detalle = await client.get(f"/ordenes/{orden['id']}")
    assert detalle.status_code == 200
    ultima = detalle.json()["historial"][-1]
    assert ultima["desde_estado"] == "EN_REPARACION"
    assert ultima["hasta_estado"] == "TERMINADA"

    # El ADMIN ve el movimiento negativo en el historial del repuesto.
    await login("admin@example.com")
    movimientos = await client.get(
        f"/repuestos/{REPUESTO_FILTRO}/movimientos", params={"size": 100}
    )
    assert movimientos.status_code == 200
    cuerpo = movimientos.json()
    assert cuerpo["total"] == 2  # el «Stock inicial» del seed + la salida
    salida = cuerpo["items"][-1]
    assert salida["cantidad"] == -2
    assert salida["orden_id"] == orden["id"]
    assert salida["usuario_id"] == mecanico_id
    assert salida["motivo"].startswith("Salida por orden")


async def test_terminar_con_admin_funciona_aunque_no_sea_el_asignado(client, login):
    await login("recepcion@example.com")
    orden = await _crear_orden(client)

    await login("mecanico@example.com")
    assert (await client.post(f"/ordenes/{orden['id']}/iniciar")).status_code == 200

    await login("admin@example.com")
    respuesta = await client.post(f"/ordenes/{orden['id']}/terminar")

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "TERMINADA"


async def test_terminar_una_orden_pendiente_responde_409(client, login):
    await login("admin@example.com")

    respuesta = await client.post(f"/ordenes/{ORDEN_LAURA}/terminar")

    assert respuesta.status_code == 409


# --- Cancelar (RN-12, DD-06) ------------------------------------------------


async def test_cancelar_propia_pendiente_como_dueno_responde_200(client, login):
    await login("cliente@example.com")
    usuario_id = await _usuario_id(client)

    respuesta = await client.post(f"/ordenes/{ORDEN_LAURA}/cancelar")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "CANCELADA"

    detalle = await client.get(f"/ordenes/{ORDEN_LAURA}")
    ultima = detalle.json()["historial"][-1]
    assert ultima["desde_estado"] == "PENDIENTE"
    assert ultima["hasta_estado"] == "CANCELADA"
    assert ultima["usuario_id"] == usuario_id == CLIENTE_ID


async def test_cancelar_una_orden_ya_cancelada_responde_409(client, login):
    await login("cliente@example.com")
    assert (await client.post(f"/ordenes/{ORDEN_LAURA}/cancelar")).status_code == 200

    respuesta = await client.post(f"/ordenes/{ORDEN_LAURA}/cancelar")

    assert respuesta.status_code == 409


async def test_cancelar_como_mecanico_ajeno_responde_403(client, login):
    await login("mecanico@example.com")

    respuesta = await client.post(f"/ordenes/{ORDEN_LAURA}/cancelar")

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == MENSAJE_SIN_PERMISO


async def test_cancelar_orden_ajena_como_cliente_responde_403(client, login):
    await login("cliente@example.com")

    respuesta = await client.post(f"/ordenes/{ORDEN_JORGE}/cancelar")

    assert respuesta.status_code == 403


async def test_cancelar_terminada_como_recepcion_responde_409(client, login):
    """Caso C-13: una orden TERMINADA no se cancela."""
    orden = await _orden_terminada(client, login)

    await login("recepcion@example.com")
    respuesta = await client.post(f"/ordenes/{orden['id']}/cancelar")

    assert respuesta.status_code == 409


async def test_cancelar_terminada_ajena_como_cliente_responde_403(client, login):
    """La identidad se evalúa antes que el estado: 403, no 409."""
    orden = await _orden_terminada(client, login, vehiculo_id=VEHICULO_JORGE)

    await login("cliente@example.com")
    respuesta = await client.post(f"/ordenes/{orden['id']}/cancelar")

    assert respuesta.status_code == 403


async def test_cancelar_orden_inexistente_responde_404(client, login):
    await login("admin@example.com")

    respuesta = await client.post("/ordenes/999999/cancelar")

    assert respuesta.status_code == 404


# --- GET /ordenes (C-17) ----------------------------------------------------


async def test_listado_de_ordenes_paginado_y_ordenado(client, login):
    await login("admin@example.com")

    respuesta = await client.get("/ordenes")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"items", "total", "page", "size", "pages"}
    assert cuerpo["total"] == 2
    assert [item["id"] for item in cuerpo["items"]] == [ORDEN_JORGE, ORDEN_LAURA]
    primero = cuerpo["items"][0]
    assert set(primero) >= {
        "id",
        "vehiculo_id",
        "patente",
        "estado",
        "falla",
        "creada_en",
        "total",
        "mecanico_id",
    }
    assert primero["patente"] == "BBB333"
    assert primero["total"] == "6000.00"


async def test_listado_filtrado_por_estado(client, login):
    await login("admin@example.com")

    pendientes = await client.get("/ordenes", params={"estado": "PENDIENTE"})
    en_reparacion = await client.get("/ordenes", params={"estado": "EN_REPARACION"})

    assert pendientes.status_code == 200
    assert [item["id"] for item in pendientes.json()["items"]] == [ORDEN_LAURA]
    assert en_reparacion.status_code == 200
    assert [item["id"] for item in en_reparacion.json()["items"]] == [ORDEN_JORGE]


async def test_c17_estado_no_declarado_responde_422(client, login):
    await login("admin@example.com")

    respuesta = await client.get("/ordenes", params={"estado": "INVENTADO"})

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MENSAJE_VALIDACION


async def test_listado_pagina_fuera_de_rango_responde_422(client, login):
    await login("admin@example.com")

    respuesta = await client.get("/ordenes", params={"page": 9, "size": 1})

    assert respuesta.status_code == 422


async def test_listado_con_cliente_responde_403(client, login):
    await login("cliente@example.com")

    respuesta = await client.get("/ordenes")

    assert respuesta.status_code == 403


# --- GET /ordenes/{id} (C-06) ----------------------------------------------


async def test_detalle_completo_con_vehiculo_cliente_items_e_historial(client, login):
    await login("admin@example.com")

    respuesta = await client.get(f"/ordenes/{ORDEN_JORGE}")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["id"] == ORDEN_JORGE
    assert cuerpo["patente"] == "BBB333"
    assert cuerpo["cliente"] == "Jorge"
    assert cuerpo["estado"] == "EN_REPARACION"
    assert cuerpo["mecanico_id"] == MECANICO_ID
    assert cuerpo["total"] == "6000.00"
    assert cuerpo["items"] == [
        {
            "repuesto_id": REPUESTO_BUJIA,
            "codigo": "BU-003",
            "descripcion": "Bujía",
            "cantidad": 4,
            "precio_unitario": "1500.00",
            "subtotal": "6000.00",
        }
    ]
    assert len(cuerpo["historial"]) == 2


async def test_c06_cliente_ve_su_orden_y_no_la_ajena(client, login):
    await login("cliente@example.com")

    propia = await client.get(f"/ordenes/{ORDEN_LAURA}")
    ajena = await client.get(f"/ordenes/{ORDEN_JORGE}")

    assert propia.status_code == 200
    assert propia.json()["patente"] == "AAA111"
    assert ajena.status_code == 403
    assert ajena.json()["detail"] == MENSAJE_SIN_PERMISO


@pytest.mark.parametrize(
    "email",
    ["admin@example.com", "recepcion@example.com", "mecanico@example.com"],
)
async def test_personal_ve_cualquier_orden(client, login, email):
    await login(email)

    respuesta = await client.get(f"/ordenes/{ORDEN_JORGE}")

    assert respuesta.status_code == 200


async def test_detalle_de_orden_inexistente_responde_404(client, login):
    await login("admin@example.com")

    respuesta = await client.get("/ordenes/999999")

    assert respuesta.status_code == 404


# --- Catálogo de estados (C-17) --------------------------------------------


async def test_estados_orden_por_posicion_y_finales(client, login):
    await login("cliente@example.com")

    respuesta = await client.get("/estados-orden")

    assert respuesta.status_code == 200
    catalogo = respuesta.json()
    assert [estado["codigo"] for estado in catalogo] == [
        "PENDIENTE",
        "EN_REPARACION",
        "TERMINADA",
        "CANCELADA",
    ]
    assert [estado["posicion"] for estado in catalogo] == [1, 2, 3, 4]
    assert [estado["es_final"] for estado in catalogo] == [
        False,
        False,
        True,
        True,
    ]


async def test_estados_orden_sin_sesion_responde_401(client):
    respuesta = await client.get("/estados-orden")

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == MENSAJE_SIN_SESION


# --- GET /mis-ordenes (RN-17) ----------------------------------------------


async def test_mis_ordenes_solo_las_de_sus_vehiculos(client, login):
    await login("cliente@example.com")

    respuesta = await client.get("/mis-ordenes")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"items", "total", "page", "size", "pages"}
    assert cuerpo["total"] == 1
    assert [item["id"] for item in cuerpo["items"]] == [ORDEN_LAURA]
    assert cuerpo["items"][0]["patente"] == "AAA111"


async def test_mis_ordenes_sin_ficha_de_cliente_devuelve_lista_vacia(client, login):
    await login("admin@example.com")

    respuesta = await client.get("/mis-ordenes")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["items"] == []
    assert cuerpo["total"] == 0
    assert cuerpo["pages"] == 0


async def test_mis_ordenes_sin_sesion_responde_401(client):
    respuesta = await client.get("/mis-ordenes")

    assert respuesta.status_code == 401


# --- Permisos: 401 sin sesión y 403 donde la matriz lo exige ---------------


@pytest.mark.parametrize(
    "metodo,ruta,cuerpo",
    [
        ("post", "/ordenes", {"vehiculo_id": 1, "falla": "x", "items": [{"repuesto_id": 1, "cantidad": 1}]}),
        ("get", "/ordenes", None),
        ("get", "/ordenes/1", None),
        ("post", "/ordenes/1/iniciar", None),
        ("post", "/ordenes/1/terminar", None),
        ("post", "/ordenes/1/cancelar", None),
        ("get", "/estados-orden", None),
        ("get", "/mis-ordenes", None),
    ],
)
async def test_sin_sesion_responde_401(client, metodo, ruta, cuerpo):
    funcion = getattr(client, metodo)
    respuesta = await funcion(ruta) if cuerpo is None else await funcion(ruta, json=cuerpo)

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == MENSAJE_SIN_SESION


@pytest.mark.parametrize(
    "email",
    ["mecanico@example.com", "cliente@example.com"],
)
async def test_alta_con_rol_no_autorizado_responde_403(client, login, email):
    await login(email)

    respuesta = await client.post(
        "/ordenes",
        json={
            "vehiculo_id": VEHICULO_LAURA,
            "falla": "Sin permiso",
            "items": [{"repuesto_id": REPUESTO_FILTRO, "cantidad": 1}],
        },
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == MENSAJE_SIN_PERMISO


@pytest.mark.parametrize(
    "email",
    ["recepcion@example.com", "cliente@example.com"],
)
async def test_terminar_con_rol_no_autorizado_responde_403(client, login, email):
    await login(email)

    respuesta = await client.post(f"/ordenes/{ORDEN_JORGE}/terminar")

    assert respuesta.status_code == 403


# --- Aviso simulado (US-026 / DD-13) ---------------------------------------


def _habilitar_logger_de_ordenes() -> None:
    """Reactiva el logger que ``alembic`` desactiva al migrar la base de test.

    ``migrations/env.py`` llama a ``logging.config.fileConfig``, cuyo valor por
    defecto es ``disable_existing_loggers=True``: al correr la migración, el
    logger ``app.ordenes`` creado al importar el servicio queda en
    ``disabled=True`` y ``caplog`` no ve nada aunque la tarea de fondo se
    ejecute. La suite lo reactiva antes de capturar.
    """
    logging.getLogger("app.ordenes").disabled = False


async def test_terminar_agenda_el_aviso_simulado(client, login, caplog):
    await login("recepcion@example.com")
    orden = await _crear_orden(client)

    await login("mecanico@example.com")
    assert (await client.post(f"/ordenes/{orden['id']}/iniciar")).status_code == 200

    _habilitar_logger_de_ordenes()
    with caplog.at_level(logging.INFO, logger="app.ordenes"):
        respuesta = await client.post(f"/ordenes/{orden['id']}/terminar")

    assert respuesta.status_code == 200
    # El ASGITransport ejecuta las tareas de fondo antes de devolver el control;
    # el aviso incluye el id de la orden y sólo aparece tras confirmar.
    assert any(
        f"orden {orden['id']}" in registro.getMessage().lower()
        or str(orden["id"]) in registro.getMessage()
        for registro in caplog.records
    )


async def test_terminar_rechazado_no_agenda_el_aviso(client, login, caplog):
    await login("mecanico@example.com")

    _habilitar_logger_de_ordenes()
    with caplog.at_level(logging.INFO, logger="app.ordenes"):
        respuesta = await client.post("/ordenes/2/terminar")

    assert respuesta.status_code == 409
    assert not caplog.records
