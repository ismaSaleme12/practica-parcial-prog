"""Servicios del módulo de repuestos (Épica 7, US-020 a US-022).

El router arma el UoW con una dependencia y lo pasa **cerrado**; el servicio lo
abre con ``async with`` (regla dura). Ningún repositorio confirma: el commit es
del UoW, y por eso el repuesto y su línea de auditoría se confirman juntos.

Reglas que este módulo implementa:

- **RN-14 — punto único de escritura del stock**: el ``stock`` sólo cambia en el
  alta con ``stock_inicial`` y en la reposición, y en los dos casos se escribe
  el ``movimiento_stock`` correspondiente en el mismo UoW. El PATCH no lo toca
  (``RepuestoPatch`` no declara ``stock``: 422, caso C-16).
- **RN-20 — historial de precios**: un cambio efectivo de precio inserta una
  fila con el anterior, el nuevo, el usuario actual y la hora, en el mismo UoW
  que el cambio. Un PATCH con el mismo precio (o sin precio) **no** deja línea
  (caso C-18).
- **RN-16 — baja lógica**: el DELETE escribe ``borrado_en``; la fila se
  conserva y el código vuelve a quedar libre por el índice único parcial.
- Las dos tablas de auditoría son de **sólo agregado** (RN-15): acá sólo se
  agregan filas; nunca se actualizan ni se borran.
"""

from __future__ import annotations

from app.core.errors import RecursoNoEncontrado
from app.core.paginacion import Page, PageParams
from app.core.schemas import cambios_enviados
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)
from app.modules.repuestos.repository import RepuestoRepository
from app.modules.repuestos.schemas import ReponerStock, RepuestoCrear, RepuestoPatch
from app.modules.repuestos.unit_of_work import RepuestosUnitOfWork

MOTIVO_STOCK_INICIAL = "Stock inicial"
MOTIVO_REPOSICION = "Reposición"


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


async def crear(
    uow: RepuestosUnitOfWork,
    datos: RepuestoCrear,
    usuario_id: int,
) -> Repuesto:
    """Alta con ``stock_inicial`` y su movimiento «Stock inicial» (RN-14).

    El movimiento se escribe **en el mismo UoW** que el repuesto: o quedan los
    dos, o no queda ninguno. Con ``stock_inicial = 0`` no se escribe movimiento
    (no habría entrada que registrar).
    """
    async with uow:
        repuesto = Repuesto(
            codigo=datos.codigo,
            descripcion=datos.descripcion,
            precio=datos.precio,
            stock=datos.stock_inicial,
        )
        await uow.repuestos.add(repuesto)

        if datos.stock_inicial > 0:
            await uow.movimientos.add(
                MovimientoStock(
                    repuesto_id=repuesto.id,
                    usuario_id=usuario_id,
                    cantidad=datos.stock_inicial,
                    motivo=MOTIVO_STOCK_INICIAL,
                )
            )

        return repuesto


async def actualizar(
    uow: RepuestosUnitOfWork,
    repuesto_id: int,
    datos: RepuestoPatch,
    usuario_id: int,
) -> Repuesto:
    """PATCH de descripción y precio, con historial sólo si el precio cambió.

    ``cambios_enviados`` aplica la convención ``exclude_unset``: sólo se escribe
    lo que vino en el cuerpo. Si el precio es idéntico al actual no se inserta
    ninguna línea y la respuesta es 200 igual (RN-20, caso C-18).
    """
    async with uow:
        repuesto = await uow.repuestos.get_by_id(repuesto_id)
        if repuesto is None:
            raise RecursoNoEncontrado("el repuesto", repuesto_id)

        cambios = cambios_enviados(datos)
        if "descripcion" in cambios:
            repuesto.descripcion = cambios["descripcion"]

        precio_nuevo = cambios.get("precio")
        if precio_nuevo is not None and precio_nuevo != repuesto.precio:
            # El anterior se lee ANTES de pisar el atributo.
            precio_anterior = repuesto.precio
            repuesto.precio = precio_nuevo
            await uow.historial_precios.add(
                HistorialPrecioRepuesto(
                    repuesto_id=repuesto.id,
                    usuario_id=usuario_id,
                    precio_anterior=precio_anterior,
                    precio_nuevo=precio_nuevo,
                )
            )

        await uow.repuestos.update(repuesto)
        return repuesto


async def eliminar(uow: RepuestosUnitOfWork, repuesto_id: int) -> None:
    """Baja lógica: escribe ``borrado_en`` sin borrar la fila (RN-16)."""
    async with uow:
        repuesto = await uow.repuestos.soft_delete(repuesto_id)

    if repuesto is None:
        raise RecursoNoEncontrado("el repuesto", repuesto_id)


async def reponer(
    uow: RepuestosUnitOfWork,
    repuesto_id: int,
    datos: ReponerStock,
    usuario_id: int,
) -> Repuesto:
    """Incrementa el stock y deja el movimiento de entrada (RN-14).

    Es el único otro camino de escritura del stock además del alta: el PATCH no
    lo toca. El stock y el movimiento se confirman juntos en el mismo UoW.
    """
    async with uow:
        repuesto = await uow.repuestos.get_by_id(repuesto_id)
        if repuesto is None:
            raise RecursoNoEncontrado("el repuesto", repuesto_id)

        repuesto.stock = repuesto.stock + datos.cantidad
        await uow.repuestos.update(repuesto)
        await uow.movimientos.add(
            MovimientoStock(
                repuesto_id=repuesto.id,
                usuario_id=usuario_id,
                cantidad=datos.cantidad,
                motivo=MOTIVO_REPOSICION,
            )
        )
        return repuesto


async def _exigir_repuesto(uow: RepuestosUnitOfWork, repuesto_id: int) -> None:
    """404 con mensaje propio si el repuesto no existe o está dado de baja."""
    if await uow.repuestos.get_by_id(repuesto_id) is None:
        raise RecursoNoEncontrado("el repuesto", repuesto_id)


async def listar_movimientos(
    uow: RepuestosUnitOfWork,
    repuesto_id: int,
    params: PageParams,
) -> Page[MovimientoStock]:
    """Página de movimientos del repuesto; 404 si el repuesto no existe."""
    async with uow:
        await _exigir_repuesto(uow, repuesto_id)
        return await uow.movimientos.listar_por_repuesto(repuesto_id, params)


async def listar_precios(
    uow: RepuestosUnitOfWork,
    repuesto_id: int,
    params: PageParams,
) -> Page[HistorialPrecioRepuesto]:
    """Página del historial de precios del repuesto; 404 si no existe."""
    async with uow:
        await _exigir_repuesto(uow, repuesto_id)
        return await uow.historial_precios.listar_por_repuesto(repuesto_id, params)
