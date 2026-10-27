"""Repositorios del módulo de órdenes de trabajo.

Reglas que este módulo respeta:

- **Ningún repositorio confirma**: ``add``/``update`` hacen ``flush()`` y el
  Unit of Work decide. Es lo que hace posible que la orden, sus ítems, los
  movimientos de stock y el historial se confirmen o se reviertan juntos
  (RN-13).
- **Sin carga perezosa**: todas las relaciones del esquema declaran
  ``lazy="raise_on_sql"``. El detalle precarga vehículo y cliente, ítems con su
  repuesto e historial con ``joinedload``/``selectinload`` en un número fijo de
  consultas; los listados precargan sólo el vehículo que necesitan para la
  patente.
- **``select`` de SQLModel**: con ``session.exec`` devuelve entidades y no
  ``Row`` (regla dura del proyecto).
- ``estado_orden`` tiene un repositorio **propio de sólo lectura** que no hereda
  de ``BaseRepository`` (DD-07): su clave primaria no es ``id`` y desde la API
  no se escribe, así que no debe ofrecer ``add``/``update``/``delete``.
- ``HistorialEstadoOrdenRepository`` es de **sólo agregado** (RN-15): el
  servicio sólo agrega filas y el disparador de la base rechaza UPDATE/DELETE.
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.paginacion import Page, PageParams
from app.core.repository import BaseRepository
from app.modules.clientes.models import Vehiculo
from app.modules.ordenes.models import (
    EstadoOrden,
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)


class OrdenTrabajoRepository(BaseRepository[OrdenTrabajo]):
    """Acceso a ``orden_trabajo`` con las precargas que cada lectura necesita."""

    # Orden determinista de los listados: la más reciente primero y, ante dos
    # marcas iguales (el reloj del sistema puede repetirlas), el id mayor.
    _orden_por = (OrdenTrabajo.creada_en.desc(), OrdenTrabajo.id.desc())

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, OrdenTrabajo)

    async def _primera(self, statement) -> OrdenTrabajo | None:
        return (await self.session.exec(statement)).first()

    async def get_con_vehiculo(self, orden_id: int) -> OrdenTrabajo | None:
        """Orden con su vehículo precargado (para la patente de las respuestas)."""
        statement = (
            select(OrdenTrabajo)
            .where(OrdenTrabajo.id == orden_id)
            .options(joinedload(OrdenTrabajo.vehiculo))
        )
        return await self._primera(statement)

    async def get_con_dueno(self, orden_id: int) -> OrdenTrabajo | None:
        """Orden con vehículo y cliente precargados (decisión de «dueño»)."""
        statement = (
            select(OrdenTrabajo)
            .where(OrdenTrabajo.id == orden_id)
            .options(
                joinedload(OrdenTrabajo.vehiculo).joinedload(Vehiculo.cliente)
            )
        )
        return await self._primera(statement)

    async def get_con_items(self, orden_id: int) -> OrdenTrabajo | None:
        """Orden con vehículo e ítems (con su repuesto) para terminar.

        Los ítems traen el repuesto en la misma precarga: el servicio lee el
        stock de cada uno sin una consulta por ítem y sin carga perezosa.
        """
        statement = (
            select(OrdenTrabajo)
            .where(OrdenTrabajo.id == orden_id)
            .options(
                joinedload(OrdenTrabajo.vehiculo),
                selectinload(OrdenTrabajo.items).joinedload(ItemOrden.repuesto),
            )
        )
        return await self._primera(statement)

    async def get_detalle(self, orden_id: int) -> OrdenTrabajo | None:
        """Detalle completo en un número fijo de consultas.

        Tres consultas, independientes de la cantidad de ítems: (1) la orden
        con su vehículo y el cliente dueño, (2) los ítems con su repuesto,
        (3) el historial de estados. No hay ningún acceso perezoso.
        """
        statement = (
            select(OrdenTrabajo)
            .where(OrdenTrabajo.id == orden_id)
            .options(
                joinedload(OrdenTrabajo.vehiculo).joinedload(Vehiculo.cliente),
                selectinload(OrdenTrabajo.items).joinedload(ItemOrden.repuesto),
                selectinload(OrdenTrabajo.historial_estados),
            )
        )
        return await self._primera(statement)

    async def listar(
        self, params: PageParams, *filtros
    ) -> Page[OrdenTrabajo]:
        """Página de órdenes con la patente del vehículo precargada.

        ``count`` recibe **los mismos filtros** que la página. No se usa
        ``BaseRepository.list_page`` porque éste no acepta opciones de carga y
        tocar ``orden.vehiculo`` en el listado sería carga perezosa.
        """
        total = await self.count(*filtros)

        statement = select(OrdenTrabajo)
        todos = self._filtros(filtros)
        if todos:
            statement = statement.where(*todos)
        statement = (
            statement.options(joinedload(OrdenTrabajo.vehiculo))
            .order_by(*self._orden_por)
            .offset(params.offset)
            .limit(params.size)
        )
        items = (await self.session.exec(statement)).all()

        return Page.create(items=items, total=total, params=params)


class ItemOrdenRepository(BaseRepository[ItemOrden]):
    """Acceso a ``item_orden``. Composición: no existe sin su orden."""

    _orden_por = (ItemOrden.id,)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ItemOrden)

    async def listar_por_orden(self, orden_id: int) -> Sequence[ItemOrden]:
        """Ítems de la orden con su repuesto precargado, en orden de id."""
        statement = (
            select(ItemOrden)
            .where(ItemOrden.orden_id == orden_id)
            .options(joinedload(ItemOrden.repuesto))
            .order_by(ItemOrden.id)
        )
        return (await self.session.exec(statement)).all()


class HistorialEstadoOrdenRepository(BaseRepository[HistorialEstadoOrden]):
    """Alta y lectura de ``historial_estado_orden`` (sólo agregado, RN-15)."""

    _orden_por = (HistorialEstadoOrden.cuando, HistorialEstadoOrden.id)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HistorialEstadoOrden)

    async def listar_por_orden(self, orden_id: int) -> Sequence[HistorialEstadoOrden]:
        """Historial de la orden en orden cronológico determinista."""
        statement = (
            select(HistorialEstadoOrden)
            .where(HistorialEstadoOrden.orden_id == orden_id)
            .order_by(*self._orden_por)
        )
        return (await self.session.exec(statement)).all()


class EstadoOrdenRepository:
    """Repositorio de **sólo lectura** del catálogo ``estado_orden`` (DD-07).

    No hereda de ``BaseRepository`` a propósito: la clave primaria es
    ``codigo`` (no ``id``) y desde la API el catálogo no se escribe (RN-19).
    Heredar le daría ``add``/``update``/``delete`` que no debe ofrecer; esta
    clase no expone ninguna escritura.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, codigo: str) -> EstadoOrden | None:
        """Estado del catálogo por su código (``session.get`` por PK)."""
        return await self.session.get(EstadoOrden, codigo)

    async def listar(self) -> Sequence[EstadoOrden]:
        """Catálogo completo, en el orden de ``posicion``."""
        statement = select(EstadoOrden).order_by(EstadoOrden.posicion)
        return (await self.session.exec(statement)).all()
