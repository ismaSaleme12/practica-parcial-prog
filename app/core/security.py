"""Primitivas de seguridad: hash de contraseñas y token firmado.

Reglas duras que este módulo implementa:

- bcrypt corre **fuera del bucle de eventos** (``asyncio.to_thread``) y bajo un
  semáforo configurable (``BCRYPT_MAX_CONCURRENT_HASHES``): el costo sale de
  ``Settings`` y nunca se escribe en el código.
- El token se firma con la clave del entorno (sin default) y lleva ``sub``,
  ``iat`` y ``exp``. El ``iat`` viaja como marca de tiempo con fracciones de
  segundo (**sin truncar**) para poder compararlo contra ``password_cambiada_en``
  (RN-07).
- ``verificar_token`` **no levanta**: devuelve ``None`` y el llamador decide el 401.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"

# Límite de hashes simultáneos: bcrypt tarda ~300 ms y no debe saturar el pool
# de hilos ni bloquear el bucle. Bajo saturación las peticiones esperan turno.
_bcrypt_semaphore = asyncio.Semaphore(max(1, settings.BCRYPT_MAX_CONCURRENT_HASHES))


async def hash_password(password: str) -> str:
    """Devuelve el hash bcrypt de ``password`` calculado fuera del bucle.

    Precondición: el contrato de entrada ya validó que la contraseña no supere
    los 72 bytes (bcrypt los rechaza). Esa validación pertenece a los contratos,
    no a esta primitiva.
    """

    def _hash() -> str:
        salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    async with _bcrypt_semaphore:
        return await asyncio.to_thread(_hash)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña contra su hash. Nunca levanta: falla con ``False``."""

    def _verify() -> bool:
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"), hashed_password.encode("utf-8")
            )
        except (ValueError, TypeError):
            # Hash malformado, contraseña de más de 72 bytes, etc.
            return False

    async with _bcrypt_semaphore:
        return await asyncio.to_thread(_verify)


def crear_token(
    sub: str,
    roles: Sequence[str] | None = None,
    expires_delta: timedelta | None = None,
    iat_minimo: datetime | None = None,
) -> str:
    """Emite un JWT firmado con ``sub``, ``iat``, ``exp`` y, si se pasan, los roles.

    ``iat`` se codifica como marca de tiempo numérica con microsegundos: JWT
    admite fracciones de segundo y truncarlas haría indistinguibles dos sesiones
    del mismo segundo (RN-07). Los roles son **informativos**: la autorización
    real se consulta en la base en cada petición.

    ``iat_minimo`` garantiza por construcción que el token quede **después** de
    ese instante (el ``password_cambiada_en`` del usuario). No alcanza con tomar
    la hora: el reloj del sistema (en Windows, ~15,6 ms de granularidad) puede
    devolver el **mismo** instante dos veces seguidas, y entonces un token
    emitido justo después de un cambio de contraseña quedaría con el mismo
    ``iat`` que el cambio y RN-07 no podría distinguirlo de una sesión anterior.
    Si ``ahora`` no llega a superarlo, se corre un microsegundo.
    """
    ahora = datetime.now(timezone.utc)
    if iat_minimo is not None and ahora <= iat_minimo:
        ahora = iat_minimo + timedelta(microseconds=1)
    duracion = expires_delta or timedelta(minutes=settings.TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": sub,
        "iat": ahora.timestamp(),
        "exp": (ahora + duracion).timestamp(),
    }
    if roles is not None:
        payload["roles"] = list(roles)

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def verificar_token(token: str) -> dict[str, Any] | None:
    """Devuelve los claims del token o ``None`` si no es válido.

    Rechaza (sin levantar) tokens vencidos, con firma inválida o sin alguno de
    los claims obligatorios ``sub``, ``iat`` y ``exp``.
    """
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.PyJWTError:
        return None
