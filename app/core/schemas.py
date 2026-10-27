"""Piezas compartidas por los contratos (schemas) de todos los módulos.

- ``ContratoEntrada``: toda entrada rechaza los campos que no declara
  (``extra="forbid"``). Es lo que impide registrarse con un ``rol``, editar el
  ``stock`` por PATCH o inyectar ``precio``/``total`` en una orden.
- ``ContratoSalida``: lee desde el ORM (``from_attributes``) y declara sólo los
  campos que el cliente puede ver. Ningún contrato de salida de usuario declara
  ``password_hash``.
- ``Dinero``: ``Decimal`` en Python que **se serializa como string** con dos
  decimales. Nunca ``float``: el dinero viaja como texto (regla dura).
- ``cambios_enviados``: convención de PATCH — sólo los campos que el cliente
  envió (``exclude_unset``), sin convertir un ``null`` explícito en un intento
  de escribir ``NULL`` en una columna que no lo admite.

Este archivo es el octavo de ``app/core/``; se prefiere un lugar compartido
antes que duplicar ``Dinero`` y ``extra="forbid"`` en cada módulo (ver
``design.md``, D5).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, PlainSerializer


def _dinero_a_texto(valor: Decimal) -> str:
    """Formatea el monto con dos decimales, como pide el contrato de la API."""
    return f"{valor:.2f}"


# ``when_used="always"``: el string se garantiza tanto en ``model_dump()`` como
# en la respuesta JSON, sin depender de cómo serialice FastAPI.
Dinero = Annotated[
    Decimal,
    PlainSerializer(_dinero_a_texto, return_type=str, when_used="always"),
]


class ContratoEntrada(BaseModel):
    """Base de todo cuerpo de entrada: rechaza campos no declarados."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContratoSalida(BaseModel):
    """Base de todo cuerpo de salida construido desde una entidad del ORM."""

    model_config = ConfigDict(from_attributes=True)


def cambios_enviados(contrato: BaseModel) -> dict[str, Any]:
    """Devuelve sólo los campos presentes en el cuerpo (convención de PATCH).

    ``exclude_unset`` implementa «sólo cambia lo enviado»; ``exclude_none``
    evita que un ``null`` explícito intente escribir ``NULL`` en una columna
    NOT NULL (sería un 500 y no un 422).
    """
    return contrato.model_dump(exclude_unset=True, exclude_none=True)
