"""Réplica automatizada de ``test/clientes.http`` (change C-09, Épica 6).

Cubre el módulo ``clientes`` completo (US-017 a US-019):

- alta de clientes y vehículos con las restricciones de la base (RN-01): el
  ``documento`` es único y la ``patente`` es única **entre los vigentes**
  (índice único parcial ``WHERE borrado_en IS NULL``), sin consulta previa;
  el ``anio`` fuera de 1950–2100 es 422 del contrato.
- ficha del cliente **con sus vehículos** resueltos por carga anticipada en el
  repositorio (``selectinload``): las relaciones declaran
  ``lazy="raise_on_sql"``, así que si el servicio olvidara la precarga la
  respuesta sería un error, no un 200.
- baja lógica del vehículo (RN-16): escribe ``borrado_en`` y la fila se
  conserva; con órdenes **abiertas** (``estado.es_final = false``) responde 409.
- **caso C-19**: después de la baja, la misma patente se puede volver a
  registrar; mientras haya una patente **vigente** igual, el alta es 409.
- **lo propio (RN-17)**: ``GET /mis-vehiculos`` sólo pide estar autenticado y
  devuelve únicamente los vehículos del cliente dueño de la sesión. Un usuario
  sin ficha de cliente recibe una lista vacía, no 404 ni 500.

Usa los fixtures de ``C-05`` (``test/conftest.py``): ``client`` es un
``httpx.AsyncClient`` con ``ASGITransport``, el seed se re-ejecuta antes de cada
test (ids deterministas) y ``asyncio_mode = auto`` evita el decorador.

Ids del seed que usa este archivo: clientes 1 (Laura, con usuario
``cliente@example.com``) y 2 (Jorge, sin usuario); vehículos 1 (``AAA111``, con
una orden PENDIENTE), 2 (``AAB222``, sin órdenes) y 3 (``BBB333`` de Jorge, con
una orden EN_REPARACION).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

MENSAJE_CONFLICTO = "La operación entra en conflicto con datos ya guardados."


async def _filas(motor, sql: str, **parametros: Any) -> list[tuple]:
    """Ejecuta una consulta contra la base real de test y devuelve sus filas."""
    async with motor.connect() as conexion:
        resultado = await conexion.execute(text(sql), parametros)
        return list(resultado.all())


def _patentes(ficha: dict) -> set[str]:
    return {vehiculo["patente"] for vehiculo in ficha["vehiculos"]}


def _vehiculo(patente: str, anio: int = 2022) -> dict:
    """Cuerpo válido de alta de vehículo (el router recibe el patente por URL)."""
    return {
        "patente": patente,
        "marca": "Chevrolet",
        "modelo": "Onix",
        "anio": anio,
    }


# --- US-017: alta de clientes y vehículos --------------------------------


async def test_alta_de_cliente_201_y_documento_duplicado_409(client, login):
    await login("recepcion@example.com")

    alta = await client.post(
        "/clientes",
        json={
            "nombre": "Carlos Pérez",
            "documento": "33444555",
            "telefono": "1145550003",
        },
    )

    assert alta.status_code == 201, alta.text
    cuerpo = alta.json()
    assert cuerpo["id"] == 3
    assert cuerpo["documento"] == "33444555"
    assert cuerpo["nombre"] == "Carlos Pérez"
    # El alta devuelve la ficha plana; los vehículos son de GET /clientes/{id}.
    assert "vehiculos" not in cuerpo

    repetido = await client.post(
        "/clientes",
        json={
            "nombre": "Otro Carlos",
            "documento": "33444555",
            "telefono": "1145550009",
        },
    )

    assert repetido.status_code == 409
    assert repetido.json()["detail"] == MENSAJE_CONFLICTO


async def test_alta_de_cliente_rechaza_campos_no_declarados(client, login):
    await login("recepcion@example.com")

    # ``usuario_id`` no se declara en el contrato: enlazar una cuenta no es una
    # operación de esta ruta y debe rechazarse (extra="forbid").
    respuesta = await client.post(
        "/clientes",
        json={
            "nombre": "Con Cuenta",
            "documento": "33444556",
            "telefono": "1145550004",
            "usuario_id": 6,
        },
    )

    assert respuesta.status_code == 422


async def test_alta_de_vehiculo_201_y_patente_vigente_duplicada_409(client, login):
    await login("recepcion@example.com")

    alta = await client.post("/clientes/2/vehiculos", json=_vehiculo("CCC444"))

    assert alta.status_code == 201, alta.text
    cuerpo = alta.json()
    assert cuerpo["id"] == 4
    assert cuerpo["cliente_id"] == 2
    assert cuerpo["patente"] == "CCC444"

    # La patente AAA111 está vigente (vehículo 1): la base la rechaza por el
    # índice único parcial y el handler central traduce a 409.
    repetida = await client.post("/clientes/2/vehiculos", json=_vehiculo("AAA111"))

    assert repetida.status_code == 409
    assert repetida.json()["detail"] == MENSAJE_CONFLICTO


async def test_alta_de_vehiculo_rechaza_campos_no_declarados(client, login):
    await login("recepcion@example.com")

    respuesta = await client.post(
        "/clientes/2/vehiculos",
        json={**_vehiculo("DDD555"), "borrado_en": "2026-01-01T00:00:00+00:00"},
    )

    assert respuesta.status_code == 422


async def test_anio_fuera_de_rango_responde_422(client, login):
    await login("recepcion@example.com")

    # Los mismos límites que el CHECK de la base (1950–2100), validados en el
    # contrato para que la respuesta sea 422 y no un 409 de integridad.
    anterior = await client.post("/clientes/2/vehiculos", json=_vehiculo("EEE666", 1949))
    posterior = await client.post(
        "/clientes/2/vehiculos", json=_vehiculo("FFF777", 2101)
    )

    assert anterior.status_code == 422
    assert posterior.status_code == 422


async def test_cliente_inexistente_responde_404(client, login):
    await login("recepcion@example.com")

    ficha = await client.get("/clientes/999999")
    alta = await client.post("/clientes/999999/vehiculos", json=_vehiculo("GGG888"))

    assert ficha.status_code == 404
    assert alta.status_code == 404


async def test_ficha_del_cliente_trae_sus_vehiculos_por_carga_anticipada(
    client, login
):
    await login("recepcion@example.com")

    respuesta = await client.get("/clientes/1")

    # Las relaciones usan lazy="raise_on_sql": un 200 con los vehículos prueba
    # que el repositorio los precargó (selectinload) en un número fijo de consultas.
    assert respuesta.status_code == 200, respuesta.text
    ficha = respuesta.json()
    assert ficha["id"] == 1
    assert ficha["documento"] == "30111222"
    assert _patentes(ficha) == {"AAA111", "AAB222"}

    jorge = await client.get("/clientes/2")
    assert jorge.status_code == 200
    assert _patentes(jorge.json()) == {"BBB333"}


# --- US-018: baja lógica de vehículos ------------------------------------


async def test_baja_con_orden_abierta_responde_409(client, login, motor):
    await login("recepcion@example.com")

    # Vehículo 1: orden PENDIENTE (es_final = false). Vehículo 3: EN_REPARACION.
    pendiente = await client.delete("/vehiculos/1")
    en_reparacion = await client.delete("/vehiculos/3")

    assert pendiente.status_code == 409
    assert "abiertas" in pendiente.json()["detail"]
    assert en_reparacion.status_code == 409

    sin_baja = await _filas(
        motor,
        """
        SELECT id, borrado_en
          FROM vehiculo
         WHERE id IN (1, 3)
         ORDER BY id
        """,
    )
    assert sin_baja == [(1, None), (3, None)]  # la baja rechazada no escribió nada


async def test_baja_logica_permite_reusar_la_patente_caso_c19(client, login, motor):
    await login("recepcion@example.com")

    # El vehículo 2 (AAB222) no tiene órdenes: se puede dar de baja.
    baja = await client.delete("/vehiculos/2")
    assert baja.status_code == 204
    assert baja.content == b""

    # La fila no se borra: queda con borrado_en y deja de aparecer en la ficha.
    fila = await _filas(
        motor,
        "SELECT borrado_en FROM vehiculo WHERE id = 2",
    )
    assert len(fila) == 1
    assert fila[0][0] is not None

    ficha = await client.get("/clientes/1")
    assert _patentes(ficha.json()) == {"AAA111"}

    # Caso C-19: la misma patente se vuelve a registrar porque la anterior está
    # dada de baja (el índice único parcial sólo mira los vigentes).
    reuso = await client.post("/clientes/1/vehiculos", json=_vehiculo("AAB222", 2019))
    assert reuso.status_code == 201, reuso.text
    assert reuso.json()["id"] == 4
    assert reuso.json()["anio"] == 2019

    # Mientras haya una vigente con esa patente, el alta vuelve a ser 409.
    repetida = await client.post("/clientes/1/vehiculos", json=_vehiculo("AAB222", 2020))
    assert repetida.status_code == 409

    # La ficha muestra el vehículo nuevo (vigente), no el dado de baja.
    ficha_final = await client.get("/clientes/1")
    assert _patentes(ficha_final.json()) == {"AAA111", "AAB222"}
    ids = {vehiculo["id"] for vehiculo in ficha_final.json()["vehiculos"]}
    assert ids == {1, 4}

    # Una segunda baja del mismo vehículo es 404: ya no hay nada vigente que bajar.
    assert (await client.delete("/vehiculos/2")).status_code == 404


async def test_baja_de_vehiculo_inexistente_responde_404(client, login):
    await login("recepcion@example.com")

    respuesta = await client.delete("/vehiculos/999999")

    assert respuesta.status_code == 404


# --- US-019 / RN-17: lo propio del cliente -------------------------------


async def test_mis_vehiculos_solo_devuelve_los_del_cliente_de_la_sesion(
    client, login
):
    # Laura (usuario 6) es dueña de los vehículos 1 y 2; el 3 es de Jorge, que no
    # tiene cuenta. RN-17: ve los suyos y ninguno ajeno.
    await login("cliente@example.com")

    respuesta = await client.get("/mis-vehiculos")

    assert respuesta.status_code == 200, respuesta.text
    patentes = {vehiculo["patente"] for vehiculo in respuesta.json()}
    assert patentes == {"AAA111", "AAB222"}
    assert "BBB333" not in patentes

    # La recepción no tiene ficha de cliente: lista vacía, no 404 ni 500.
    await login("recepcion@example.com")
    vacia = await client.get("/mis-vehiculos")
    assert vacia.status_code == 200
    assert vacia.json() == []

    # Tampoco el ADMIN, que no está atado a ninguna ficha.
    await login("admin@example.com")
    assert (await client.get("/mis-vehiculos")).json() == []


async def test_mis_vehiculos_exige_sesion(client):
    assert (await client.get("/mis-vehiculos")).status_code == 401


# --- Matriz RBAC de la Épica 6 (03_actores_y_roles.md) --------------------


async def test_sin_sesion_los_endpoints_de_clientes_responden_401(client):
    assert (await client.get("/clientes/1")).status_code == 401
    assert (
        await client.post(
            "/clientes",
            json={"nombre": "X", "documento": "111", "telefono": "555"},
        )
    ).status_code == 401
    assert (
        await client.post("/clientes/1/vehiculos", json=_vehiculo("HHH999"))
    ).status_code == 401
    assert (await client.delete("/vehiculos/2")).status_code == 401


async def test_cliente_y_mecanico_no_pueden_administrar_clientes(client, login):
    # La matriz sólo concede estas rutas a ADMIN y RECEPCION; MECANICO y CLIENTE
    # tienen sesión válida (403, no 401).
    for email in ("cliente@example.com", "mecanico@example.com"):
        await login(email)

        assert (
            await client.post(
                "/clientes",
                json={"nombre": "X", "documento": "111", "telefono": "555"},
            )
        ).status_code == 403
        assert (await client.get("/clientes/1")).status_code == 403
        assert (
            await client.post("/clientes/1/vehiculos", json=_vehiculo("III000"))
        ).status_code == 403
        assert (await client.delete("/vehiculos/2")).status_code == 403

    # ADMIN puede la baja: la matriz le da las cuatro rutas.
    await login("admin@example.com")
    assert (await client.get("/clientes/1")).status_code == 200
    assert (await client.delete("/vehiculos/2")).status_code == 204
