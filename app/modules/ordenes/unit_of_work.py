"""Unit of Work del módulo de órdenes de trabajo.

Hereda el UoW base: confirma al salir sin excepción, revierte con excepción y
**nunca** cierra la sesión (la cierra la petición que la abrió). Sólo declara
sus repositorios, todos sobre la misma sesión.

Que todos compartan la sesión es lo que hace posible la transacción
multi-escritura del TP (RN-13): la orden, sus ítems, los movimientos de stock y
la línea de historial se confirman o se revierten juntos. El catálogo de
estados se lee con un repositorio propio de sólo lectura (DD-07) y los
vehículos, clientes, repuestos y movimientos reutilizan los repositorios de sus
módulos en vez de duplicarlos.
"""

from __future__ import annotations

from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import ClienteRepository, VehiculoRepository
from app.modules.ordenes.repository import (
    EstadoOrdenRepository,
    HistorialEstadoOrdenRepository,
    ItemOrdenRepository,
    OrdenTrabajoRepository,
)
from app.modules.repuestos.repository import (
    MovimientoStockRepository,
    RepuestoRepository,
)


class OrdenesUnitOfWork(UnitOfWork):
    """Transacción de negocio del módulo, con sus repositorios tipados."""

    @property
    def ordenes(self) -> OrdenTrabajoRepository:
        return OrdenTrabajoRepository(self.session)

    @property
    def items(self) -> ItemOrdenRepository:
        return ItemOrdenRepository(self.session)

    @property
    def historial(self) -> HistorialEstadoOrdenRepository:
        return HistorialEstadoOrdenRepository(self.session)

    @property
    def estados(self) -> EstadoOrdenRepository:
        return EstadoOrdenRepository(self.session)

    @property
    def clientes(self) -> ClienteRepository:
        return ClienteRepository(self.session)

    @property
    def vehiculos(self) -> VehiculoRepository:
        return VehiculoRepository(self.session)

    @property
    def repuestos(self) -> RepuestoRepository:
        return RepuestoRepository(self.session)

    @property
    def movimientos(self) -> MovimientoStockRepository:
        return MovimientoStockRepository(self.session)
