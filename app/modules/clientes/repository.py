"""Repositorios del módulo de clientes (cartera y vehículos).

Reglas que este módulo respeta:

- Heredan ``BaseRepository``/``SoftDeleteRepository``: ``add``/``update``/
  ``soft_delete`` hacen ``flush()`` y nada más; el UoW es el único punto de
  confirmación y la sesión la cierra la petición que la abrió.
- **Unicidad por la base, nunca por consulta previa** (RN-01): el ``documento``
  de ``cliente`` es UNIQUE y la ``patente`` de ``vehiculo`` es única **entre los
  vigentes** (índice único parcial ``WHERE borrado_en IS NULL``). No hay ningún
  ``SELECT`` que intente anticipar el choque: el ``IntegrityError`` lo traduce a
  409 el handler central.
- **Sin carga perezosa** (regla dura): las relaciones declaran
  ``lazy="raise_on_sql"``. La ficha del cliente y ``/mis-vehiculos`` precargan
  los vehículos con ``selectinload`` en un número **fijo** de consultas (dos),
  y sólo traen los vigentes (``borrado_en IS NULL``): un vehículo dado de baja
  deja de aparecer (RN-16).
- **Órdenes abiertas**: ``VehiculoRepository.tiene_ordenes_abiertas`` responde
  con un ``SELECT ... LIMIT 1`` propio que cruza ``orden_trabajo`` con el
  catálogo ``estado_orden`` por ``es_final`` (RN-16). La decisión de negocio
  queda en el servicio; el servicio no importa la lógica de otro módulo.
"""

from __future__ import annotations

from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.repository import BaseRepository, SoftDeleteRepository
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo


def _vehiculos_vigentes():
    """Opción de carga anticipada: los vehículos del cliente que no están de baja.

    ``and_()`` agrega un criterio al ``selectinload``: la relación se resuelve
    con **una** consulta extra (fija), con ``borrado_en IS NULL`` en el WHERE,
    sin depender de la carga perezosa (prohibida: ``lazy="raise_on_sql"``).
    """
    return selectinload(
        Cliente.vehiculos.and_(Vehiculo.borrado_en.is_(None))
    )


class ClienteRepository(BaseRepository[Cliente]):
    """Acceso a la tabla ``cliente`` con la ficha y su dueño por sesión."""

    _orden_por = (Cliente.id,)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Cliente)

    async def get_ficha(self, cliente_id: int) -> Cliente | None:
        """Cliente con sus vehículos vigentes precargados (2 consultas fijas)."""
        statement = (
            select(Cliente)
            .where(Cliente.id == cliente_id)
            .options(_vehiculos_vigentes())
        )
        return (await self.session.exec(statement)).first()

    async def get_by_usuario_id(self, usuario_id: int) -> Cliente | None:
        """Ficha del cliente dueño de la cuenta de sesión, con sus vehículos.

        ``cliente.usuario_id`` es UNIQUE y nulo: una cuenta tiene a lo sumo una
        ficha, y muchas cuentas (personal del taller) no tienen ninguna. Que no
        exista **no es un error**: ``/mis-vehiculos`` responde una lista vacía
        (RN-17).
        """
        statement = (
            select(Cliente)
            .where(Cliente.usuario_id == usuario_id)
            .options(_vehiculos_vigentes())
        )
        return (await self.session.exec(statement)).first()


class VehiculoRepository(SoftDeleteRepository[Vehiculo]):
    """Acceso a ``vehiculo`` con borrado lógico (``borrado_en``).

    Las lecturas normales excluyen los vehículos dados de baja; la baja escribe
    ``borrado_en`` y conserva la fila (RN-16). La patente se libera para un alta
    nueva por el índice único parcial, no por una consulta previa (caso C-19).
    """

    _orden_por = (Vehiculo.id,)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Vehiculo)

    async def tiene_ordenes_abiertas(self, vehiculo_id: int) -> bool:
        """¿El vehículo tiene órdenes en un estado que el catálogo no marca final?

        RN-16: un vehículo con órdenes abiertas (``es_final = false``) no se da
        de baja. La consulta es un ``LIMIT 1`` sobre el índice de
        ``orden_trabajo.vehiculo_id`` y el catálogo ``estado_orden``.
        """
        statement = (
            select(OrdenTrabajo.id)
            .join(EstadoOrden, OrdenTrabajo.estado == EstadoOrden.codigo)
            .where(
                OrdenTrabajo.vehiculo_id == vehiculo_id,
                EstadoOrden.es_final.is_(False),
            )
            .limit(1)
        )
        return (await self.session.exec(statement)).first() is not None
