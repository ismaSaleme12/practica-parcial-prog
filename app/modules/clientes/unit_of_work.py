"""Unit of Work del módulo de clientes (cartera y vehículos).

Hereda el UoW base: confirma al salir sin excepción, revierte con excepción y
**nunca** cierra la sesión (la cierra la petición que la abrió). Sólo declara
sus repositorios, todos sobre la misma sesión: el alta del vehículo y la
consulta del cliente que la valida comparten transacción.
"""

from __future__ import annotations

from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import ClienteRepository, VehiculoRepository


class ClientesUnitOfWork(UnitOfWork):
    """Transacción de negocio del módulo, con sus repositorios tipados."""

    @property
    def clientes(self) -> ClienteRepository:
        return ClienteRepository(self.session)

    @property
    def vehiculos(self) -> VehiculoRepository:
        return VehiculoRepository(self.session)
