"""Contratos del módulo de repuestos (US-007, US-008).

Separados de `models.Repuesto` a propósito:

- ``RepuestoCrear`` **no declara** ``stock`` ni ``stock_inicial``: enviarlos es
  422 (``extra="forbid"``) porque el stock sólo cambia por movimientos (RN-14).
- ``RepuestoLeer`` expone ``precio`` como string Decimal (nunca número/float).
- ``RepuestoPatch`` fija la convención de PATCH: sólo ``descripcion`` y
  ``precio``, y sólo se aplican los campos enviados (``cambios_enviados``).
"""

from __future__ import annotations

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


class RepuestoCrear(ContratoEntrada):
    """Alta de repuesto. El stock nace en 0 y se mueve sólo por movimientos."""

    codigo: Codigo
    descripcion: Descripcion
    precio: Precio


class RepuestoPatch(ContratoEntrada):
    """Contrato de referencia de la convención PATCH (``exclude_unset``).

    ``stock`` no se declara: enviarlo responde 422 (caso C-16).
    """

    descripcion: Descripcion | None = None
    precio: Precio | None = None


class RepuestoLeer(ContratoSalida):
    """Salida de un repuesto: el dinero viaja como string Decimal."""

    id: int
    codigo: str
    descripcion: str
    precio: Dinero
    stock: int
