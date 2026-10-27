"""Unit of Work del módulo de usuarios.

Hereda el UoW base (confirma al salir sin excepción, revierte con excepción y no
cierra la sesión) y sólo declara sus repositorios sobre la sesión compartida.

El auto-registro (`C-07`) compone además el repositorio de ``clientes``: la
ficha del cliente es una de las tres filas que RN-02 exige en **el mismo** UoW.
"""

from __future__ import annotations

from app.core.unit_of_work import UnitOfWork
from app.modules.clientes.repository import ClienteRepository
from app.modules.usuarios.repository import (
    AsignacionRolRepository,
    EventoSeguridadRepository,
    IntentoAccesoRepository,
    UsuarioRepository,
)


class UsuariosUnitOfWork(UnitOfWork):
    """Transacción de negocio del módulo de identidad."""

    @property
    def usuarios(self) -> UsuarioRepository:
        return UsuarioRepository(self.session)

    @property
    def roles(self) -> AsignacionRolRepository:
        return AsignacionRolRepository(self.session)

    @property
    def intentos(self) -> IntentoAccesoRepository:
        return IntentoAccesoRepository(self.session)

    @property
    def eventos(self) -> EventoSeguridadRepository:
        return EventoSeguridadRepository(self.session)

    @property
    def clientes(self) -> ClienteRepository:
        return ClienteRepository(self.session)
