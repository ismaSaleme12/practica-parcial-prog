"""Unit of Work del módulo de repuestos.

Hereda el UoW base: confirma al salir sin excepción, revierte con excepción y
**nunca** cierra la sesión (la cierra la petición que la abrió). Sólo declara
sus repositorios, todos sobre la misma sesión.
"""

from __future__ import annotations

from app.core.unit_of_work import UnitOfWork
from app.modules.repuestos.repository import RepuestoRepository


class RepuestosUnitOfWork(UnitOfWork):
    """Transacción de negocio del módulo, con sus repositorios tipados."""

    @property
    def repuestos(self) -> RepuestoRepository:
        return RepuestoRepository(self.session)
