"""Modelos del dominio de repuestos y stock.

Tablas: ``repuesto``, ``movimiento_stock`` e ``historial_precio_repuesto``.

Reglas que viven en la base:

- ``repuesto.precio`` es ``NUMERIC(10,2)`` mayor que cero; ``stock`` no es
  negativo; ``codigo`` es único **entre los vigentes** (índice parcial, DD-03).
- ``movimiento_stock.cantidad`` tiene CHECK ``<> 0`` (IN-01: la consigna lo
  imprime como ``>> 0``, que en PostgreSQL es un desplazamiento de bits y no
  aplica a un entero con esa semántica).
- ``historial_precio_repuesto`` exige ``precio_nuevo > 0`` y
  ``precio_nuevo <> precio_anterior`` (IN-02); el precio puede subir o bajar.
- ``movimiento_stock`` e ``historial_precio_repuesto`` son de **sólo agregado**:
  el disparador que rechaza UPDATE y DELETE lo crea la migración de ``C-04``.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:  # solo para los tipos; el registro real lo hace ``app/models.py``
    from app.modules.ordenes.models import ItemOrden, OrdenTrabajo
    from app.modules.usuarios.models import Usuario


def _ahora() -> datetime:
    """Marca de tiempo con zona horaria (todas las fechas del esquema son timestamptz)."""
    return datetime.now(timezone.utc)


class Repuesto(SQLModel, table=True):
    """Repuesto del catálogo, con borrado lógico y stock que sólo cambia por movimientos."""

    __tablename__ = "repuesto"
    __table_args__ = (
        CheckConstraint("precio > 0", name="ck_repuesto_precio_positivo"),
        CheckConstraint("stock >= 0", name="ck_repuesto_stock_no_negativo"),
        Index(
            "uq_repuesto_codigo_vigente",
            "codigo",
            unique=True,
            postgresql_where=text("borrado_en IS NULL"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    codigo: str = Field(sa_column=Column(String(40), nullable=False))
    descripcion: str = Field(sa_column=Column(String(200), nullable=False))
    precio: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    stock: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    borrado_en: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    items_orden: list["ItemOrden"] = Relationship(
        back_populates="repuesto",
        sa_relationship_kwargs={"lazy": "raise_on_sql"},
    )
    movimientos_stock: list["MovimientoStock"] = Relationship(
        back_populates="repuesto",
        sa_relationship_kwargs={"lazy": "raise_on_sql"},
    )
    historial_precios: list["HistorialPrecioRepuesto"] = Relationship(
        back_populates="repuesto",
        sa_relationship_kwargs={"lazy": "raise_on_sql"},
    )


class MovimientoStock(SQLModel, table=True):
    """Punto único de escritura del stock (RN-14). Sólo agregado.

    La reposición entra con ``cantidad`` positiva; la salida por terminación de
    una orden, negativa.
    """

    __tablename__ = "movimiento_stock"
    __table_args__ = (
        CheckConstraint("cantidad <> 0", name="ck_movimiento_stock_cantidad_no_cero"),
        Index("ix_movimiento_stock_repuesto_id", "repuesto_id"),
        Index("ix_movimiento_stock_orden_id", "orden_id"),
        Index("ix_movimiento_stock_usuario_id", "usuario_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    repuesto_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("repuesto.id", name="fk_movimiento_stock_repuesto", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    orden_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("orden_trabajo.id", name="fk_movimiento_stock_orden", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    usuario_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("usuario.id", name="fk_movimiento_stock_usuario", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    cantidad: int = Field(sa_column=Column(Integer, nullable=False))
    motivo: str = Field(sa_column=Column(String(120), nullable=False))
    cuando: datetime = Field(
        default_factory=_ahora,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )

    repuesto: "Repuesto" = Relationship(
        back_populates="movimientos_stock",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "MovimientoStock.repuesto_id",
        },
    )
    orden: Optional["OrdenTrabajo"] = Relationship(
        back_populates="movimientos_stock",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "MovimientoStock.orden_id",
        },
    )
    usuario: "Usuario" = Relationship(
        back_populates="movimientos_stock",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "MovimientoStock.usuario_id",
        },
    )


class HistorialPrecioRepuesto(SQLModel, table=True):
    """Cada cambio de precio, en la misma transacción que el cambio (RN-20). Sólo agregado."""

    __tablename__ = "historial_precio_repuesto"
    __table_args__ = (
        CheckConstraint("precio_nuevo > 0", name="ck_historial_precio_precio_nuevo_positivo"),
        CheckConstraint(
            "precio_nuevo <> precio_anterior",
            name="ck_historial_precio_cambio_efectivo",
        ),
        Index("ix_historial_precio_repuesto_repuesto_id", "repuesto_id"),
        Index("ix_historial_precio_repuesto_usuario_id", "usuario_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    repuesto_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("repuesto.id", name="fk_historial_precio_repuesto", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    usuario_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("usuario.id", name="fk_historial_precio_usuario", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    precio_anterior: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    precio_nuevo: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    cuando: datetime = Field(
        default_factory=_ahora,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )

    repuesto: "Repuesto" = Relationship(
        back_populates="historial_precios",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "HistorialPrecioRepuesto.repuesto_id",
        },
    )
    usuario: "Usuario" = Relationship(
        back_populates="historial_precios",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "HistorialPrecioRepuesto.usuario_id",
        },
    )
