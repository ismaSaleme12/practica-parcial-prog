"""Contratos del módulo de repuestos (US-007, US-008, US-020 a US-022).

Separados de `models.Repuesto` a propósito:

- ``RepuestoCrear`` declara ``stock_inicial`` (``ge=0``) y **no** ``stock``:
  enviar ``stock`` es 422 (``extra="forbid"``) porque el stock sólo cambia por
  movimientos (RN-14). El ``stock_inicial`` no es la columna: es la instrucción
  de crear el primer ``movimiento_stock`` «Stock inicial» en el mismo UoW.
- ``RepuestoLeer`` expone ``precio`` como string Decimal (nunca número/float).
- ``RepuestoPatch`` fija la convención de PATCH: sólo ``descripcion`` y
  ``precio``, y sólo se aplican los campos enviados (``cambios_enviados``).
  Enviar ``stock`` responde 422 (caso C-16).
- ``ReponerStock`` es el único otro punto de entrada del stock (RN-14): una
  cantidad positiva que deja su ``movimiento_stock``.
- ``MovimientoStockLeer`` e ``HistorialPrecioLeer`` son los contratos de salida
  de las dos tablas de sólo agregado, con el dinero como string Decimal.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints

from app.core.schemas import ContratoEntrada, ContratoSalida, Dinero

# Las longitudes calcadas de los VARCHAR del esquema: un texto más largo es 422
# del contrato y no un DataError del motor.
Codigo = Annotated[str, StringConstraints(min_length=1, max_length=40)]
Descripcion = Annotated[str, StringConstraints(min_length=1, max_length=200)]

# NUMERIC(10,2) y mayor que cero: los mismos límites que el CHECK de la base.
Precio = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]

# ``movimiento_stock.cantidad`` es un entero distinto de cero; una reposición
# siempre es una entrada, así que el contrato exige ``> 0``.
Cantidad = Annotated[int, Field(gt=0)]


class RepuestoCrear(ContratoEntrada):
    """Alta de repuesto con stock inicial opcional (0 por defecto).

    ``stock`` no se declara: enviarlo es 422 (caso C-16). El stock del repuesto
    nace en ``stock_inicial`` y, si es mayor que cero, deja su movimiento
    «Stock inicial» en el mismo UoW (RN-14).
    """

    codigo: Codigo
    descripcion: Descripcion
    precio: Precio
    stock_inicial: int = Field(default=0, ge=0)


class RepuestoPatch(ContratoEntrada):
    """Contrato de referencia de la convención PATCH (``exclude_unset``).

    ``stock`` no se declara: enviarlo responde 422 (caso C-16). Un ``precio``
    idéntico al actual no deja línea de historial (RN-20).
    """

    descripcion: Descripcion | None = None
    precio: Precio | None = None


class ReponerStock(ContratoEntrada):
    """Reposición de stock: la cantidad entra positiva y deja su movimiento."""

    cantidad: Cantidad


class RepuestoLeer(ContratoSalida):
    """Salida de un repuesto: el dinero viaja como string Decimal."""

    id: int
    codigo: str
    descripcion: str
    precio: Dinero
    stock: int


class MovimientoStockLeer(ContratoSalida):
    """Una fila de ``movimiento_stock`` (sólo agregado, RN-15)."""

    id: int
    cantidad: int
    motivo: str
    usuario_id: int
    orden_id: int | None
    cuando: datetime


class HistorialPrecioLeer(ContratoSalida):
    """Una fila de ``historial_precio_repuesto`` (sólo agregado, RN-20)."""

    id: int
    precio_anterior: Dinero
    precio_nuevo: Dinero
    usuario_id: int
    cuando: datetime
