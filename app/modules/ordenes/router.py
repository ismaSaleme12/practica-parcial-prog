"""Router del módulo de órdenes de trabajo (Épica 8, US-023 a US-026).

Tres routers, todos en el grupo **protegido** de ``main.py`` (que aporta el 401
de la sesión y el 403 del cambio obligatorio, montados una sola vez):

- ``router`` (``/ordenes``):
  - ``GET /ordenes`` — ADMIN, RECEPCION y MECANICO; filtro ``estado`` validado
    contra el enum del contrato (no declarado → 422, C-17).
  - ``GET /ordenes/{id}`` — personal del taller o dueño del vehículo (ajeno →
    403, C-06); 404 si no existe.
  - ``POST /ordenes`` — ADMIN, RECEPCION → 201 con total, ítems e historial.
  - ``POST /ordenes/{id}/iniciar`` — MECANICO → 200.
  - ``POST /ordenes/{id}/terminar`` — ADMIN o mecánico asignado; **403 de
    identidad antes que 409 de estado** (SU-04) → 200 y aviso simulado agendado
    después del commit (DD-13).
  - ``POST /ordenes/{id}/cancelar`` — ADMIN, RECEPCION o dueño, **sin**
    ``requiere_rol`` (DD-06); el servicio decide identidad antes que estado.
- ``estados_router`` (``/estados-orden``): catálogo por posición para cualquier
  sesión válida.
- ``propios_router`` (``/mis-ordenes``): órdenes de los vehículos del cliente
  dueño de la sesión (RN-17), para cualquier sesión válida.

El mapeo ORM → contrato es explícito: el detalle arma los ítems con su subtotal
y ordena el historial, sin que ningún modelo de tabla salga tal cual.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import (
    PersonalDep,
    SessionDep,
    UsuarioActual,
    UsuarioActualDep,
    requiere_rol,
)
from app.core.paginacion import Page, PageParamsDep
from app.modules.ordenes import service
from app.modules.ordenes.models import OrdenTrabajo
from app.modules.ordenes.schemas import (
    EstadoOrdenCodigo,
    EstadoOrdenLeer,
    HistorialEstadoLeer,
    ItemOrdenLeer,
    OrdenCrear,
    OrdenDetalle,
    OrdenResumen,
)
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork

router = APIRouter(prefix="/ordenes", tags=["Órdenes"])
estados_router = APIRouter(prefix="/estados-orden", tags=["Órdenes"])
# ``/mis-ordenes`` no comparte prefijo con los otros dos: es el router de «lo
# propio» (RN-17) y no lleva ``requiere_rol``, sólo sesión válida.
propios_router = APIRouter(tags=["Órdenes"])

# La matriz de ``03_actores_y_roles.md`` concede el alta a ADMIN y RECEPCION;
# iniciar sólo a MECANICO; terminar a ADMIN y MECANICO (el servicio distingue
# después si es el asignado). Cancelar no lleva ``requiere_rol`` (DD-06).
AtencionDep = Depends(requiere_rol("ADMIN", "RECEPCION"))
MecanicoDep = Depends(requiere_rol("MECANICO"))
TallerDep = Depends(requiere_rol("ADMIN", "MECANICO"))

EstadoQuery = Annotated[
    EstadoOrdenCodigo | None,
    Query(description="Filtra por un estado declarado del catálogo."),
]


async def get_uow(session: AsyncSession = SessionDep) -> OrdenesUnitOfWork:
    """Arma el UoW del módulo con la sesión de la petición, sin abrirlo."""
    return OrdenesUnitOfWork(session)


UoWDep = Annotated[OrdenesUnitOfWork, Depends(get_uow)]


def _resumen(orden: OrdenTrabajo) -> OrdenResumen:
    """Fila liviana: la patente viene del vehículo precargado (sin lazy)."""
    return OrdenResumen(
        id=orden.id,
        vehiculo_id=orden.vehiculo_id,
        patente=orden.vehiculo.patente,
        estado=orden.estado,
        falla=orden.falla,
        creada_en=orden.creada_en,
        total=orden.total,
        mecanico_id=orden.mecanico_id,
    )


def _detalle(orden: OrdenTrabajo) -> OrdenDetalle:
    """Detalle completo: ítems con subtotal e historial en orden cronológico."""
    items = [
        ItemOrdenLeer(
            repuesto_id=item.repuesto_id,
            codigo=item.repuesto.codigo,
            descripcion=item.repuesto.descripcion,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            subtotal=item.precio_unitario * item.cantidad,
        )
        for item in sorted(orden.items, key=lambda item: item.id or 0)
    ]
    historial = [
        HistorialEstadoLeer.model_validate(linea)
        for linea in sorted(
            orden.historial_estados,
            key=lambda linea: (linea.cuando, linea.id or 0),
        )
    ]
    return OrdenDetalle(
        id=orden.id,
        vehiculo_id=orden.vehiculo_id,
        patente=orden.vehiculo.patente,
        estado=orden.estado,
        falla=orden.falla,
        creada_en=orden.creada_en,
        total=orden.total,
        mecanico_id=orden.mecanico_id,
        cliente=orden.vehiculo.cliente.nombre,
        items=items,
        historial=historial,
    )


def _pagina(pagina: Page[OrdenTrabajo]) -> Page[OrdenResumen]:
    return Page[OrdenResumen](
        items=[_resumen(orden) for orden in pagina.items],
        total=pagina.total,
        page=pagina.page,
        size=pagina.size,
        pages=pagina.pages,
    )


@router.get(
    "",
    response_model=Page[OrdenResumen],
    status_code=status.HTTP_200_OK,
    summary="Listado paginado de órdenes (ADMIN, RECEPCION, MECANICO)",
)
async def listar_ordenes(
    uow: UoWDep,
    params: PageParamsDep,
    actual: UsuarioActual = PersonalDep,
    estado: EstadoQuery = None,
) -> Page[OrdenResumen]:
    pagina = await service.listar(uow, params, estado)
    return _pagina(pagina)


@router.get(
    "/{orden_id}",
    response_model=OrdenDetalle,
    status_code=status.HTTP_200_OK,
    summary="Detalle de una orden (personal o dueño del vehículo)",
)
async def obtener_orden(
    uow: UoWDep,
    orden_id: int,
    actual: UsuarioActual = UsuarioActualDep,
) -> OrdenDetalle:
    orden = await service.obtener(uow, orden_id, actual.usuario.id)
    return _detalle(orden)


@router.post(
    "",
    response_model=OrdenDetalle,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de una orden PENDIENTE (ADMIN, RECEPCION)",
)
async def crear_orden(
    uow: UoWDep,
    datos: OrdenCrear,
    actual: UsuarioActual = AtencionDep,
) -> OrdenDetalle:
    orden = await service.crear(uow, datos, actual.usuario.id)
    return _detalle(orden)


@router.post(
    "/{orden_id}/iniciar",
    response_model=OrdenResumen,
    status_code=status.HTTP_200_OK,
    summary="Inicia una orden y asigna el mecánico de la sesión (MECANICO)",
)
async def iniciar_orden(
    uow: UoWDep,
    orden_id: int,
    actual: UsuarioActual = MecanicoDep,
) -> OrdenResumen:
    orden = await service.iniciar(uow, orden_id, actual.usuario.id)
    return _resumen(orden)


@router.post(
    "/{orden_id}/terminar",
    response_model=OrdenResumen,
    status_code=status.HTTP_200_OK,
    summary="Termina una orden, descuenta stock y avisa al cliente",
)
async def terminar_orden(
    uow: UoWDep,
    orden_id: int,
    background_tasks: BackgroundTasks,
    actual: UsuarioActual = TallerDep,
) -> OrdenResumen:
    # El servicio confirma (o revierte) al salir del ``async with``. Recién
    # cuando devuelve, el aviso se agenda: un 403/404/409 no llega hasta acá
    # (US-026 / DD-13).
    orden = await service.terminar(uow, orden_id, actual.usuario.id)
    background_tasks.add_task(service.avisar_cliente, orden.id)
    return _resumen(orden)


@router.post(
    "/{orden_id}/cancelar",
    response_model=OrdenResumen,
    status_code=status.HTTP_200_OK,
    summary="Cancela una orden PENDIENTE (ADMIN, RECEPCION o dueño)",
)
async def cancelar_orden(
    uow: UoWDep,
    orden_id: int,
    actual: UsuarioActual = UsuarioActualDep,
) -> OrdenResumen:
    orden = await service.cancelar(uow, orden_id, actual.usuario.id)
    return _resumen(orden)


@estados_router.get(
    "",
    response_model=list[EstadoOrdenLeer],
    status_code=status.HTTP_200_OK,
    summary="Catálogo de estados por posición (cualquier sesión)",
)
async def listar_estados(
    uow: UoWDep,
    actual: UsuarioActual = UsuarioActualDep,
) -> list[EstadoOrdenLeer]:
    estados = await service.listar_estados(uow)
    return [EstadoOrdenLeer.model_validate(estado) for estado in estados]


@propios_router.get(
    "/mis-ordenes",
    response_model=Page[OrdenResumen],
    status_code=status.HTTP_200_OK,
    summary="Órdenes de los vehículos del cliente de la sesión (cualquier rol)",
)
async def listar_mis_ordenes(
    uow: UoWDep,
    params: PageParamsDep,
    actual: UsuarioActual = UsuarioActualDep,
) -> Page[OrdenResumen]:
    pagina = await service.listar_mis_ordenes(uow, params, actual.usuario.id)
    return _pagina(pagina)
