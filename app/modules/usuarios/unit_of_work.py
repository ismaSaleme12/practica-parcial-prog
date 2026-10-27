"""Unit of Work del módulo de usuarios.

Hereda el UoW base (confirma al salir sin excepción, revierte con excepción y no
cierra la sesión) y sólo declara sus repositorios sobre la sesión compartida.
`C-07`/`C-08` agregan los de roles, intentos de acceso y eventos.
"""

from __future__ import annotations

from app.core.unit_of_work import UnitOfWork
from app.modules.usuarios.repository import UsuarioRepository


class UsuariosUnitOfWork(UnitOfWork):
    """Transacción de negocio del módulo de identidad."""

    @property
    def usuarios(self) -> UsuarioRepository:
        return UsuarioRepository(self.session)
