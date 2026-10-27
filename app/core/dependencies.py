"""Dependencias compartidas de FastAPI.

``C-07`` implementa la versión **mínima** de ``get_usuario_actual`` que necesitan
``GET /auth/yo`` y ``POST /auth/cambiar-password``:

- Lee el token **sólo** de ``request.cookies["access_token"]``; nunca de la
  cabecera ``Authorization`` (US-011 CA-4, caso C-03).
- Sin cookie, token inválido o vencido → 401.
- Usuario inexistente o ``activo=False`` → 401.
- ``iat`` del token **anterior** a ``password_cambiada_en`` → 401, comparando
  **sin truncar** (RN-07 / DD-04).

**Pendiente explícito de C-08**: ``requiere_rol`` (403, consulta de roles
vigentes en cada petición) y el control de ``debe_cambiar_password`` (403) con
los dos grupos de rutas de ``main.py`` (DD-05 / US-013 / US-015).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.security import verificar_token
from app.modules.usuarios.models import Usuario

# Dependencia de sesión lista para usar en los routers:
#     async def handler(session: AsyncSession = SessionDep) -> ...
SessionDep = Depends(get_session)

NOMBRE_COOKIE = "access_token"
MENSAJE_SIN_SESION = "No hay una sesión válida."
HTTP_401 = 401


@dataclass(frozen=True)
class UsuarioActual:
    """Identidad resuelta de la petición: el usuario y los claims del token.

    ``claims`` expone ``roles`` (informativos) para ``GET /auth/yo``. La
    autorización real se consulta en la base en cada petición (RN-04); por eso
    ``C-08`` agregará ``requiere_rol`` sin confiar en estos roles.
    """

    usuario: Usuario
    claims: dict[str, Any]


def _sin_sesion() -> HTTPException:
    """401 uniforme: no se distingue por qué falló la sesión."""
    return HTTPException(status_code=HTTP_401, detail=MENSAJE_SIN_SESION)


async def get_usuario_actual(
    request: Request,
    session: AsyncSession = SessionDep,
) -> UsuarioActual:
    """Resuelve el usuario de la cookie ``access_token`` o lanza 401.

    No acepta ``Authorization: Bearer``: el token viaja **sólo** en la cookie
    HttpOnly (regla dura, caso C-03).
    """
    token = request.cookies.get(NOMBRE_COOKIE)
    if not token:
        raise _sin_sesion()

    claims = verificar_token(token)
    if claims is None:
        raise _sin_sesion()

    try:
        usuario_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        raise _sin_sesion() from None

    usuario = await session.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo:
        raise _sin_sesion()

    cambiada_en = usuario.password_cambiada_en
    if cambiada_en is not None:
        # ``iat`` viaja como número con microsegundos y ``password_cambiada_en``
        # es timestamptz: la comparación es estricta y sin truncar (RN-07).
        # El token emitido por el propio cambio se crea después del commit y
        # queda con iat mayor; los anteriores, con iat menor, dan 401.
        if cambiada_en.tzinfo is None:  # defensa: nunca debería ser naive
            cambiada_en = cambiada_en.replace(tzinfo=timezone.utc)
        iat = claims.get("iat")
        if not isinstance(iat, (int, float)) or float(iat) < cambiada_en.timestamp():
            raise _sin_sesion()

    return UsuarioActual(usuario=usuario, claims=claims)


UsuarioActualDep = Depends(get_usuario_actual)
