"""Router de autenticación del módulo ``usuarios`` (``C-07``).

Es un **objeto de router separado** de ``app/modules/usuarios/router.py`` a
propósito: ``C-08`` monta dos grupos de rutas (DD-05 / US-015 CA-1) — el grupo
**abierto** con ``/auth`` y ``/health``, y el **protegido** con ``/usuarios``,
``/repuestos``, etc., con el control de ``debe_cambiar_password`` montado una
sola vez. Si ``/auth`` compartiera el router de ``/usuarios``, no se podría
montar en dos grupos distintos.

Rutas (todas en el grupo abierto; las dos últimas exigen sesión):

- ``POST /auth/registro``: 201, usuario + rol CLIENTE + ficha de cliente.
- ``POST /auth/login``: 200 **sin token en el cuerpo**; el JWT va en la cookie.
- ``POST /auth/logout``: borra la cookie, 200.
- ``GET /auth/yo``: usuario, roles vigentes y roles del token (200/401).
- ``POST /auth/cambiar-password``: 200/401/422; emite un token nuevo.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.dependencies import (
    NOMBRE_COOKIE,
    SessionDep,
    UsuarioActual,
    UsuarioActualDep,
)
from app.modules.usuarios import service
from app.modules.usuarios.schemas import (
    CambioPassword,
    LoginCrear,
    MensajeRespuesta,
    RegistroCrear,
    SesionRespuesta,
    UsuarioLeer,
    YoRespuesta,
)
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork

router = APIRouter(prefix="/auth", tags=["Autenticación"])


async def get_uow(session: AsyncSession = SessionDep) -> UsuariosUnitOfWork:
    """Arma el UoW del módulo con la sesión de la petición, sin abrirlo.

    Es el mismo patrón que ``app/modules/usuarios/router.py``: el router arma el
    UoW con una dependencia y el servicio lo abre con ``async with``.
    """
    return UsuariosUnitOfWork(session)


UoWDep = Annotated[UsuariosUnitOfWork, Depends(get_uow)]


def _segundos_de_sesion() -> int:
    """Duración del token en segundos: ``Max-Age`` y cuerpo usan el mismo valor."""
    return settings.TOKEN_EXPIRE_MINUTES * 60


def _poner_cookie(response: Response, token: str) -> None:
    """Deja el JWT en la cookie ``access_token`` (US-011 CA-2).

    ``HttpOnly`` impide leerla desde JavaScript, ``SameSite=Lax`` acompaña la
    navegación normal y ``Secure`` sale de la configuración (false en desarrollo,
    true en producción). El token **nunca** viaja en el cuerpo ni en un header.
    """
    response.set_cookie(
        key=NOMBRE_COOKIE,
        value=token,
        max_age=_segundos_de_sesion(),
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )


@router.post(
    "/registro",
    response_model=UsuarioLeer,
    status_code=status.HTTP_201_CREATED,
    summary="Auto-registro de un cliente (usuario + rol CLIENTE + ficha)",
)
async def registro(uow: UoWDep, datos: RegistroCrear) -> UsuarioLeer:
    usuario = await service.registrar(uow, datos)
    return UsuarioLeer.model_validate(usuario)


@router.post(
    "/login",
    response_model=SesionRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Inicia sesión y deja el JWT en la cookie access_token",
)
async def login(
    request: Request,
    response: Response,
    uow: UoWDep,
    datos: LoginCrear,
) -> SesionRespuesta:
    ip = request.client.host if request.client else "desconocida"
    usuario, _roles, token = await service.autenticar(
        uow,
        request.app.state.session_maker,
        datos,
        ip=ip,
        hash_ficticio=request.app.state.hash_ficticio,
    )
    _poner_cookie(response, token)
    return SesionRespuesta(
        mensaje="Sesión iniciada",
        debe_cambiar_password=usuario.debe_cambiar_password,
        expira_en_segundos=_segundos_de_sesion(),
    )


@router.post(
    "/logout",
    response_model=MensajeRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Cierra la sesión borrando la cookie",
)
async def logout(response: Response) -> MensajeRespuesta:
    response.delete_cookie(key=NOMBRE_COOKIE, path="/")
    return MensajeRespuesta(mensaje="Sesión cerrada")


@router.get(
    "/yo",
    response_model=YoRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Identidad de la sesión: usuario y roles",
)
async def yo(
    uow: UoWDep,
    actual: UsuarioActual = UsuarioActualDep,
) -> YoRespuesta:
    roles_vigentes = await service.roles_vigentes(uow, actual.usuario.id)
    roles_token = [str(rol) for rol in actual.claims.get("roles", [])]
    return YoRespuesta(
        usuario=UsuarioLeer.model_validate(actual.usuario),
        roles_vigentes=roles_vigentes,
        roles_token=roles_token,
    )


@router.post(
    "/cambiar-password",
    response_model=SesionRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Cambia la contraseña y emite un token nuevo",
)
async def cambiar_password(
    response: Response,
    uow: UoWDep,
    datos: CambioPassword,
    actual: UsuarioActual = UsuarioActualDep,
) -> SesionRespuesta:
    token = await service.cambiar_password(uow, actual.usuario, datos)
    _poner_cookie(response, token)
    return SesionRespuesta(
        mensaje="Contraseña actualizada",
        debe_cambiar_password=False,
        expira_en_segundos=_segundos_de_sesion(),
    )
