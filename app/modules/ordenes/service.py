"""Servicios del módulo de órdenes de trabajo (Épica 8, US-023 a US-026).

El router arma el UoW con una dependencia y lo pasa **cerrado**; el servicio lo
abre con ``async with`` (regla dura). Ningún repositorio confirma: el commit es
del UoW, y por eso la orden, sus ítems, los movimientos de stock y la línea de
historial se confirman o se revierten juntos (RN-13).

Reglas que este módulo implementa:

- **RN-10 — el precio y el total los pone el servidor**: el contrato sólo acepta
  ``vehiculo_id``, ``falla`` e ``items``; cada ítem copia el precio del repuesto
  y el total se calcula con ``Decimal``. El alta nace ``PENDIENTE`` y deja su
  primera línea de historial.
- **RN-19 — el catálogo manda**: crear exige que ``PENDIENTE`` exista. Un
  catálogo vacío es 409 y no deja ninguna orden. Los estados nunca se escriben
  desde la API.
- **RN-12 / DD-06 — cancelar**: la identidad se evalúa **antes** que el estado.
  Puede cancelar ADMIN, RECEPCION o el dueño de la cuenta del vehículo; un
  tercero recibe 403 aunque la orden tampoco admita la transición (SU-04).
- **RN-13 — terminar es la transacción multi-escritura**: se validan **todos**
  los stock antes de escribir nada; si falta uno, 409 y rollback total. Si
  alcanza, cada ítem descuenta su repuesto y deja **un** movimiento negativo, y
  la orden deja su línea de historial. La identidad también se evalúa antes que
  el estado (SU-04): un mecánico no asignado recibe 403, no 409.
- **RN-15 — historial de sólo agregado**: acá sólo se agregan filas.
- **US-026 / DD-13 — aviso simulado**: ``terminar`` no lo ejecuta; el router lo
  agenda con ``BackgroundTasks`` **después** de que el servicio devuelve (es
  decir, después del commit). Un ``terminar`` rechazado nunca lo agenda.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from fastapi import HTTPException

from app.core.dependencies import MENSAJE_SIN_PERMISO
from app.core.errors import Conflicto, RecursoNoEncontrado
from app.core.paginacion import Page, PageParams
from app.modules.ordenes.models import (
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)
from app.modules.ordenes.repository import OrdenTrabajoRepository
from app.modules.ordenes.schemas import EstadoOrdenCodigo, OrdenCrear
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from app.modules.repuestos.models import MovimientoStock
from app.modules.usuarios.repository import AsignacionRolRepository

logger = logging.getLogger("app.ordenes")

# Códigos del catálogo (DD-01). Son el contrato; la fuente de verdad es la tabla.
ESTADO_PENDIENTE = "PENDIENTE"
ESTADO_EN_REPARACION = "EN_REPARACION"
ESTADO_TERMINADA = "TERMINADA"
ESTADO_CANCELADA = "CANCELADA"

# Roles de la matriz de ``03_actores_y_roles.md``.
ROLES_PERSONAL = frozenset({"ADMIN", "RECEPCION", "MECANICO"})
ROLES_CANCELACION = frozenset({"ADMIN", "RECEPCION"})

MOTIVO_SALIDA = "Salida por orden"

HTTP_403 = 403

MENSAJE_CATALOGO_VACIO = (
    "El catálogo de estados está vacío: no se puede crear una orden."
)
MENSAJE_VEHICULO = "El vehículo indicado no existe o está dado de baja."
MENSAJE_REPUESTO = "Uno de los repuestos indicados no existe o está dado de baja."
MENSAJE_ESTADO = "La orden no admite esa transición de estado."
MENSAJE_STOCK = "No hay stock suficiente para terminar la orden."


def _sin_permiso() -> HTTPException:
    """403 uniforme con el mensaje compartido de autorización."""
    return HTTPException(status_code=HTTP_403, detail=MENSAJE_SIN_PERMISO)


def _orden_no_encontrada(orden_id: int) -> RecursoNoEncontrado:
    return RecursoNoEncontrado("la orden", orden_id)


def _es_dueno(orden: OrdenTrabajo, usuario_id: int) -> bool:
    """¿La cuenta de sesión es la dueña del vehículo de la orden?

    ``get_detalle``/``get_con_dueno`` precargan ``vehiculo.cliente``, así que
    esta comparación no dispara una carga perezosa.
    """
    return orden.vehiculo.cliente.usuario_id == usuario_id


async def _roles(uow: OrdenesUnitOfWork, usuario_id: int) -> frozenset[str]:
    """Roles **vigentes** del usuario, consultados en la base (RN-04)."""
    return frozenset(
        await AsignacionRolRepository(uow.session).roles_vigentes(usuario_id)
    )


async def listar(
    uow: OrdenesUnitOfWork,
    params: PageParams,
    estado: EstadoOrdenCodigo | None = None,
) -> Page[OrdenTrabajo]:
    """Página de órdenes con la patente precargada.

    El filtro ``estado`` llega ya validado contra el enum del contrato: un
    estado no declarado es 422 antes de tocar la base (caso C-17).
    """
    filtros = (OrdenTrabajo.estado == estado.value,) if estado is not None else ()
    async with uow:
        return await uow.ordenes.listar(params, *filtros)


async def obtener(
    uow: OrdenesUnitOfWork,
    orden_id: int,
    usuario_id: int,
) -> OrdenTrabajo:
    """Detalle completo si la sesión es personal del taller o dueña del vehículo.

    Un 404 tiene prioridad sobre el 403: no se confirma la existencia de una
    orden a quien no puede verla, pero el id inexistente tampoco se disfraza de
    «sin permiso».
    """
    async with uow:
        orden = await uow.ordenes.get_detalle(orden_id)
        if orden is None:
            raise _orden_no_encontrada(orden_id)
        if ROLES_PERSONAL.isdisjoint(await _roles(uow, usuario_id)) and not _es_dueno(
            orden, usuario_id
        ):
            raise _sin_permiso()
        return orden


async def crear(
    uow: OrdenesUnitOfWork,
    datos: OrdenCrear,
    usuario_id: int,
) -> OrdenTrabajo:
    """Alta de una orden PENDIENTE con sus ítems, total e historial (RN-10).

    Orden de las verificaciones, antes de escribir cualquier fila:

    1. el catálogo tenga ``PENDIENTE`` (RN-19; catálogo vacío → 409, C-09);
    2. el vehículo exista y no esté dado de baja (RN-16; si no, 409, C-10);
    3. cada repuesto exista y no esté dado de baja (si no, 409, C-10).

    Recién entonces se construyen la orden, sus ítems (con el precio copiado) y
    la primera línea de historial, todos en el mismo UoW.
    """
    async with uow:
        if await uow.estados.get(ESTADO_PENDIENTE) is None:
            raise Conflicto(MENSAJE_CATALOGO_VACIO)

        if await uow.vehiculos.get_by_id(datos.vehiculo_id) is None:
            raise Conflicto(MENSAJE_VEHICULO)

        items: list[ItemOrden] = []
        total = Decimal("0.00")
        for datos_item in datos.items:
            repuesto = await uow.repuestos.get_by_id(datos_item.repuesto_id)
            if repuesto is None:
                raise Conflicto(MENSAJE_REPUESTO)
            items.append(
                ItemOrden(
                    repuesto_id=repuesto.id,
                    cantidad=datos_item.cantidad,
                    precio_unitario=repuesto.precio,
                )
            )
            total += repuesto.precio * datos_item.cantidad

        orden = OrdenTrabajo(
            vehiculo_id=datos.vehiculo_id,
            estado=ESTADO_PENDIENTE,
            falla=datos.falla,
            total=total,
        )
        await uow.ordenes.add(orden)

        for item in items:
            item.orden_id = orden.id
            await uow.items.add(item)

        await uow.historial.add(
            HistorialEstadoOrden(
                orden_id=orden.id,
                desde_estado=None,
                hasta_estado=ESTADO_PENDIENTE,
                usuario_id=usuario_id,
            )
        )

        # Se relee con todas las precargas para devolver el detalle completo sin
        # carga perezosa y con los ids que acaba de asignar el flush.
        detalle = await uow.ordenes.get_detalle(orden.id)
        if detalle is None:  # pragma: no cover - recién insertada en esta transacción
            raise _orden_no_encontrada(orden.id)
        return detalle


async def iniciar(
    uow: OrdenesUnitOfWork,
    orden_id: int,
    usuario_id: int,
) -> OrdenTrabajo:
    """PENDIENTE → EN_REPARACION y asigna el mecánico de la sesión (US-024)."""
    async with uow:
        orden = await uow.ordenes.get_con_vehiculo(orden_id)
        if orden is None:
            raise _orden_no_encontrada(orden_id)
        if orden.estado != ESTADO_PENDIENTE:
            raise Conflicto(MENSAJE_ESTADO)

        orden.estado = ESTADO_EN_REPARACION
        orden.mecanico_id = usuario_id
        await uow.ordenes.update(orden)
        await uow.historial.add(
            HistorialEstadoOrden(
                orden_id=orden.id,
                desde_estado=ESTADO_PENDIENTE,
                hasta_estado=ESTADO_EN_REPARACION,
                usuario_id=usuario_id,
            )
        )
        return orden


async def terminar(
    uow: OrdenesUnitOfWork,
    orden_id: int,
    usuario_id: int,
) -> OrdenTrabajo:
    """EN_REPARACION → TERMINADA descontando el stock en un solo UoW (RN-13).

    El orden de las verificaciones es parte del contrato:

    1. 404 si la orden no existe;
    2. **403 si la sesión no es el mecánico asignado ni ADMIN** (SU-04): la
       identidad se evalúa antes que el estado;
    3. 409 si la orden no está EN_REPARACION;
    4. 409 si a **algún** repuesto le falta stock, sin haber escrito nada;
    5. recién entonces: un ``movimiento_stock`` negativo por ítem, el stock
       descontado y la línea de historial, en la misma transacción.

    El aviso al cliente no se ejecuta acá: lo agenda el router después de que
    este servicio devuelve (DD-13).
    """
    async with uow:
        orden = await uow.ordenes.get_con_items(orden_id)
        if orden is None:
            raise _orden_no_encontrada(orden_id)

        if "ADMIN" not in await _roles(uow, usuario_id):
            if orden.mecanico_id != usuario_id:
                raise _sin_permiso()

        if orden.estado != ESTADO_EN_REPARACION:
            raise Conflicto(MENSAJE_ESTADO)

        # Se valida el stock de TODOS los ítems antes de escribir el primero:
        # así un faltante no deja media orden descontada (caso C-11).
        if any(item.repuesto.stock < item.cantidad for item in orden.items):
            raise Conflicto(MENSAJE_STOCK)

        for item in orden.items:
            repuesto = item.repuesto
            repuesto.stock = repuesto.stock - item.cantidad
            await uow.repuestos.update(repuesto)
            await uow.movimientos.add(
                MovimientoStock(
                    repuesto_id=repuesto.id,
                    orden_id=orden.id,
                    usuario_id=usuario_id,
                    cantidad=-item.cantidad,
                    motivo=f"{MOTIVO_SALIDA} {orden.id}",
                )
            )

        orden.estado = ESTADO_TERMINADA
        await uow.ordenes.update(orden)
        await uow.historial.add(
            HistorialEstadoOrden(
                orden_id=orden.id,
                desde_estado=ESTADO_EN_REPARACION,
                hasta_estado=ESTADO_TERMINADA,
                usuario_id=usuario_id,
            )
        )
        return orden


async def cancelar(
    uow: OrdenesUnitOfWork,
    orden_id: int,
    usuario_id: int,
) -> OrdenTrabajo:
    """PENDIENTE → CANCELADA si la sesión es ADMIN/RECEPCION o dueña (RN-12).

    La ruta **no** lleva ``requiere_rol`` (DD-06): el servicio decide. La
    identidad va primero: un cliente ajeno recibe 403 aunque la orden esté
    TERMINADA y tampoco se pueda cancelar (SU-04).
    """
    async with uow:
        orden = await uow.ordenes.get_con_dueno(orden_id)
        if orden is None:
            raise _orden_no_encontrada(orden_id)

        puede = not ROLES_CANCELACION.isdisjoint(
            await _roles(uow, usuario_id)
        ) or _es_dueno(orden, usuario_id)
        if not puede:
            raise _sin_permiso()

        if orden.estado != ESTADO_PENDIENTE:
            raise Conflicto(MENSAJE_ESTADO)

        orden.estado = ESTADO_CANCELADA
        await uow.ordenes.update(orden)
        await uow.historial.add(
            HistorialEstadoOrden(
                orden_id=orden.id,
                desde_estado=ESTADO_PENDIENTE,
                hasta_estado=ESTADO_CANCELADA,
                usuario_id=usuario_id,
            )
        )
        return orden


async def listar_estados(uow: OrdenesUnitOfWork):
    """Catálogo completo por ``posicion`` (sólo lectura, DD-07)."""
    async with uow:
        return list(await uow.estados.listar())


async def listar_mis_ordenes(
    uow: OrdenesUnitOfWork,
    params: PageParams,
    usuario_id: int,
) -> Page[OrdenTrabajo]:
    """Órdenes de los vehículos vigentes del cliente dueño de la sesión (RN-17).

    Sin ficha de cliente no es un error: la respuesta es una página vacía, igual
    que ``/mis-vehiculos``.
    """
    async with uow:
        ficha = await uow.clientes.get_by_usuario_id(usuario_id)
        if ficha is None or not ficha.vehiculos:
            return Page.create(items=[], total=0, params=params)

        vehiculos = [vehiculo.id for vehiculo in ficha.vehiculos]
        return await uow.ordenes.listar(
            params, OrdenTrabajo.vehiculo_id.in_(vehiculos)
        )


async def avisar_cliente(orden_id: int) -> None:
    """Aviso simulado de «orden terminada» (US-026 / DD-13).

    Lo agenda el router con ``BackgroundTasks`` **después** del commit. Es un
    ``sleep`` de 0.5 s y un log: no hay integración externa en el alcance.
    """
    await asyncio.sleep(0.5)
    logger.info(
        "Aviso simulado al cliente: la orden %s está terminada.", orden_id
    )
