"""Contratos del módulo de clientes (Épica 6, US-017 a US-019).

Separados de `models.Cliente` y `models.Vehiculo` a propósito:

- ``ClienteCrear`` y ``VehiculoCrear`` rechazan los campos que no declaran
  (``extra="forbid"``): enlazar una cuenta (``usuario_id``) o escribir
  ``borrado_en`` no son operaciones de estas rutas.
- ``anio`` repite en el contrato los límites del CHECK de la base
  (1950–2100): fuera de rango es **422**, no un 409 de integridad.
- ``ClienteLeer`` es la ficha plana (la del alta); ``ClienteFicha`` agrega los
  vehículos vigentes, que el repositorio precarga con ``selectinload``.
- ``VehiculoLeer`` no expone ``borrado_en``: la baja se ve porque el vehículo
  deja de aparecer (RN-16).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

from app.core.schemas import ContratoEntrada, ContratoSalida

# Las longitudes calcadas de los VARCHAR del esquema: un texto más largo es 422
# del contrato y no un DataError del motor.
Nombre = Annotated[str, StringConstraints(min_length=1, max_length=120)]
Documento = Annotated[str, StringConstraints(min_length=1, max_length=40)]
Telefono = Annotated[str, StringConstraints(min_length=1, max_length=40)]
Patente = Annotated[str, StringConstraints(min_length=1, max_length=20)]
Marca = Annotated[str, StringConstraints(min_length=1, max_length=60)]
Modelo = Annotated[str, StringConstraints(min_length=1, max_length=60)]

# Los mismos límites que el CHECK ``anio BETWEEN 1950 AND 2100`` de la base.
Anio = Annotated[int, Field(ge=1950, le=2100)]


class ClienteCrear(ContratoEntrada):
    """Alta de un cliente del taller (puede quedar sin cuenta de usuario)."""

    nombre: Nombre
    documento: Documento
    telefono: Telefono


class VehiculoCrear(ContratoEntrada):
    """Alta de un vehículo de un cliente.

    El ``cliente_id`` viene por la URL (``POST /clientes/{id}/vehiculos``), nunca
    en el cuerpo: así el recurso de la ruta y la FK no pueden discrepar.
    """

    patente: Patente
    marca: Marca
    modelo: Modelo
    anio: Anio


class VehiculoLeer(ContratoSalida):
    """Vehículo vigente de un cliente."""

    id: int
    cliente_id: int
    patente: str
    marca: str
    modelo: str
    anio: int


class ClienteLeer(ContratoSalida):
    """Ficha plana del cliente (respuesta del alta)."""

    id: int
    nombre: str
    documento: str
    telefono: str


class ClienteFicha(ClienteLeer):
    """Ficha con sus vehículos vigentes, resueltos por carga anticipada."""

    vehiculos: list[VehiculoLeer]
