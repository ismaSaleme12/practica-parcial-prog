"""Contratos del módulo de usuarios (US-007).

Puntos que este archivo fija:

- ``extra="forbid"``: no se puede crear un usuario con ``rol`` ni con
  ``password_hash`` (el rol es una asignación, no una columna: DD-02).
- La contraseña se mide en **bytes** UTF-8 (máximo 72): bcrypt ≥ 5 rechaza las
  más largas con excepción, así que sin este límite la petición daría 500 en
  lugar de 422 (US-009 CA-4). Una «ñ» ocupa dos bytes.
- ``UsuarioLeer`` **no declara** ``password_hash``: ninguna respuesta lo lleva.

No se usa ``EmailStr`` para no agregar ``email-validator`` al stack cerrado: el
formato se valida con un patrón en el contrato.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints, field_validator

from app.core.schemas import ContratoEntrada, ContratoSalida

# Las longitudes calcadas de los VARCHAR del esquema (usuario.email 320,
# usuario.nombre 120): un texto más largo es 422 del contrato, no un DataError.
Email = Annotated[
    str,
    StringConstraints(
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]
Nombre = Annotated[str, StringConstraints(min_length=1, max_length=120)]
Password = Annotated[str, StringConstraints(min_length=1)]

LIMITE_PASSWORD_BYTES = 72


class UsuarioCrear(ContratoEntrada):
    """Alta de usuario con contraseña provisoria."""

    email: Email
    nombre: Nombre
    password: Password

    @field_validator("password")
    @classmethod
    def _limite_de_bytes(cls, valor: str) -> str:
        """bcrypt sólo acepta hasta 72 bytes; se valida acá para responder 422."""
        if len(valor.encode("utf-8")) > LIMITE_PASSWORD_BYTES:
            raise ValueError(
                "La contraseña no puede superar los "
                f"{LIMITE_PASSWORD_BYTES} bytes en UTF-8."
            )
        return valor


class UsuarioLeer(ContratoSalida):
    """Salida de un usuario: nunca incluye ``password_hash``."""

    id: int
    email: str
    nombre: str
    activo: bool
    debe_cambiar_password: bool
