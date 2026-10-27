"""Contratos del módulo de usuarios (US-007 y Épica 4).

Puntos que este archivo fija:

- ``extra="forbid"``: no se puede crear un usuario con ``rol`` ni con
  ``password_hash`` (el rol es una asignación, no una columna: DD-02), ni enviar
  campos que el login o el registro no declaran.
- Toda contraseña que termina en bcrypt (alta, registro, login, la actual y la
  nueva del cambio) se mide en **bytes** UTF-8 y admite **máximo 72**: bcrypt ≥ 5
  rechaza las más largas con excepción, así que sin este límite la petición daría
  500 en lugar de 422 (US-009 CA-4). Una «ñ» ocupa dos bytes.
- La contraseña **nueva** del cambio tiene además un mínimo de **más de 8
  bytes**: el Flujo 4 de ``07_flujos_principales.md`` manda 422 para «≤ 8 bytes o
  > 72 bytes», y esa lectura literal se documenta en el ``design.md`` de C-07.
- ``UsuarioLeer`` **no declara** ``password_hash``: ninguna respuesta lo lleva.

No se usa ``EmailStr`` para no agregar ``email-validator`` al stack cerrado: el
formato se valida con un patrón en el contrato.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import StringConstraints, field_validator

from app.core.schemas import ContratoEntrada, ContratoSalida

if TYPE_CHECKING:  # sólo para los tipos; evita un ciclo en tiempo de import
    from app.modules.usuarios.models import AsignacionRol

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
# Longitudes calcadas de los VARCHAR del esquema (cliente.documento 40,
# cliente.telefono 40): un texto más largo es 422 del contrato, no un DataError.
Documento = Annotated[str, StringConstraints(min_length=1, max_length=40)]
Telefono = Annotated[str, StringConstraints(min_length=1, max_length=40)]

LIMITE_PASSWORD_BYTES = 72
MINIMO_PASSWORD_NUEVA_BYTES = 8


def _validar_password_hasta_72(valor: str) -> str:
    """bcrypt sólo acepta hasta 72 bytes; se valida acá para responder 422."""
    if len(valor.encode("utf-8")) > LIMITE_PASSWORD_BYTES:
        raise ValueError(
            "La contraseña no puede superar los "
            f"{LIMITE_PASSWORD_BYTES} bytes en UTF-8."
        )
    return valor


class UsuarioCrear(ContratoEntrada):
    """Alta de usuario con contraseña provisoria."""

    email: Email
    nombre: Nombre
    password: Password

    @field_validator("password")
    @classmethod
    def _limite_de_bytes(cls, valor: str) -> str:
        return _validar_password_hasta_72(valor)


class RegistroCrear(ContratoEntrada):
    """Auto-registro de un cliente (RN-02).

    Crea usuario + asignación CLIENTE + ficha de cliente en un solo UoW. El
    contrato **no** declara ``rol``: el rol del auto-registro es siempre CLIENTE
    (``extra="forbid"`` rechaza cualquier intento de elegir otro).
    """

    email: Email
    nombre: Nombre
    password: Password
    documento: Documento
    telefono: Telefono

    @field_validator("password")
    @classmethod
    def _limite_de_bytes(cls, valor: str) -> str:
        return _validar_password_hasta_72(valor)


class LoginCrear(ContratoEntrada):
    """Credenciales del login.

    La contraseña también se acota a 72 bytes: es un campo que termina en bcrypt
    (US-009 CA-4). Una contraseña más larga da 422 antes de tocar la base.
    """

    email: Email
    password: Password

    @field_validator("password")
    @classmethod
    def _limite_de_bytes(cls, valor: str) -> str:
        return _validar_password_hasta_72(valor)


class CambioPassword(ContratoEntrada):
    """Cambio de contraseña: actual + nueva.

    Decisión de C-07 (documentada en ``design.md``): la nueva sólo es válida si
    mide **más de 8 bytes y hasta 72 bytes** en UTF-8. Es la lectura literal del
    Flujo 4: «Nueva ≤ 8 bytes o > 72 bytes u otra regla del contrato → 422».
    """

    password_actual: Password
    password_nueva: Password

    @field_validator("password_actual")
    @classmethod
    def _limite_actual(cls, valor: str) -> str:
        return _validar_password_hasta_72(valor)

    @field_validator("password_nueva")
    @classmethod
    def _regla_nueva(cls, valor: str) -> str:
        en_bytes = len(valor.encode("utf-8"))
        if en_bytes <= MINIMO_PASSWORD_NUEVA_BYTES:
            raise ValueError(
                "La contraseña nueva debe tener más de "
                f"{MINIMO_PASSWORD_NUEVA_BYTES} bytes en UTF-8."
            )
        if en_bytes > LIMITE_PASSWORD_BYTES:
            raise ValueError(
                "La contraseña nueva no puede superar los "
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


class SesionRespuesta(ContratoSalida):
    """Cuerpo del login y del cambio de contraseña: **sin** el token.

    El JWT viaja sólo en la cookie ``access_token`` (US-011 CA-3).
    """

    mensaje: str
    debe_cambiar_password: bool
    expira_en_segundos: int


class MensajeRespuesta(ContratoSalida):
    """Respuesta mínima para operaciones sin cuerpo propio (logout)."""

    mensaje: str


class YoRespuesta(ContratoSalida):
    """Identidad de la sesión: usuario, roles vigentes y roles del token.

    Los roles del token son **informativos**; los vigentes se consultan en la
    base en esta petición (RN-04).
    """

    usuario: UsuarioLeer
    roles_vigentes: list[str]
    roles_token: list[str]


# Los cuatro roles del CHECK de ``asignacion_rol``. Se declaran acá (contrato)
# para que un rol desconocido en el cuerpo sea 422, no un error de integridad.
RolNombre = Literal["ADMIN", "RECEPCION", "MECANICO", "CLIENTE"]


class RolAsignar(ContratoEntrada):
    """Asignación de un rol con vigencia opcional (US-014).

    ``vence_en`` es opcional, pero si viene debe traer **zona horaria** y estar
    en el **futuro**: una fecha sin zona es ambigua (¿la hora de quién?) y una
    que ya pasó no choca con nada guardado (Ejercicio 5). Las dos son 422, no
    409, porque son errores de contrato. ``desde`` también exige zona horaria
    si se envía (todas las fechas del esquema son ``timestamptz``).
    """

    rol: RolNombre
    desde: datetime | None = None
    vence_en: datetime | None = None

    @field_validator("desde", "vence_en")
    @classmethod
    def _con_zona_horaria(cls, valor: datetime | None) -> datetime | None:
        if valor is not None and (
            valor.tzinfo is None or valor.utcoffset() is None
        ):
            raise ValueError(
                "La fecha debe incluir zona horaria "
                "(por ejemplo 2026-12-31T23:59:59+00:00)."
            )
        return valor

    @field_validator("vence_en")
    @classmethod
    def _en_el_futuro(cls, valor: datetime | None) -> datetime | None:
        if valor is not None and valor <= datetime.now(timezone.utc):
            raise ValueError("La fecha de vencimiento debe ser futura.")
        return valor


class RolLeer(ContratoSalida):
    """Una asignación de rol con su vigencia e historial.

    ``vigente`` aplica la misma definición que ``requiere_rol``: no revocada y
    sin vencer. Las filas revocadas o vencidas se devuelven igual porque el
    historial de quién tuvo qué rol y hasta cuándo no se borra nunca.
    """

    rol: str
    desde: datetime
    vence_en: datetime | None = None
    revocada_en: datetime | None = None
    vigente: bool

    @classmethod
    def de_asignacion(
        cls,
        asignacion: "AsignacionRol",
        ahora: datetime | None = None,
    ) -> "RolLeer":
        momento = ahora or datetime.now(timezone.utc)
        vence = asignacion.vence_en
        if vence is not None and vence.tzinfo is None:  # defensa: es timestamptz
            vence = vence.replace(tzinfo=timezone.utc)
        vigente = asignacion.revocada_en is None and (
            vence is None or vence > momento
        )
        return cls(
            rol=asignacion.rol,
            desde=asignacion.desde,
            vence_en=asignacion.vence_en,
            revocada_en=asignacion.revocada_en,
            vigente=vigente,
        )


class EventoLeer(ContratoSalida):
    """Un evento de ``evento_seguridad`` (US-016)."""

    id: int
    cuando: datetime
    actor: str
    accion: str
