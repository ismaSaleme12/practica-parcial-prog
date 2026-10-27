"""Modelos del dominio de cartera de clientes.

Tablas: ``cliente`` y ``vehiculo``.

Reglas que viven en la base:

- ``cliente.usuario_id`` es UNIQUE y admite nulo (1:1 opcional con ``usuario``).
- ``cliente.documento`` es UNIQUE.
- ``vehiculo.patente`` es único **entre los vigentes**: índice único parcial
  ``WHERE borrado_en IS NULL`` (DD-03), para que la patente de un auto dado de
  baja se pueda volver a registrar.
- ``vehiculo.anio`` tiene CHECK entre 1950 y 2100.
- ``vehiculo`` y ``repuesto`` usan ``SoftDeleteRepository``: la baja escribe
  ``borrado_en`` y la fila no se borra.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:  # solo para los tipos; el registro real lo hace ``app/models.py``
    from app.modules.ordenes.models import OrdenTrabajo
    from app.modules.usuarios.models import Usuario


class Cliente(SQLModel, table=True):
    """Ficha del cliente. Puede tener cuenta de usuario (1:1) o no tenerla."""

    __tablename__ = "cliente"
    __table_args__ = (
        UniqueConstraint("usuario_id", name="uq_cliente_usuario_id"),
        UniqueConstraint("documento", name="uq_cliente_documento"),
    )

    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int | None = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("usuario.id", name="fk_cliente_usuario", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    nombre: str = Field(sa_column=Column(String(120), nullable=False))
    documento: str = Field(sa_column=Column(String(40), nullable=False))
    telefono: str = Field(sa_column=Column(String(40), nullable=False))

    # El UNIQUE de ``usuario_id`` ya crea el índice que necesita la FK.
    usuario: Optional["Usuario"] = Relationship(
        back_populates="cliente",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "Cliente.usuario_id",
        },
    )
    vehiculos: list["Vehiculo"] = Relationship(
        back_populates="cliente",
        sa_relationship_kwargs={"lazy": "raise_on_sql"},
    )


class Vehiculo(SQLModel, table=True):
    """Vehículo de un cliente, con borrado lógico (RN-16)."""

    __tablename__ = "vehiculo"
    __table_args__ = (
        CheckConstraint("anio BETWEEN 1950 AND 2100", name="ck_vehiculo_anio_rango"),
        Index("ix_vehiculo_cliente_id", "cliente_id"),
        Index(
            "uq_vehiculo_patente_vigente",
            "patente",
            unique=True,
            postgresql_where=text("borrado_en IS NULL"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    cliente_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("cliente.id", name="fk_vehiculo_cliente", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    patente: str = Field(sa_column=Column(String(20), nullable=False))
    marca: str = Field(sa_column=Column(String(60), nullable=False))
    modelo: str = Field(sa_column=Column(String(60), nullable=False))
    anio: int = Field(sa_column=Column(Integer, nullable=False))
    borrado_en: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    cliente: "Cliente" = Relationship(
        back_populates="vehiculos",
        sa_relationship_kwargs={
            "lazy": "raise_on_sql",
            "foreign_keys": "Vehiculo.cliente_id",
        },
    )
    ordenes: list["OrdenTrabajo"] = Relationship(
        back_populates="vehiculo",
        sa_relationship_kwargs={"lazy": "raise_on_sql"},
    )
