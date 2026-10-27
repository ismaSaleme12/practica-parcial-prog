"""Réplica automatizada de ``test/repuestos.http`` (change C-10).

Cubre la Épica 7 (US-020 a US-022):

- **C-16**: el ``stock`` no se edita por PATCH (422) y la búsqueda con comillas
  no inyecta SQL (``total: 0``).
- **C-18**: un cambio de precio deja exactamente una línea en
  ``historial_precio_repuesto`` en el mismo UoW; un PATCH que **no** cambia el
  precio no deja ninguna (RN-20).
- **RN-14**: el stock sólo cambia por movimientos — alta con ``stock_inicial``
  y ``POST /repuestos/{id}/reponer`` —, nunca por PATCH.
- Baja lógica: 204, después 404 y el ``codigo`` queda libre para un alta nueva
  (índice único parcial).
- Matriz de permisos: 401 sin sesión y 403 de RECEPCION/MECANICO donde la KB
  exige ADMIN.

Usa los fixtures de ``test/conftest.py`` (``client``, ``login``, ``token_*``,
``motor``). El seed se re-ejecuta antes de cada test, así que cada uno arranca
con los cuatro repuestos (``FA-001`` stock 10, ``PF-002`` 4, ``BU-003`` 2,
``AC-004`` 20), un movimiento «Stock inicial» por repuesto y una línea de
historial de precio para ``FA-001`` (8000.00 → 8500.00).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

MENSAJE_VALIDACION = "La petición no cumple el contrato."
MENSAJE_CONFLICTO = "La operación entra en conflicto con datos ya guardados."

# Las seis rutas que la KB reserva a ADMIN (03_actores_y_roles.md).
RUTAS_ADMIN = [
    ("post", "/repuestos", {"codigo": "ZZ-900", "descripcion": "Alta", "precio": "100.00"}),
    ("patch", "/repuestos/1", {"descripcion": "Cambio"}),
    ("delete", "/repuestos/1", None),
    ("post", "/repuestos/1/reponer", {"cantidad": 1}),
    ("get", "/repuestos/1/movimientos", None),
    ("get", "/repuestos/1/precios", None),
]


async def _filas(motor, sql: str, **parametros: Any) -> list[tuple]:
    """Ejecuta una consulta contra la base real de test y devuelve sus filas."""
    async with motor.connect() as conexion:
        resultado = await conexion.execute(text(sql), parametros)
        return list(resultado.all())


def _campos(cuerpo: dict) -> str:
    """Concatena los campos del error de validación para poder buscarlos."""
    return " ".join(error.get("campo", "") for error in cuerpo.get("errores", []))


def _llamar(client, metodo: str, ruta: str, cuerpo: dict | None = None):
    """Llama a la ruta con el método pedido (``GET`` no acepta ``json``)."""
    funcion = getattr(client, metodo)
    if cuerpo is None:
        return funcion(ruta)
    return funcion(ruta, json=cuerpo)


@pytest.fixture
async def admin(client, login) -> int:
    """Inicia sesión como ADMIN y devuelve el id del usuario de la sesión."""
    await login("admin@example.com")
    respuesta = await client.get("/auth/yo")
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["usuario"]["id"]


async def _precios(client, repuesto_id: int = 1) -> dict:
    respuesta = await client.get(f"/repuestos/{repuesto_id}/precios", params={"size": 100})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


async def _movimientos(client, repuesto_id: int = 1) -> dict:
    respuesta = await client.get(
        f"/repuestos/{repuesto_id}/movimientos", params={"size": 100}
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


# --- C-16: el stock no se edita a mano --------------------------------------


async def test_patch_con_stock_responde_422(client, admin):
    respuesta = await client.patch("/repuestos/1", json={"stock": 99})

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["detail"] == MENSAJE_VALIDACION
    assert "stock" in _campos(cuerpo)


async def test_patch_con_stock_inicial_responde_422(client, admin):
    respuesta = await client.patch("/repuestos/1", json={"stock_inicial": 99})

    assert respuesta.status_code == 422
    assert "stock_inicial" in _campos(respuesta.json())


async def test_el_stock_no_cambia_cuando_el_patch_falla(client, admin):
    intento = await client.patch("/repuestos/1", json={"stock": 99})
    assert intento.status_code == 422

    detalle = await client.get("/repuestos/1")

    assert detalle.status_code == 200
    assert detalle.json()["stock"] == 10


# --- C-16: búsqueda con parámetros ligados ----------------------------------


async def test_busqueda_con_inyeccion_devuelve_lista_vacia(client, admin):
    respuesta = await client.get("/repuestos", params={"q": "' OR '1'='1"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["items"] == []
    assert cuerpo["total"] == 0
    assert cuerpo["pages"] == 0


# --- PATCH: sólo descripción y precio (C-18 / RN-20) ------------------------


async def test_patch_solo_descripcion_no_deja_linea_de_precio(client, admin):
    antes = await _precios(client)

    respuesta = await client.patch(
        "/repuestos/1", json={"descripcion": "Filtro de aceite premium"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["descripcion"] == "Filtro de aceite premium"
    assert respuesta.json()["precio"] == "8500.00"
    assert (await _precios(client))["total"] == antes["total"]


async def test_patch_con_precio_nuevo_deja_una_linea_con_el_anterior_y_el_nuevo(
    client, admin
):
    antes = await _precios(client)

    respuesta = await client.patch("/repuestos/1", json={"precio": "9000.00"})

    assert respuesta.status_code == 200
    assert respuesta.json()["precio"] == "9000.00"

    despues = await _precios(client)
    assert despues["total"] == antes["total"] + 1
    ultima = despues["items"][-1]
    assert ultima["precio_anterior"] == "8500.00"
    assert ultima["precio_nuevo"] == "9000.00"
    assert ultima["usuario_id"] == admin


async def test_patch_con_el_mismo_precio_no_deja_linea(client, admin):
    antes = await _precios(client)

    respuesta = await client.patch("/repuestos/1", json={"precio": "8500.00"})

    assert respuesta.status_code == 200
    assert respuesta.json()["precio"] == "8500.00"
    assert (await _precios(client))["total"] == antes["total"]


async def test_dos_cambios_de_precio_dejan_dos_lineas(client, admin):
    antes = await _precios(client)

    assert (
        await client.patch("/repuestos/1", json={"precio": "9000.00"})
    ).status_code == 200
    assert (
        await client.patch("/repuestos/1", json={"precio": "9500.50"})
    ).status_code == 200

    despues = await _precios(client)
    assert despues["total"] == antes["total"] + 2
    ultimas = despues["items"][-2:]
    assert [item["precio_anterior"] for item in ultimas] == ["8500.00", "9000.00"]
    assert [item["precio_nuevo"] for item in ultimas] == ["9000.00", "9500.50"]


async def test_patch_cambiando_descripcion_y_precio_deja_una_sola_linea(client, admin):
    antes = await _precios(client)

    respuesta = await client.patch(
        "/repuestos/1",
        json={"descripcion": "Filtro premium", "precio": "9100.00"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["descripcion"] == "Filtro premium"
    assert cuerpo["precio"] == "9100.00"
    assert (await _precios(client))["total"] == antes["total"] + 1


async def test_patch_de_repuesto_inexistente_responde_404(client, admin):
    respuesta = await client.patch("/repuestos/999999", json={"precio": "9000.00"})

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "No existe el repuesto con id 999999."


async def test_patch_con_precio_invalido_responde_422(client, admin):
    respuesta = await client.patch("/repuestos/1", json={"precio": "0.00"})

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == MENSAJE_VALIDACION


# --- Alta con stock_inicial (RN-14) ----------------------------------------


async def test_alta_con_stock_inicial_deja_stock_y_movimiento(client, admin):
    respuesta = await client.post(
        "/repuestos",
        json={
            "codigo": "ZZ-901",
            "descripcion": "Bomba de agua",
            "precio": "15000.00",
            "stock_inicial": 7,
        },
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["stock"] == 7
    assert cuerpo["precio"] == "15000.00"

    movimientos = await _movimientos(client, cuerpo["id"])
    assert movimientos["total"] == 1
    movimiento = movimientos["items"][0]
    assert movimiento["cantidad"] == 7
    assert movimiento["motivo"] == "Stock inicial"
    assert movimiento["usuario_id"] == admin
    assert movimiento["orden_id"] is None


async def test_alta_sin_stock_inicial_no_deja_movimiento(client, admin):
    respuesta = await client.post(
        "/repuestos",
        json={"codigo": "ZZ-902", "descripcion": "Sin stock", "precio": "500.00"},
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["stock"] == 0
    assert (await _movimientos(client, respuesta.json()["id"]))["total"] == 0


async def test_alta_con_stock_inicial_negativo_responde_422(client, admin):
    respuesta = await client.post(
        "/repuestos",
        json={
            "codigo": "ZZ-903",
            "descripcion": "Negativo",
            "precio": "500.00",
            "stock_inicial": -1,
        },
    )

    assert respuesta.status_code == 422
    assert "stock_inicial" in _campos(respuesta.json())


async def test_alta_con_stock_sigue_prohibida_responde_422(client, admin):
    respuesta = await client.post(
        "/repuestos",
        json={
            "codigo": "ZZ-904",
            "descripcion": "Stock por la puerta de atrás",
            "precio": "500.00",
            "stock": 5,
        },
    )

    assert respuesta.status_code == 422
    assert "stock" in _campos(respuesta.json())


# --- Reposición (RN-14) -----------------------------------------------------


async def test_reponer_incrementa_el_stock_y_deja_movimiento(client, admin):
    respuesta = await client.post("/repuestos/3/reponer", json={"cantidad": 5})

    assert respuesta.status_code == 200
    assert respuesta.json()["stock"] == 7

    movimientos = await _movimientos(client, 3)
    assert movimientos["total"] == 2
    ultimo = movimientos["items"][-1]
    assert ultimo["cantidad"] == 5
    assert ultimo["motivo"] == "Reposición"
    assert ultimo["usuario_id"] == admin


async def test_reponer_con_cantidad_cero_o_negativa_responde_422(client, admin):
    cero = await client.post("/repuestos/3/reponer", json={"cantidad": 0})
    negativa = await client.post("/repuestos/3/reponer", json={"cantidad": -2})

    assert cero.status_code == 422
    assert negativa.status_code == 422
    assert "cantidad" in _campos(cero.json())


async def test_reponer_repuesto_inexistente_responde_404(client, admin):
    respuesta = await client.post("/repuestos/999999/reponer", json={"cantidad": 1})

    assert respuesta.status_code == 404


# --- Baja lógica ------------------------------------------------------------


async def test_delete_es_baja_logica_y_la_fila_se_conserva(client, admin, motor):
    respuesta = await client.delete("/repuestos/1")

    assert respuesta.status_code == 204

    detalle = await client.get("/repuestos/1")
    assert detalle.status_code == 404

    filas = await _filas(
        motor,
        "SELECT borrado_en FROM repuesto WHERE codigo = 'FA-001' ORDER BY id",
    )
    assert len(filas) == 1
    assert filas[0][0] is not None


async def test_el_codigo_queda_libre_tras_la_baja(client, admin, motor):
    assert (await client.delete("/repuestos/1")).status_code == 204

    respuesta = await client.post(
        "/repuestos",
        json={"codigo": "FA-001", "descripcion": "Filtro nuevo", "precio": "9000.00"},
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["codigo"] == "FA-001"
    filas = await _filas(
        motor,
        "SELECT borrado_en FROM repuesto WHERE codigo = 'FA-001' ORDER BY id",
    )
    assert len(filas) == 2
    assert filas[0][0] is not None
    assert filas[1][0] is None


async def test_delete_de_un_repuesto_ya_dado_de_baja_responde_404(client, admin):
    assert (await client.delete("/repuestos/1")).status_code == 204

    respuesta = await client.delete("/repuestos/1")

    assert respuesta.status_code == 404


async def test_codigo_repetido_entre_vigentes_responde_409(client, admin):
    respuesta = await client.post(
        "/repuestos",
        json={"codigo": "FA-001", "descripcion": "Otro filtro", "precio": "9999.00"},
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == MENSAJE_CONFLICTO


# --- Historiales paginados --------------------------------------------------


async def test_movimientos_paginados(client, admin):
    # El seed deja un movimiento; la reposición agrega el segundo.
    assert (await client.post("/repuestos/3/reponer", json={"cantidad": 3})).status_code == 200

    primera = await client.get(
        "/repuestos/3/movimientos", params={"page": 1, "size": 1}
    )
    segunda = await client.get(
        "/repuestos/3/movimientos", params={"page": 2, "size": 1}
    )

    assert primera.status_code == 200
    assert segunda.status_code == 200
    cuerpo_primera = primera.json()
    assert set(cuerpo_primera) == {"items", "total", "page", "size", "pages"}
    assert cuerpo_primera["total"] == 2
    assert cuerpo_primera["pages"] == 2

    ids = [cuerpo_primera["items"][0]["id"], segunda.json()["items"][0]["id"]]
    assert len(set(ids)) == 2

    fuera = await client.get("/repuestos/3/movimientos", params={"page": 3, "size": 1})
    assert fuera.status_code == 422


async def test_precios_paginados(client, admin):
    assert (
        await client.patch("/repuestos/1", json={"precio": "9000.00"})
    ).status_code == 200
    assert (
        await client.patch("/repuestos/1", json={"precio": "9100.00"})
    ).status_code == 200

    primera = await client.get("/repuestos/1/precios", params={"page": 1, "size": 2})
    segunda = await client.get("/repuestos/1/precios", params={"page": 2, "size": 2})

    assert primera.status_code == 200
    assert segunda.status_code == 200
    cuerpo = primera.json()
    assert cuerpo["total"] == 3  # una del seed + las dos del test
    assert cuerpo["pages"] == 2
    assert len(cuerpo["items"]) == 2
    assert len(segunda.json()["items"]) == 1


async def test_movimientos_ordenados_por_cuando_e_id(client, admin):
    assert (await client.post("/repuestos/3/reponer", json={"cantidad": 3})).status_code == 200
    assert (await client.post("/repuestos/3/reponer", json={"cantidad": 4})).status_code == 200

    movimientos = await _movimientos(client, 3)

    cantidades = [item["cantidad"] for item in movimientos["items"]]
    ids = [item["id"] for item in movimientos["items"]]
    assert cantidades == [2, 3, 4]
    assert ids == sorted(ids)


async def test_movimientos_de_repuesto_inexistente_responde_404(client, admin):
    respuesta = await client.get("/repuestos/999999/movimientos")

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "No existe el repuesto con id 999999."


async def test_precios_de_repuesto_inexistente_responde_404(client, admin):
    respuesta = await client.get("/repuestos/999999/precios")

    assert respuesta.status_code == 404


# --- Permisos: 401 sin sesión y 403 sin ADMIN -------------------------------


@pytest.mark.parametrize("metodo,ruta,cuerpo", RUTAS_ADMIN)
async def test_sin_sesion_responde_401(client, metodo, ruta, cuerpo):
    respuesta = await _llamar(client, metodo, ruta, cuerpo)

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == "No hay una sesión válida."


@pytest.mark.parametrize("metodo,ruta,cuerpo", RUTAS_ADMIN)
async def test_recepcion_recibe_403_en_las_rutas_de_admin(
    client, token_recepcion, metodo, ruta, cuerpo
):
    respuesta = await _llamar(client, metodo, ruta, cuerpo)

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No tenés permiso para realizar esta operación."


@pytest.mark.parametrize("metodo,ruta,cuerpo", RUTAS_ADMIN)
async def test_mecanico_recibe_403_en_las_rutas_de_admin(
    client, token_mecanico, metodo, ruta, cuerpo
):
    respuesta = await _llamar(client, metodo, ruta, cuerpo)

    assert respuesta.status_code == 403


async def test_recepcion_puede_consultar_el_catalogo(client, token_recepcion):
    listado = await client.get("/repuestos")
    detalle = await client.get("/repuestos/1")

    assert listado.status_code == 200
    assert detalle.status_code == 200
