"""Deja la base en el estado inicial conocido que usan los casos de prueba.

Uso::

    alembic upgrade head     # el esquema se crea SÓLO con Alembic
    python seed.py           # este script carga los datos

Qué hace:

1. Vacía las trece tablas con ``TRUNCATE ... RESTART IDENTITY CASCADE``. Se usa
   TRUNCATE y no DELETE porque los disparadores de sólo agregado (migración
   ``0002``) rechazan el borrado fila por fila. La API nunca trunca: el permiso
   vive en este script de puesta en marcha.
2. Carga el catálogo de estados **primero**: todo lo que tiene un estado apunta
   a él y sin sus filas no se puede crear ninguna orden.
3. Carga usuarios y roles, clientes y vehículos, repuestos con su movimiento de
   «Stock inicial», las dos órdenes de prueba, el historial de precio del filtro
   y el evento de seguridad de la carga inicial.

Todo ocurre en un solo Unit of Work: o queda el estado completo, o no queda nada.
Las contraseñas son **de mentira** y viven sólo acá: ``secreto123``.
"""

import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.core.unit_of_work import UnitOfWork
from app.models import (
    AsignacionRol,
    Cliente,
    EstadoOrden,
    EventoSeguridad,
    HistorialEstadoOrden,
    HistorialPrecioRepuesto,
    ItemOrden,
    MovimientoStock,
    OrdenTrabajo,
    Repuesto,
    Usuario,
    Vehiculo,
)

PASSWORD_SEED = "secreto123"

TABLAS = (
    "historial_estado_orden",
    "movimiento_stock",
    "historial_precio_repuesto",
    "item_orden",
    "orden_trabajo",
    "asignacion_rol",
    "intento_acceso",
    "evento_seguridad",
    "vehiculo",
    "repuesto",
    "cliente",
    "usuario",
    "estado_orden",
)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


