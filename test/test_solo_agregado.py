"""Réplica automatizada del caso C-14: sólo agregado e integridad del catálogo.

La consigna pide ``test/solo_agregado.sql`` con captura de psql (Flujo 13). Este
archivo **no reemplaza** esa evidencia: la automatiza para que la suite falle si
alguien quita el disparador de la migración ``0002`` o debilita la clave foránea
de ``orden_trabajo.estado`` al catálogo ``estado_orden`` (RN-15 / RN-19).

Qué se prueba, con SQL crudo sobre el motor real (sin psql y sin dependencias
nuevas — ``sqlalchemy.text`` ya viene con SQLAlchemy 2.0):

1. ``UPDATE`` sobre cada una de las tres tablas de auditoría → el disparador
   lanza una violación de integridad (SQLSTATE ``23000``).
2. ``DELETE`` sobre cada una de las tres tablas → lo mismo.
3. ``INSERT`` de una ``orden_trabajo`` con ``estado = 'INVENTADO'`` → la clave
   foránea al catálogo lo rechaza (SQLSTATE ``23503``).
4. Los intentos fallidos **no escriben nada**: las filas quedan exactamente como
   las dejó el seed.
5. ``TRUNCATE`` **no** dispara el disparador (es ``BEFORE UPDATE OR DELETE``):
   por eso ``seed.py`` puede reiniciar la base. Se comprueba dentro de una
   transacción que termina en ``rollback``, así que la tabla no queda vacía.
6. ``INSERT`` sigue permitido: sólo agregado significa «agregá, no corrijas».

Cada intento corre en su **propia** transacción (``motor.begin()``): en
PostgreSQL una transacción abortada no admite la sentencia siguiente hasta el
``ROLLBACK``, y los errores buscados abortan la transacción por diseño.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

TABLAS_AUDITORIA = (
    "historial_estado_orden",
    "movimiento_stock",
    "historial_precio_repuesto",
)

# Un UPDATE inocuo por tabla: escribir la misma columna con su propio valor es
# suficiente para que el disparador BEFORE UPDATE se dispare.
UPDATE_INOCUO = {
    "historial_estado_orden": "UPDATE historial_estado_orden SET usuario_id = usuario_id",
    "movimiento_stock": "UPDATE movimiento_stock SET motivo = motivo",
    "historial_precio_repuesto": (
        "UPDATE historial_precio_repuesto SET precio_nuevo = precio_nuevo"
    ),
}

DELETE = {
    tabla: f"DELETE FROM {tabla}" for tabla in TABLAS_AUDITORIA
}

INSERT_ESTADO_INVENTADO = (
    "INSERT INTO orden_trabajo (vehiculo_id, estado, falla, total) "
    "VALUES (1, 'INVENTADO', 'Estado fuera del catálogo', 0)"
)

# SQLSTATE de la función de la migración (ERRCODE integrity_constraint_violation)
# y de una violación de clave foránea.
SQLSTATE_INTEGRIDAD = "23000"
SQLSTATE_FK = "23503"

# Conteo que deja ``seed.py`` (``RESTART IDENTITY``).
FILAS_DEL_SEED = {
    "historial_estado_orden": 3,
    "movimiento_stock": 4,
    "historial_precio_repuesto": 1,
}


async def _contar(motor, tabla: str) -> int:
    async with motor.connect() as conexion:
        resultado = await conexion.execute(text(f"SELECT count(*) FROM {tabla}"))
        return int(resultado.scalar_one())


async def _capturar_error(motor, sql: str) -> DBAPIError:
    """Ejecuta ``sql`` en su propia transacción y devuelve el error de la base.

    ``motor.begin()`` revierte al salir con excepción, así que la conexión vuelve
    al pool limpia y el intento siguiente arranca de cero.
    """
    with pytest.raises(DBAPIError) as capturado:
        async with motor.begin() as conexion:
            await conexion.execute(text(sql))
    return capturado.value


def _verificar_disparador(error: DBAPIError, tabla: str, operacion: str) -> None:
    """El rechazo es una violación de integridad con el mensaje del disparador.

    Se asserta el SQLSTATE además del texto: el texto del servidor está
    localizado (``lc_messages = Spanish_Argentina.1252``) y la traducción no es
    parte del contrato; el código sí.
    """
    assert isinstance(error, IntegrityError), error
    assert getattr(error.orig, "sqlstate", None) == SQLSTATE_INTEGRIDAD, error
    mensaje = str(error.orig)
    assert tabla in mensaje, mensaje
    assert "es de sólo agregado" in mensaje, mensaje
    assert f"{operacion} no está permitido" in mensaje, mensaje


# --- UPDATE y DELETE sobre las tres tablas de auditoría ----------------------


@pytest.mark.parametrize("tabla", TABLAS_AUDITORIA)
async def test_update_rechazado_por_el_disparador(motor, tabla):
    """``UPDATE`` sobre una tabla de auditoría lo rechaza el disparador (RN-15)."""
    error = await _capturar_error(motor, UPDATE_INOCUO[tabla])

    _verificar_disparador(error, tabla, "UPDATE")
    assert await _contar(motor, tabla) == FILAS_DEL_SEED[tabla]


@pytest.mark.parametrize("tabla", TABLAS_AUDITORIA)
async def test_delete_rechazado_por_el_disparador(motor, tabla):
    """``DELETE`` sobre una tabla de auditoría lo rechaza el disparador (RN-15)."""
    error = await _capturar_error(motor, DELETE[tabla])

    _verificar_disparador(error, tabla, "DELETE")
    assert await _contar(motor, tabla) == FILAS_DEL_SEED[tabla]


# --- El catálogo se impone por clave foránea (RN-19) -------------------------


async def test_insert_con_estado_fuera_del_catalogo_viola_la_fk(motor):
    """Un estado que no existe en ``estado_orden`` no puede entrar en una orden."""
    error = await _capturar_error(motor, INSERT_ESTADO_INVENTADO)

    assert isinstance(error, IntegrityError), error
    assert getattr(error.orig, "sqlstate", None) == SQLSTATE_FK, error
    assert "fk_orden_trabajo_estado" in str(error.orig), error
    assert await _contar(motor, "orden_trabajo") == 2


# --- Los errores no dejan rastro --------------------------------------------


async def test_los_intentos_fallidos_no_escriben_nada(motor):
    """Después de los siete intentos, cada fila sigue exactamente como estaba."""
    antes = {tabla: await _contar(motor, tabla) for tabla in TABLAS_AUDITORIA}

    for tabla in TABLAS_AUDITORIA:
        await _capturar_error(motor, UPDATE_INOCUO[tabla])
        await _capturar_error(motor, DELETE[tabla])
    await _capturar_error(motor, INSERT_ESTADO_INVENTADO)

    despues = {tabla: await _contar(motor, tabla) for tabla in TABLAS_AUDITORIA}
    assert despues == antes == FILAS_DEL_SEED

    # Y no sólo cambia el conteo: los valores siguen intactos.
    async with motor.connect() as conexion:
        precio = await conexion.execute(
            text(
                "SELECT precio_nuevo FROM historial_precio_repuesto "
                "WHERE repuesto_id = 1"
            )
        )
        assert str(precio.scalar_one()) == "8500.00"

        stock = await conexion.execute(text("SELECT stock FROM repuesto WHERE id = 3"))
        assert stock.scalar_one() == 2

        estado = await conexion.execute(
            text("SELECT estado FROM orden_trabajo WHERE id = 2")
        )
        assert estado.scalar_one() == "EN_REPARACION"


# --- TRUNCATE no dispara el disparador (por eso el seed puede reiniciar) ----


async def test_truncate_no_dispara_el_disparador_y_el_seed_puede_reiniciar(motor):
    """El disparador es ``BEFORE UPDATE OR DELETE``: ``TRUNCATE`` no lo dispara.

    ``seed.py`` vacía con ``TRUNCATE ... RESTART IDENTITY CASCADE`` justamente
    por esto. La prueba corre dentro de una transacción que **revierte**, así que
    la tabla no queda vacía: sólo demuestra que el vaciado está permitido.
    """
    async with motor.connect() as conexion:
        transaccion = await conexion.begin()
        try:
            await conexion.execute(text("TRUNCATE historial_estado_orden"))
            vacia = await conexion.execute(
                text("SELECT count(*) FROM historial_estado_orden")
            )
            assert vacia.scalar_one() == 0
        finally:
            await transaccion.rollback()

    assert await _contar(motor, "historial_estado_orden") == 3


# --- INSERT sigue permitido: sólo agregado no es «sólo lectura» --------------


async def test_insert_sigue_permitido(motor):
    """Agregar una fila nueva es la corrección prevista; el disparador no la bloquea."""
    async with motor.connect() as conexion:
        transaccion = await conexion.begin()
        try:
            await conexion.execute(
                text(
                    "INSERT INTO historial_estado_orden "
                    "(orden_id, desde_estado, hasta_estado, usuario_id, cuando) "
                    "VALUES (1, 'PENDIENTE', 'CANCELADA', 3, now())"
                )
            )
            dentro = await conexion.execute(
                text("SELECT count(*) FROM historial_estado_orden")
            )
            assert dentro.scalar_one() == 4
        finally:
            await transaccion.rollback()

    assert await _contar(motor, "historial_estado_orden") == 3
