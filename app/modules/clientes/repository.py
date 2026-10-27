"""Repositorio de clientes.

Hereda ``BaseRepository``: ``add`` hace ``flush()`` y nada más (el UoW es el
único punto de confirmación). La unicidad de ``documento`` y de ``usuario_id``
la garantiza la base: no hay consulta previa, el choque se traduce a 409 en
``app/core/errors.py``.

``C-07`` lo compone desde el UoW de ``usuarios`` para crear la ficha en el mismo
UoW que el usuario y su rol (RN-02). ``C-09`` extiende este módulo con las
consultas de la cartera (vehículos y borrado lógico).
"""

from __future__ import annotations

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.repository import BaseRepository
from app.modules.clientes.models import Cliente


class ClienteRepository(BaseRepository[Cliente]):
    """Acceso a la tabla ``cliente``."""

    _orden_por = (Cliente.id,)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Cliente)
