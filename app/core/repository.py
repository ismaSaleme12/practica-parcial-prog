"""Repositorios base del proyecto.

Reglas duras que este módulo implementa:

- **Ningún repositorio confirma**: ``add``, ``update``, ``delete`` y
  ``soft_delete`` hacen ``flush()`` y nada más. El único punto de confirmación
  es el ``UnitOfWork`` (``app/core/unit_of_work.py``).
- **Ningún repositorio cierra la sesión**: la sesión la abre y la cierra quien
  la creó (la dependencia de sesión de la petición).
- **Sin carga perezosa**: las lecturas que necesiten relaciones las precargan
  los repositorios de cada módulo con ``selectinload``/``joinedload`` y un
  número fijo de consultas.
- **Sin SQL concatenado**: todos los filtros viajan como expresiones ligadas.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import ColumnElement, func, select
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.paginacion import Page, PageParams

ModelT = TypeVar("ModelT", bound=SQLModel)

# Filtros ya armados como expresiones SQLModel/SQLAlchemy (parámetros ligados).
Filtro = ColumnElement[bool]


class BaseRepository(Generic[ModelT]):
    """Acceso a una tabla: lee, pagina y escribe con ``flush()``.

    Recibe la sesión y la **clase del modelo**; nunca crea sesiones ni confirma.
    """

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    # -- filtros compartidos -------------------------------------------------
    def _filtros_base(self) -> tuple[Filtro, ...]:
        """Filtros que toda lectura de este repositorio aplica.

        ``SoftDeleteRepository`` los usa para excluir las filas dadas de baja.
        """
        return ()

    def _filtros(self, filtros: Sequence[Filtro]) -> tuple[Filtro, ...]:
        return (*self._filtros_base(), *filtros)

    # -- lecturas ------------------------------------------------------------
    async def get_by_id(self, id: Any) -> ModelT | None:
        """Devuelve la entidad por clave primaria o ``None`` si no existe."""
        return await self.session.get(self.model, id)

    async def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[ModelT]:
        """Listado simple, sin contar el total (usar ``list_page`` si se pagina)."""
        statement = select(self.model)
        filtros = self._filtros(())
        if filtros:
            statement = statement.where(*filtros)
        statement = statement.offset(skip).limit(limit)
        return (await self.session.exec(statement)).all()

    async def count(self, *filtros: Filtro) -> int:
        """Cuenta con **los mismos filtros** que recibe la página."""
        statement = select(func.count()).select_from(self.model)
        todos = self._filtros(filtros)
        if todos:
            statement = statement.where(*todos)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_page(self, params: PageParams, *filtros: Filtro) -> Page[ModelT]:
        """Página + total con los mismos filtros (2 consultas fijas)."""
        total = await self.count(*filtros)

        statement = select(self.model)
        todos = self._filtros(filtros)
        if todos:
            statement = statement.where(*todos)
        statement = statement.offset(params.offset).limit(params.size)
        items = (await self.session.exec(statement)).all()

        return Page.create(items=items, total=total, params=params)

    # -- escrituras (flush, nunca commit) ------------------------------------
    async def add(self, entity: ModelT) -> ModelT:
        """Agrega y hace ``flush()`` para obtener la PK. No confirma."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: ModelT) -> ModelT:
        """Marca la entidad como modificada y hace ``flush()``. No confirma."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, id: Any) -> bool:
        """Borrado físico. Devuelve ``False`` si la fila no existe. No confirma."""
        entity = await self.get_by_id(id)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True

    async def refresh(self, entity: ModelT) -> ModelT:
        """Recarga la entidad desde la base (solo si hacen falta defaults del motor)."""
        await self.session.refresh(entity)
        return entity


class SoftDeleteRepository(BaseRepository[ModelT], Generic[ModelT]):
    """Repositorio de entidades con borrado lógico.

    Requiere que el modelo tenga la columna ``borrado_en`` (``timestamptz``
    nullable). Las lecturas normales excluyen las filas dadas de baja; las
    bajas se consultan con ``get_by_id_including_deleted``.
    """

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        if not hasattr(model, "borrado_en"):
            raise TypeError(
                f"{model.__name__} no tiene la columna 'borrado_en': "
                "SoftDeleteRepository necesita un modelo con borrado lógico."
            )
        super().__init__(session, model)
        self._columna_borrado = getattr(model, "borrado_en")

    def _filtros_base(self) -> tuple[Filtro, ...]:
        return (self._columna_borrado.is_(None),)

    async def get_by_id(self, id: Any) -> ModelT | None:
        entity = await super().get_by_id(id)
        if entity is not None and getattr(entity, "borrado_en", None) is not None:
            return None
        return entity

    async def get_by_id_including_deleted(self, id: Any) -> ModelT | None:
        """Como ``get_by_id`` pero también devuelve las filas dadas de baja."""
        return await super().get_by_id(id)

    async def soft_delete(self, id: Any) -> ModelT | None:
        """Anota ``borrado_en`` con la hora actual (UTC). No confirma.

        Si la fila no existe o ya estaba dada de baja devuelve ``None`` y no
        toca la marca original.
        """
        entity = await self.get_by_id_including_deleted(id)
        if entity is None or getattr(entity, "borrado_en", None) is not None:
            return None
        entity.borrado_en = datetime.now(timezone.utc)  # type: ignore[attr-defined]
        self.session.add(entity)
        await self.session.flush()
        return entity
