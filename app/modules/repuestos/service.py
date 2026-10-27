"""Servicios del módulo de repuestos (prototipo de contratos de `C-06`).

El router arma el UoW con una dependencia y lo pasa **cerrado**; el servicio lo
abre con ``async with`` (regla dura). Ningún repositorio confirma.

Alcance de este change: listado paginado con búsqueda ``q``, detalle y alta con
stock 0. El alta con ``stock_inicial`` + movimiento «Stock inicial», el PATCH
con historial de precio y la baja lógica llegan en `C-10` (necesitan el usuario
actual que agregan `C-07`/`C-08`).
"""

from __future__ import annotations

from app.core.errors import RecursoNoEncontrado
from app.core.paginacion import Page, PageParams
from app.modules.repuestos.models import Repuesto
from app.modules.repuestos.repository import RepuestoRepository
from app.modules.repuestos.schemas import RepuestoCrear
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork


async def listar(
    uow: RepuestosUnitOfWork,
    params: PageParams,
    q: str | None = None,
) -> Page[Repuesto]:
    """Página de repuestos vigentes; ``total`` usa los mismos filtros que la página."""
    async with uow:
        filtros = RepuestoRepository.filtro_busqueda(q)
        return await uow.repuestos.list_page(params, *filtros)


async def obtener(uow: RepuestosUnitOfWork, repuesto_id: int) -> Repuesto:
    """Repuesto vigente por id o 404 con mensaje propio."""
    async with uow:
        repuesto = await uow.repuestos.get_by_id(repuesto_id)

    if repuesto is None:
        raise RecursoNoEncontrado("el repuesto", repuesto_id)
    return repuesto


async def crear(uow: RepuestosUnitOfWork, datos: RepuestoCrear) -> Repuesto:
    """Alta de repuesto con stock 0 (el stock sólo cambia por movimientos)."""
    repuesto = Repuesto(**datos.model_dump())

    async with uow:
        return await uow.repuestos.add(repuesto)
