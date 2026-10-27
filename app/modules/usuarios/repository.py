"""Repositorio de usuarios.

Hereda ``BaseRepository``: ``add`` hace ``flush()`` y nada más (el UoW es el
único punto de confirmación). La unicidad del email la garantiza el UNIQUE de la
base: no hay consulta previa, el choque se traduce a 409 en `app/core/errors.py`.
"""

from __future__ import annotations

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.repository import BaseRepository
from app.modules.usuarios.models import Usuario


class UsuarioRepository(BaseRepository[Usuario]):
    """Acceso a la tabla ``usuario``."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Usuario)
