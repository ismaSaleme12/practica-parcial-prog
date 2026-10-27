"""Router del módulo de repuestos (prototipo de contratos de `C-06`).

Endpoints:

- ``GET /repuestos``: listado paginado con el envoltorio uniforme y búsqueda
  ``q`` parametrizada.
- ``GET /repuestos/{id}``: 200/404.
- ``POST /repuestos``: 201 con stock 0.

**Provisional**: todavía no hay autenticación. `C-08` mueve este router al grupo
protegido y agrega ``requiere_rol`` (ADMIN/RECEPCION/MECANICO para leer, ADMIN
para escribir); `C-10` completa el ABM.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import SessionDep
from app.core.paginacion import Page, PageParamsDep
from app.modules.repuestos import service
from app.modules.repuestos.schemas import RepuestoCrear, RepuestoLeer
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
async def obtener_repuesto(uow: UoWDep, repuesto_id: int) -> RepuestoLeer:
    repuesto = await service.obtener(uow, repuesto_id)
    return RepuestoLeer.model_validate(repuesto)


@router.post(
    "",
    response_model=RepuestoLeer,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de repuesto (stock inicial 0)",
)
async def crear_repuesto(uow: UoWDep, datos: RepuestoCrear) -> RepuestoLeer:
    repuesto = await service.crear(uow, datos)
    return RepuestoLeer.model_validate(repuesto)
