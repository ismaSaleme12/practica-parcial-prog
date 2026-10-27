"""Repositorios del módulo de repuestos: catálogo, stock y precios.

``RepuestoRepository`` hereda ``SoftDeleteRepository``: las lecturas excluyen
``borrado_en IS NOT NULL`` y la unicidad del código entre vigentes la garantiza
el índice único parcial de la base, no una consulta previa.

``MovimientoStockRepository`` e ``HistorialPrecioRepository`` son de **sólo
agregado** (RN-15): el repositorio hereda de ``BaseRepository`` y sólo agrega
filas; el disparador de la migración de ``C-04`` rechaza cualquier UPDATE o
DELETE sobre esas tablas, venga de donde venga.

Reglas que este módulo respeta:

- Ningún repositorio confirma: ``add`` hace ``flush()`` y el UoW decide.
- Ninguna consulta se arma por concatenación: ``ILIKE`` recibe el patrón como
  **parámetro ligado** (``descripcion ILIKE $1``). Un ``q`` con comillas viaja
  como valor y no cambia la forma de la sentencia (caso C-16).
- Las páginas de movimientos y precios tienen orden determinista
  (``cuando`` e ``id``), así dos páginas consecutivas no repiten ni omiten filas.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.paginacion import Page, PageParams
from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)


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


class MovimientoStockRepository(BaseRepository[MovimientoStock]):
    """Lectura y alta de ``movimiento_stock`` (sólo agregado, RN-15).

    Es el registro del punto único de escritura del stock (RN-14): el alta con
    stock inicial y la reposición dejan acá su entrada positiva; la terminación
    de una orden deja su salida negativa (``C-11``).
    """

    _orden_por = (MovimientoStock.cuando, MovimientoStock.id)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MovimientoStock)

    async def listar_por_repuesto(
        self, repuesto_id: int, params: PageParams
    ) -> Page[MovimientoStock]:
        """Página de movimientos del repuesto, del más antiguo al más reciente."""
        return await self.list_page(params, MovimientoStock.repuesto_id == repuesto_id)


class HistorialPrecioRepository(BaseRepository[HistorialPrecioRepuesto]):
    """Lectura y alta de ``historial_precio_repuesto`` (sólo agregado, RN-15).

    Cada cambio efectivo del precio deja una fila acá **en el mismo UoW** que el
    cambio (RN-20); un PATCH que no cambia el precio no escribe nada.
    """

    _orden_por = (HistorialPrecioRepuesto.cuando, HistorialPrecioRepuesto.id)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HistorialPrecioRepuesto)

    async def listar_por_repuesto(
        self, repuesto_id: int, params: PageParams
    ) -> Page[HistorialPrecioRepuesto]:
        """Página del historial de precios del repuesto, del más antiguo al más reciente."""
        return await self.list_page(
            params, HistorialPrecioRepuesto.repuesto_id == repuesto_id
        )
