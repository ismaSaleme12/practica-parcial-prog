"""Unit of Work del módulo de repuestos.

Hereda el UoW base: confirma al salir sin excepción, revierte con excepción y
**nunca** cierra la sesión (la cierra la petición que la abrió). Sólo declara
sus repositorios, todos sobre la misma sesión: el catálogo y las dos tablas de
sólo agregado.

Que las tres compartan la sesión es lo que hace posible RN-20 y RN-14: el alta
con stock inicial, la reposición, el cambio de precio y su línea de historial
se confirman o se revierten juntos.
"""

from __future__ import annotations

from app.core.unit_of_work import UnitOfWork
from app.modules.repuestos.repository import (
    HistorialPrecioRepository,
    MovimientoStockRepository,
    RepuestoRepository,
)


class RepuestosUnitOfWork(UnitOfWork):
    """Transacción de negocio del módulo, con sus repositorios tipados."""

    @property
    def repuestos(self) -> RepuestoRepository:
        return RepuestoRepository(self.session)

    @property
    def movimientos(self) -> MovimientoStockRepository:
        return MovimientoStockRepository(self.session)

    @property
    def historial_precios(self) -> HistorialPrecioRepository:
        return HistorialPrecioRepository(self.session)
