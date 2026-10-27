"""Repositorio de repuestos: borrado lógico y búsqueda con parámetros ligados.

Hereda ``SoftDeleteRepository``: las lecturas excluyen ``borrado_en IS NOT NULL``
y la unicidad del código entre vigentes la garantiza el índice único parcial de
la base, no una consulta previa.

Reglas que este módulo respeta:

- Ningún repositorio confirma: ``add`` hace ``flush()`` y el UoW decide.
- Ninguna consulta se arma por concatenación: ``ILIKE`` recibe el patrón como
  **parámetro ligado** (``descripcion ILIKE $1``). Un ``q`` con comillas viaja
  como valor y no cambia la forma de la sentencia (caso C-16).
"""

from __future__ import annotations

from sqlalchemy import ColumnElement
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.repository import SoftDeleteRepository
from app.modules.repuestos.models import Repuesto


class RepuestoRepository(SoftDeleteRepository[Repuesto]):
    """Acceso a ``repuesto`` con búsqueda parcial por descripción."""

    # Orden determinista de las páginas (mismo criterio que el ejemplo de la KB).
    _orden_por = (Repuesto.id,)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Repuesto)

    @staticmethod
    def filtro_busqueda(q: str | None) -> tuple[ColumnElement[bool], ...]:
        """Filtro de búsqueda por descripción, como expresión SQLModel ligada.

        Se devuelve una tupla para que ``count`` y la página reciban **los
        mismos filtros** (requisito del envoltorio de paginación).
        """
        texto = (q or "").strip()
        if not texto:
            return ()
        # El patrón viaja como parámetro: SQLAlchemy compila ILIKE con un bind.
        return (Repuesto.descripcion.ilike(f"%{texto}%"),)
