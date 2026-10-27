"""Router del módulo de usuarios: personal, roles y eventos de seguridad.

Endpoints (todos ADMIN, en el grupo **protegido** de ``main.py``):

- ``POST /usuarios``: alta de personal con contraseña provisoria (201).
- ``GET /usuarios/{id}/roles``: historial de roles del usuario (200/404).
- ``POST /usuarios/{id}/roles``: asignación con vigencia opcional
  (201/404/409/422).
- ``DELETE /usuarios/{id}/roles/{rol}``: revocación con ``revocada_en``, sin
  borrar la fila (200/404/409).
- ``GET /eventos`` (router propio, ``eventos_router``): historial de seguridad
  paginado (200/422).

La matriz de ``03_actores_y_roles.md`` es la única fuente de permisos: estas
rutas son de ADMIN y no aceptan otro rol. La autenticación (401) y el cambio
obligatorio (403) los aporta el grupo protegido, montados una sola vez en
``main.py`` (DD-05). ``requiere_rol("ADMIN")`` decide el permiso por ruta con
los roles vigentes en la base (RN-04).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import AdminDep, SessionDep, UsuarioActual
from app.core.paginacion import Page, PageParamsDep
from app.modules.usuarios import service
from app.modules.usuarios.schemas import (
    EventoLeer,
    MensajeRespuesta,
    RolAsignar,
    RolLeer,
    UsuarioCrear,
    UsuarioLeer,
)
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])
# ``GET /eventos`` no comparte el prefijo ``/usuarios``: router propio, montado
# en el mismo grupo protegido y con la misma exigencia de ADMIN.
eventos_router = APIRouter(prefix="/eventos", tags=["Seguridad"])


async def get_uow(session: AsyncSession = SessionDep) -> UsuariosUnitOfWork:
    """Arma el UoW del módulo con la sesión de la petición, sin abrirlo."""
    return UsuariosUnitOfWork(session)


UoWDep = Annotated[UsuariosUnitOfWork, Depends(get_uow)]


@router.post(
    "",
    response_model=UsuarioLeer,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de personal con contraseña provisoria (ADMIN)",
)
async def crear_usuario(
    uow: UoWDep,
    datos: UsuarioCrear,
    actual: UsuarioActual = AdminDep,
) -> UsuarioLeer:
    usuario = await service.crear(
        uow, datos, actor=service.actor_de(actual.usuario)
    )
    return UsuarioLeer.model_validate(usuario)


@router.get(
    "/{usuario_id}/roles",
    response_model=list[RolLeer],
    status_code=status.HTTP_200_OK,
    summary="Historial de roles de un usuario (ADMIN)",
)
async def listar_roles(
    uow: UoWDep,
    usuario_id: int,
    actual: UsuarioActual = AdminDep,
) -> list[RolLeer]:
    asignaciones = await service.listar_roles(uow, usuario_id)
    return [RolLeer.de_asignacion(asignacion) for asignacion in asignaciones]


@router.post(
    "/{usuario_id}/roles",
    response_model=RolLeer,
    status_code=status.HTTP_201_CREATED,
    summary="Asignación de un rol con vigencia opcional (ADMIN)",
)
async def asignar_rol(
    uow: UoWDep,
    usuario_id: int,
    datos: RolAsignar,
    actual: UsuarioActual = AdminDep,
) -> RolLeer:
    asignacion = await service.asignar_rol(
        uow, usuario_id, datos, actor=service.actor_de(actual.usuario)
    )
    return RolLeer.de_asignacion(asignacion)


@router.delete(
    "/{usuario_id}/roles/{rol}",
    response_model=MensajeRespuesta,
    status_code=status.HTTP_200_OK,
    summary="Revocación de un rol: escribe revocada_en, no borra (ADMIN)",
)
async def revocar_rol(
    uow: UoWDep,
    usuario_id: int,
    rol: str,
    actual: UsuarioActual = AdminDep,
) -> MensajeRespuesta:
    await service.revocar_rol(uow, usuario_id, rol, admin=actual.usuario)
    return MensajeRespuesta(mensaje=f"Rol {rol} revocado.")


@eventos_router.get(
    "",
    response_model=Page[EventoLeer],
    status_code=status.HTTP_200_OK,
    summary="Historial de eventos de seguridad, paginado (ADMIN)",
)
async def listar_eventos(
    uow: UoWDep,
    params: PageParamsDep,
    actual: UsuarioActual = AdminDep,
) -> Page[EventoLeer]:
    pagina = await service.listar_eventos(uow, params)
    return Page[EventoLeer](
        items=[EventoLeer.model_validate(evento) for evento in pagina.items],
        total=pagina.total,
        page=pagina.page,
        size=pagina.size,
        pages=pagina.pages,
    )
