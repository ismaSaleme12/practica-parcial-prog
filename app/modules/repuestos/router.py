"""Router del módulo de repuestos (Épica 7, US-020 a US-022).

Endpoints (grupo **protegido** de ``main.py``):

- ``GET /repuestos``: listado paginado con el envoltorio uniforme y búsqueda
  ``q`` parametrizada — ADMIN, RECEPCION y MECANICO.
- ``GET /repuestos/{id}``: 200/404 — ADMIN, RECEPCION y MECANICO.
- ``POST /repuestos``: 201 con ``stock_inicial`` (y su movimiento) — sólo ADMIN.
- ``PATCH /repuestos/{id}``: 200/404/422, sólo ``descripcion`` y ``precio``
  (``stock`` en el cuerpo → 422, caso C-16) — sólo ADMIN.
- ``DELETE /repuestos/{id}``: 204 con baja lógica — sólo ADMIN.
- ``POST /repuestos/{id}/reponer``: 200 con el repuesto actualizado y su
  movimiento de entrada — sólo ADMIN.
- ``GET /repuestos/{id}/movimientos`` y ``GET /repuestos/{id}/precios``:
  200 paginado / 404 — sólo ADMIN.

Los permisos salen de la matriz de ``03_actores_y_roles.md``, no de una
invención local. ``requiere_rol`` consulta los roles vigentes en la base en
cada petición (RN-04); el grupo protegido aporta el 401 y el 403 del cambio
obligatorio (DD-05).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import AdminDep, PersonalDep, SessionDep, UsuarioActual
from app.core.paginacion import Page, PageParamsDep
from app.modules.repuestos import service
from app.modules.repuestos.schemas import (
    HistorialPrecioLeer,
    MovimientoStockLeer,
    ReponerStock,
    RepuestoCrear,
    RepuestoLeer,
    RepuestoPatch,
)
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork

router = APIRouter(prefix="/repuestos", tags=["Repuestos"])


async def get_uow(session: AsyncSession = SessionDep) -> RepuestosUnitOfWork:
    """Arma el UoW del módulo con la sesión de la petición, sin abrirlo."""
    return RepuestosUnitOfWork(session)


UoWDep = Annotated[RepuestosUnitOfWork, Depends(get_uow)]
BusquedaDep = Annotated[
    str | None,
    Query(
        max_length=200,
        description="Texto a buscar en la descripción del repuesto.",
    ),
]


@router.get(
    "",
    response_model=Page[RepuestoLeer],
    status_code=status.HTTP_200_OK,
    summary="Listado paginado de repuestos vigentes",
)
async def listar_repuestos(
    uow: UoWDep,
    params: PageParamsDep,
    actual: UsuarioActual = PersonalDep,
    q: BusquedaDep = None,
) -> Page[RepuestoLeer]:
    pagina = await service.listar(uow, params, q)
    # El mapeo ORM → contrato es explícito: el modelo de tabla nunca sale tal cual.
    return Page[RepuestoLeer](
        items=[RepuestoLeer.model_validate(item) for item in pagina.items],
        total=pagina.total,
        page=pagina.page,
        size=pagina.size,
        pages=pagina.pages,
    )


@router.get(
    "/{repuesto_id}",
    response_model=RepuestoLeer,
    status_code=status.HTTP_200_OK,
    summary="Detalle de un repuesto vigente",
)
async def obtener_repuesto(
    uow: UoWDep,
    repuesto_id: int,
    actual: UsuarioActual = PersonalDep,
) -> RepuestoLeer:
    repuesto = await service.obtener(uow, repuesto_id)
    return RepuestoLeer.model_validate(repuesto)


@router.post(
    "",
    response_model=RepuestoLeer,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de repuesto con stock inicial",
)
async def crear_repuesto(
    uow: UoWDep,
    datos: RepuestoCrear,
    actual: UsuarioActual = AdminDep,
) -> RepuestoLeer:
    repuesto = await service.crear(uow, datos, usuario_id=actual.usuario.id)
    return RepuestoLeer.model_validate(repuesto)


@router.patch(
    "/{repuesto_id}",
    response_model=RepuestoLeer,
    status_code=status.HTTP_200_OK,
    summary="Edición de descripción y precio, con historial de precio",
)
async def actualizar_repuesto(
    uow: UoWDep,
    repuesto_id: int,
    datos: RepuestoPatch,
    actual: UsuarioActual = AdminDep,
) -> RepuestoLeer:
    repuesto = await service.actualizar(
        uow, repuesto_id, datos, usuario_id=actual.usuario.id
    )
    return RepuestoLeer.model_validate(repuesto)


@router.delete(
    "/{repuesto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Baja lógica de un repuesto",
)
async def eliminar_repuesto(
    uow: UoWDep,
    repuesto_id: int,
    actual: UsuarioActual = AdminDep,
) -> Response:
    await service.eliminar(uow, repuesto_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{repuesto_id}/reponer",
    response_model=RepuestoLeer,
    status_code=status.HTTP_200_OK,
    summary="Reposición de stock (punto único de escritura, RN-14)",
)
async def reponer_stock(
    uow: UoWDep,
    repuesto_id: int,
    datos: ReponerStock,
    actual: UsuarioActual = AdminDep,
) -> RepuestoLeer:
    repuesto = await service.reponer(
        uow, repuesto_id, datos, usuario_id=actual.usuario.id
    )
    return RepuestoLeer.model_validate(repuesto)


@router.get(
    "/{repuesto_id}/movimientos",
    response_model=Page[MovimientoStockLeer],
    status_code=status.HTTP_200_OK,
    summary="Historial de movimientos de stock del repuesto",
)
async def listar_movimientos(
    uow: UoWDep,
    repuesto_id: int,
    params: PageParamsDep,
    actual: UsuarioActual = AdminDep,
) -> Page[MovimientoStockLeer]:
    pagina = await service.listar_movimientos(uow, repuesto_id, params)
    return Page[MovimientoStockLeer](
        items=[MovimientoStockLeer.model_validate(item) for item in pagina.items],
        total=pagina.total,
        page=pagina.page,
        size=pagina.size,
        pages=pagina.pages,
    )


@router.get(
    "/{repuesto_id}/precios",
    response_model=Page[HistorialPrecioLeer],
    status_code=status.HTTP_200_OK,
    summary="Historial de cambios de precio del repuesto",
)
async def listar_precios(
    uow: UoWDep,
    repuesto_id: int,
    params: PageParamsDep,
    actual: UsuarioActual = AdminDep,
) -> Page[HistorialPrecioLeer]:
    pagina = await service.listar_precios(uow, repuesto_id, params)
    return Page[HistorialPrecioLeer](
        items=[HistorialPrecioLeer.model_validate(item) for item in pagina.items],
        total=pagina.total,
        page=pagina.page,
        size=pagina.size,
        pages=pagina.pages,
    )
