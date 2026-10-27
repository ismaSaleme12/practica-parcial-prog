"""Modelos del dominio de órdenes de trabajo.

Tablas: ``estado_orden`` (catálogo), ``orden_trabajo``, ``item_orden``
(composición) e ``historial_estado_orden``.

Reglas que viven en la base:

- ``estado_orden.codigo`` es la clave primaria (no un ``id``): así
  ``orden_trabajo.estado`` se lee igual en psql que en la API (DD-01) y
  ``posicion`` es UNIQUE.
- ``orden_trabajo.estado`` es FK a ``estado_orden.codigo``: un estado que no
  exista lo rechaza la base (RN-19). ``total`` es ``NUMERIC(12,2) >= 0``.
- ``item_orden`` tiene UNIQUE ``(orden_id, repuesto_id)`` (sin repuestos
  repetidos) y CHECK de ``cantidad`` y ``precio_unitario`` mayores que cero.
- ``historial_estado_orden`` referencia el catálogo por sus dos extremos.
- El catálogo lo carga ``seed.py``, no la migración: la tabla nace vacía.
- ``historial_estado_orden`` es de sólo agregado; el disparador lo crea ``C-04``.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:  # solo para los tipos; el registro real lo hace ``app/models.py``
    from app.modules.clientes.models import Vehiculo
    from app.modules.repuestos.models import MovimientoStock, Repuesto
    from app.modules.usuarios.models import Usuario


def _ahora() -> datetime:
    """Marca de tiempo con zona horaria (todas las fechas del esquema son timestamptz)."""
    return datetime.now(timezone.utc)


class EstadoOrden(SQLModel, table=True):
    """Catálogo de estados. Sus filas son datos: las carga ``seed.py``."""

    __tablename__ = "estado_orden"
    __table_args__ = (UniqueConstraint("posicion", name="uq_estado_orden_posicion"),)

    codigo: str = Field(sa_column=Column(String(30), primary_key=True))
    descripcion: str = Field(sa_column=Column(String(120), nullable=False))
    posicion: int = Field(sa_column=Column(Integer, nullable=False))
    es_final: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )

    ordenes: list["OrdenTrabajo"] = Relationship(
        back_populates="estado_actual",
        sa_relationship_kwargs={"lazy": "raise_on_sql"},
    )
    historiales_desde: list["HistorialEstadoOrden"] = Relationship(
        back_populates="estado_desde",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "HistorialEstadoOrden.desde_estado",
        },
    )
    historiales_hasta: list["HistorialEstadoOrden"] = Relationship(
        back_populates="estado_hasta",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "HistorialEstadoOrden.hasta_estado",
        },
    )


class OrdenTrabajo(SQLModel, table=True):
    """Orden de trabajo de un vehículo. Nace PENDIENTE y se mueve por el catálogo."""

    __tablename__ = "orden_trabajo"
    __table_args__ = (
        CheckConstraint("total >= 0", name="ck_orden_trabajo_total_no_negativo"),
        Index("ix_orden_trabajo_vehiculo_id", "vehiculo_id"),
        Index("ix_orden_trabajo_mecanico_id", "mecanico_id"),
        Index("ix_orden_trabajo_estado", "estado"),
    )

    id: int | None = Field(default=None, primary_key=True)
    vehiculo_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("vehiculo.id", name="fk_orden_trabajo_vehiculo", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    mecanico_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("usuario.id", name="fk_orden_trabajo_mecanico", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    # Columna con el nombre obligatorio (``estado``); el estado navegable es
    # ``estado_actual``, porque un atributo no puede llamarse igual que la columna.
    estado: str = Field(
        sa_column=Column(
            String(30),
            ForeignKey("estado_orden.codigo", name="fk_orden_trabajo_estado", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    falla: str = Field(sa_column=Column(Text, nullable=False))
    creada_en: datetime = Field(
        default_factory=_ahora,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    total: Decimal = Field(
        default=Decimal("0.00"),
        sa_column=Column(Numeric(12, 2), nullable=False, server_default=text("0")),
    )

    vehiculo: "Vehiculo" = Relationship(
        back_populates="ordenes",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "OrdenTrabajo.vehiculo_id",
        },
    )
    mecanico: Optional["Usuario"] = Relationship(
        back_populates="ordenes_asignadas",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "OrdenTrabajo.mecanico_id",
        },
    )
    estado_actual: "EstadoOrden" = Relationship(
        back_populates="ordenes",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "OrdenTrabajo.estado",
        },
    )
    # Composición (rombo lleno): un ítem no existe sin su orden.
    items: list["ItemOrden"] = Relationship(
        back_populates="orden",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "cascade": "all, delete-orphan",
        },
    )
    historial_estados: list["HistorialEstadoOrden"] = Relationship(
        back_populates="orden",
        sa_relationship_kwargs={"lazy": "raise_on_sql"},
    )
    movimientos_stock: list["MovimientoStock"] = Relationship(
        back_populates="orden",
        sa_relationship_kwargs={"lazy": "raise_on_sql"},
    )


class ItemOrden(SQLModel, table=True):
    """Repuesto usado en una orden. El precio se copia del repuesto al crear la orden (RN-10)."""

    __tablename__ = "item_orden"
    __table_args__ = (
        UniqueConstraint("orden_id", "repuesto_id", name="uq_item_orden_orden_repuesto"),
        CheckConstraint("cantidad > 0", name="ck_item_orden_cantidad_positiva"),
        CheckConstraint(
            "precio_unitario > 0",
            name="ck_item_orden_precio_unitario_positivo",
        ),
        # El UNIQUE (orden_id, repuesto_id) ya indexa ``orden_id`` como primera
        # columna; sólo falta el índice de la otra FK.
        Index("ix_item_orden_repuesto_id", "repuesto_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    orden_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("orden_trabajo.id", name="fk_item_orden_orden", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    repuesto_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("repuesto.id", name="fk_item_orden_repuesto", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    cantidad: int = Field(sa_column=Column(Integer, nullable=False))
    precio_unitario: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))

    orden: "OrdenTrabajo" = Relationship(
        back_populates="items",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "ItemOrden.orden_id",
        },
    )
    repuesto: "Repuesto" = Relationship(
        back_populates="items_orden",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "ItemOrden.repuesto_id",
        },
    )


class HistorialEstadoOrden(SQLModel, table=True):
    """Transición de estado de una orden. Sólo agregado."""

    __tablename__ = "historial_estado_orden"
    __table_args__ = (
        Index("ix_historial_estado_orden_orden_id", "orden_id"),
        Index("ix_historial_estado_orden_desde_estado", "desde_estado"),
        Index("ix_historial_estado_orden_hasta_estado", "hasta_estado"),
        Index("ix_historial_estado_orden_usuario_id", "usuario_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    orden_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("orden_trabajo.id", name="fk_historial_estado_orden", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    desde_estado: str | None = Field(
        default=None,
        sa_column=Column(
            String(30),
            ForeignKey("estado_orden.codigo", name="fk_historial_estado_desde", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    hasta_estado: str = Field(
        sa_column=Column(
            String(30),
            ForeignKey("estado_orden.codigo", name="fk_historial_estado_hasta", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    usuario_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("usuario.id", name="fk_historial_estado_usuario", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    cuando: datetime = Field(
        default_factory=_ahora,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )

    orden: "OrdenTrabajo" = Relationship(
        back_populates="historial_estados",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "HistorialEstadoOrden.orden_id",
        },
    )
    estado_desde: Optional["EstadoOrden"] = Relationship(
        back_populates="historiales_desde",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "HistorialEstadoOrden.desde_estado",
        },
    )
    estado_hasta: "EstadoOrden" = Relationship(
        back_populates="historiales_hasta",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "HistorialEstadoOrden.hasta_estado",
        },
    )
    usuario: "Usuario" = Relationship(
        back_populates="historial_estados",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "HistorialEstadoOrden.usuario_id",
        },
    )
