"""Router del módulo de usuarios (prototipo de contratos de `C-06`).

Endpoint de este change:

- ``POST /usuarios``: 201, contraseña provisoria (`debe_cambiar_password`) y
  respuesta **sin** ``password_hash``.

**Provisional**: todavía no hay autenticación. `C-08` mueve este router al grupo
protegido y le agrega ``requiere_rol(ADMIN)``, la asignación de rol y el evento
de seguridad.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import SessionDep
from app.modules.usuarios import service
from app.modules.usuarios.schemas import UsuarioCrear, UsuarioLeer
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


async def get_uow(session: AsyncSession = SessionDep) -> UsuariosUnitOfWork:
    """Arma el UoW del módulo con la sesión de la petición, sin abrirlo."""
    return UsuariosUnitOfWork(session)


UoWDep = Annotated[UsuariosUnitOfWork, Depends(get_uow)]


@router.post(
    "",
    response_model=UsuarioLeer,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de usuario con contraseña provisoria",
)
async def crear_usuario(uow: UoWDep, datos: UsuarioCrear) -> UsuarioLeer:
    usuario = await service.crear(uow, datos)
    return UsuarioLeer.model_validate(usuario)
