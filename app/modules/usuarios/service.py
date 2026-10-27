"""Servicios del módulo de usuarios (prototipo de contratos de `C-06`).

Alcance: alta de usuario con contraseña provisoria. `C-07` agrega registro,
login, logout y cambio de contraseña; `C-08` agrega la autorización ADMIN, la
asignación de rol y el evento de seguridad.
"""

from __future__ import annotations

from app.core.security import hash_password
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.schemas import UsuarioCrear
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork


async def crear(uow: UsuariosUnitOfWork, datos: UsuarioCrear) -> Usuario:
    """Crea el usuario con contraseña provisoria.

    El hash se calcula **antes** de abrir la transacción (regla dura): dentro,
    la conexión quedaría tomada los ~300 ms de bcrypt sin usar la base.
    """
    password_hash = await hash_password(datos.password)

    usuario = Usuario(
        email=datos.email,
        nombre=datos.nombre,
        password_hash=password_hash,
        debe_cambiar_password=True,
    )

    async with uow:
        return await uow.usuarios.add(usuario)
