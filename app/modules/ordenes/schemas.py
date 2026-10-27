"""Contratos del módulo de órdenes de trabajo (Épica 8, US-023 a US-026).

Separados de los modelos de tabla a propósito:

- ``OrdenCrear`` declara **sólo** ``vehiculo_id``, ``falla`` e ``items``. El
  ``precio_unitario``, el ``total``, el ``estado``, la fecha y el ``mecanico_id``
  **no viajan en el cuerpo**: enviarlos es 422 por ``extra="forbid"`` (RN-10,
  caso C-16-style). ``items`` exige al menos un elemento y un validador rechaza
  los repuestos repetidos antes de tocar la base.
- ``EstadoOrdenCodigo`` declara los cuatro códigos del catálogo. Se usa también
  como tipo del filtro de ``GET /ordenes``: un estado que el contrato no declara
  es 422 (caso C-17), no 409 ni una lista vacía.
- Los campos de dinero (``total``, ``precio_unitario``, ``subtotal``) son
  ``Decimal`` y viajan como **string** (``Dinero``); nunca como número.
- ``OrdenDetalle`` refleja el detalle completo —vehículo, cliente, ítems con su
  repuesto e historial— tal como lo precarga el repositorio (sin carga
  perezosa); ``OrdenResumen`` es la fila liviana de los listados.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints, field_validator

from app.core.schemas import ContratoEntrada, ContratoSalida, Dinero

# Los códigos del catálogo ``estado_orden`` (DD-01). El catálogo se consulta
# desde la API y no se escribe desde ella (RN-19); estos valores son el
# contrato, no la fuente de verdad: la fuente es la tabla.
class EstadoOrdenCodigo(StrEnum):
    """Códigos de estado que el contrato de la API declara."""

    PENDIENTE = "PENDIENTE"
    EN_REPARACION = "EN_REPARACION"
    TERMINADA = "TERMINADA"
    CANCELADA = "CANCELADA"


# ``falla`` es Text en la base; el límite del contrato evita cuerpos enormes y
# un DataError del motor. No inventa un máximo de negocio.
Falla = Annotated[str, StringConstraints(min_length=1, max_length=2000)]

# Los mismos límites que el CHECK de la base: cantidad > 0.
Cantidad = Annotated[int, Field(gt=0)]


class ItemOrdenCrear(ContratoEntrada):
    """Ítem de una orden nueva: el repuesto y cuánto se usa.

    El precio **no** se declara: se copia del repuesto en el servidor (RN-10).
    """

    repuesto_id: int = Field(gt=0)
    cantidad: Cantidad


class OrdenCrear(ContratoEntrada):
    """Alta de una orden: vehículo, falla y al menos un ítem sin repetir."""

    vehiculo_id: int = Field(gt=0)
    falla: Falla
    items: list[ItemOrdenCrear] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def _sin_repuestos_repetidos(cls, items: list[ItemOrdenCrear]) -> list[ItemOrdenCrear]:
        """RN-10: una orden no repite el mismo repuesto entre sus ítems."""
        vistos: set[int] = set()
        for item in items:
            if item.repuesto_id in vistos:
                raise ValueError(
                    "Una orden no puede repetir el mismo repuesto entre sus ítems."
                )
            vistos.add(item.repuesto_id)
        return items


class ItemOrdenLeer(ContratoSalida):
    """Ítem del detalle, con el repuesto copiado y su subtotal calculado."""

    repuesto_id: int
    codigo: str
    descripcion: str
    cantidad: int
    precio_unitario: Dinero
    subtotal: Dinero


class HistorialEstadoLeer(ContratoSalida):
    """Una línea del historial de estados (sólo agregado, RN-15)."""

    desde_estado: str | None
    hasta_estado: str
    usuario_id: int
    cuando: datetime


class OrdenResumen(ContratoSalida):
    """Fila liviana de ``GET /ordenes`` y de las transiciones."""

    id: int
    vehiculo_id: int
    patente: str
    estado: str
    falla: str
    creada_en: datetime
    total: Dinero
    mecanico_id: int | None


class OrdenDetalle(OrdenResumen):
    """Detalle completo de una orden, con sus ítems y su historial."""

    cliente: str
    items: list[ItemOrdenLeer]
    historial: list[HistorialEstadoLeer]


class EstadoOrdenLeer(ContratoSalida):
    """Fila del catálogo de estados, en el orden de ``posicion``."""

    codigo: str
    descripcion: str
    posicion: int
    es_final: bool