async def _cargar(sesion: AsyncSession) -> None:
    # Un solo hash: el costo de bcrypt se paga una vez y todos los usuarios de
    # prueba comparten la contraseña conocida.
    hash_prueba = await hash_password(PASSWORD_SEED)

    # 1. Catálogo primero
    sesion.add_all(
        [
            EstadoOrden(codigo="PENDIENTE", descripcion="Pendiente de reparación", posicion=1, es_final=False),
            EstadoOrden(codigo="EN_REPARACION", descripcion="En reparación", posicion=2, es_final=False),
            EstadoOrden(codigo="TERMINADA", descripcion="Terminada", posicion=3, es_final=True),
            EstadoOrden(codigo="CANCELADA", descripcion="Cancelada", posicion=4, es_final=True),
        ]
    )
    await sesion.flush()

    # 2. Usuarios y roles (una asignación abierta por usuario)
    def usuario(email: str, nombre: str, debe_cambiar: bool = False) -> Usuario:
        return Usuario(
            email=email,
            nombre=nombre,
            password_hash=hash_prueba,
            activo=True,
            debe_cambiar_password=debe_cambiar,
            password_cambiada_en=_ahora(),
        )

    admin = usuario("admin@example.com", "Administrador")
    admin2 = usuario("admin2@example.com", "Administrador Dos")
    recepcion = usuario("recepcion@example.com", "Recepción")
    mecanico = usuario("mecanico@example.com", "Mecánico")
    mecanico2 = usuario("mecanico2@example.com", "Mecánico Dos")
    cliente_usuario = usuario("cliente@example.com", "Laura Gómez")
    nuevo = usuario("nuevo@example.com", "Mecánico Nuevo", debe_cambiar=True)

    usuarios = [admin, admin2, recepcion, mecanico, mecanico2, cliente_usuario, nuevo]
    sesion.add_all(usuarios)
    await sesion.flush()

    roles = [
        (admin, "ADMIN"),
        (admin2, "ADMIN"),
        (recepcion, "RECEPCION"),
        (mecanico, "MECANICO"),
        (mecanico2, "MECANICO"),
        (cliente_usuario, "CLIENTE"),
        (nuevo, "MECANICO"),
    ]
    sesion.add_all(
        [
            AsignacionRol(
                usuario_id=u.id,
                rol=rol,
                desde=_ahora(),
                otorgada_por="SISTEMA",
            )
            for u, rol in roles
        ]
    )

    # 3. Clientes y vehículos
    laura = Cliente(
        usuario_id=cliente_usuario.id,
        nombre="Laura",
        documento="30111222",
        telefono="1145550001",
    )
    jorge = Cliente(nombre="Jorge", documento="27888999", telefono="1145550002")
    sesion.add_all([laura, jorge])
    await sesion.flush()

    vehiculo_laura_1 = Vehiculo(
        cliente_id=laura.id, patente="AAA111", marca="Fiat", modelo="Uno", anio=2015
    )
    vehiculo_laura_2 = Vehiculo(
        cliente_id=laura.id, patente="AAB222", marca="Renault", modelo="Clio", anio=2018
    )
    vehiculo_jorge = Vehiculo(
        cliente_id=jorge.id, patente="BBB333", marca="Ford", modelo="Fiesta", anio=2020
    )
    sesion.add_all([vehiculo_laura_1, vehiculo_laura_2, vehiculo_jorge])
    await sesion.flush()

    # 4. Repuestos con su «Stock inicial» (el stock sólo cambia por movimientos)
    filtro = Repuesto(codigo="FA-001", descripcion="Filtro de aceite", precio=Decimal("8500.00"), stock=10)
    pastillas = Repuesto(codigo="PF-002", descripcion="Pastillas de freno", precio=Decimal("12000.00"), stock=4)
    bujia = Repuesto(codigo="BU-003", descripcion="Bujía", precio=Decimal("1500.00"), stock=2)
    aceite = Repuesto(codigo="AC-004", descripcion="Aceite por litro", precio=Decimal("2500.00"), stock=20)
    repuestos = [filtro, pastillas, bujia, aceite]
    sesion.add_all(repuestos)
    await sesion.flush()

    sesion.add_all(
        [
            MovimientoStock(
                repuesto_id=r.id,
                usuario_id=admin.id,
                cantidad=r.stock,
                motivo="Stock inicial",
                cuando=_ahora(),
            )
            for r in repuestos
        ]
    )

    # 5. Órdenes: la 2 con 4 bujías sobre un stock de 2 (insumo del caso C-11)
    orden_1 = OrdenTrabajo(
        vehiculo_id=vehiculo_laura_1.id,
        mecanico_id=None,
        estado="PENDIENTE",
        falla="Ruido en el motor al acelerar",
        creada_en=_ahora(),
        total=Decimal("0.00"),
    )
    item_2 = ItemOrden(
        repuesto_id=bujia.id,
        cantidad=4,
        precio_unitario=bujia.precio,
    )
    orden_2 = OrdenTrabajo(
        vehiculo_id=vehiculo_jorge.id,
        mecanico_id=mecanico.id,
        estado="EN_REPARACION",
        falla="Cambio de bujías",
        creada_en=_ahora(),
        total=item_2.cantidad * item_2.precio_unitario,
    )
    orden_2.items = [item_2]
    sesion.add_all([orden_1, orden_2])
    await sesion.flush()

    # 6. Historial de estados, precio del filtro y evento de la carga inicial
    sesion.add_all(
        [
            HistorialEstadoOrden(
                orden_id=orden_1.id,
                desde_estado=None,
                hasta_estado="PENDIENTE",
                usuario_id=recepcion.id,
                cuando=_ahora(),
            ),
            HistorialEstadoOrden(
                orden_id=orden_2.id,
                desde_estado=None,
                hasta_estado="PENDIENTE",
                usuario_id=recepcion.id,
                cuando=_ahora(),
            ),
            HistorialEstadoOrden(
                orden_id=orden_2.id,
                desde_estado="PENDIENTE",
                hasta_estado="EN_REPARACION",
                usuario_id=mecanico.id,
                cuando=_ahora(),
            ),
            HistorialPrecioRepuesto(
                repuesto_id=filtro.id,
                usuario_id=admin.id,
                precio_anterior=Decimal("8000.00"),
                precio_nuevo=Decimal("8500.00"),
                cuando=_ahora(),
            ),
            EventoSeguridad(
                cuando=_ahora(),
                actor="SISTEMA",
                accion="Carga de los datos iniciales",
            ),
        ]
    )


async def main() -> None:
    motor = create_async_engine(settings.ASYNC_DATABASE_URL)
    fabrica = async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)

    try:
        async with fabrica() as sesion:
            try:
                await sesion.exec(
                    text("TRUNCATE " + ", ".join(TABLAS) + " RESTART IDENTITY CASCADE")
                )
                async with UnitOfWork(sesion):
                    await _cargar(sesion)
            except ProgrammingError as exc:
                await sesion.rollback()
                # 42P01 = undefined_table. Se mira el SQLSTATE y no el texto
                # porque el mensaje del servidor viene en el idioma configurado.
                if getattr(exc.orig, "sqlstate", None) == "42P01":
                    print(
                        "ERROR: la base no está migrada. Corré primero:\n"
                        "  alembic upgrade head",
                        file=sys.stderr,
                    )
                    raise SystemExit(1) from exc
                raise

            print(f"Seed cargado en {settings.POSTGRES_DB} ({settings.POSTGRES_HOST}).")
            for tabla in TABLAS:
                cantidad = (
                    await sesion.exec(text(f"SELECT count(*) FROM {tabla}"))
                ).scalar_one()
                print(f"  {tabla:<28} {cantidad}")
            print(f"Contraseña de los usuarios de prueba: {PASSWORD_SEED}")
    finally:
        await motor.dispose()


if __name__ == "__main__":
    asyncio.run(main())
