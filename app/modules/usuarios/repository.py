"""Repositorios del dominio de identidad y accesos.

Todos heredan ``BaseRepository``: ``add``/``update`` hacen ``flush()`` y nada
más (el UoW es el único punto de confirmación). Las consultas usan expresiones
ligadas: ningún filtro se arma por concatenación de SQL.

Reglas que este módulo respeta:

- ``UsuarioRepository.get_by_email`` busca el correo como **parámetro ligado**.
- ``AsignacionRolRepository.roles_vigentes`` aplica la definición de vigencia de
  RN-04: no revocada (``revocada_en IS NULL``) y sin vencer (``vence_en`` nulo o
  futuro). Se consulta en **cada** petición: los roles del token son informativos.
- ``IntentoAccesoRepository`` alimenta el límite de intentos de login (RN-08):
  cuenta los fallos de los últimos 60 s con el mismo ``(email, ip)`` **después del
  último login correcto**, con lo que un login correcto reinicia la cuenta sin
  borrar las filas viejas.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.repository import BaseRepository
from app.modules.usuarios.models import (
    AsignacionRol,
    EventoSeguridad,
    IntentoAcceso,
    Usuario,
)


class UsuarioRepository(BaseRepository[Usuario]):
    """Acceso a la tabla ``usuario``."""

    _orden_por = (Usuario.id,)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Usuario)

    async def get_by_email(self, email: str) -> Usuario | None:
        """Usuario por correo (parámetro ligado) o ``None`` si no existe."""
        statement = select(Usuario).where(Usuario.email == email)
        return (await self.session.exec(statement)).first()


class AsignacionRolRepository(BaseRepository[AsignacionRol]):
    """Acceso a ``asignacion_rol`` (historial de roles con vigencia)."""

    _orden_por = (AsignacionRol.id,)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AsignacionRol)

    async def roles_vigentes(
        self,
        usuario_id: int,
        ahora: datetime | None = None,
    ) -> list[str]:
        """Roles vigentes del usuario, en el orden en que se otorgaron.

        Vigente = la fila no está revocada y no venció (RN-04). Se consulta en
        la base en cada petición, nunca desde el token.
        """
        momento = ahora or datetime.now(timezone.utc)
        statement = (
            select(AsignacionRol.rol)
            .where(
                AsignacionRol.usuario_id == usuario_id,
                AsignacionRol.revocada_en.is_(None),
                or_(
                    AsignacionRol.vence_en.is_(None),
                    AsignacionRol.vence_en > momento,
                ),
            )
            .order_by(AsignacionRol.id)
        )
        return list((await self.session.exec(statement)).all())

    async def listar_por_usuario(self, usuario_id: int) -> list[AsignacionRol]:
        """Todas las asignaciones del usuario, incluidas revocadas y vencidas.

        El historial no se borra nunca: ``GET /usuarios/{id}/roles`` devuelve
        también las filas cerradas para auditar quién tuvo qué rol y hasta
        cuándo (US-014).
        """
        statement = (
            select(AsignacionRol)
            .where(AsignacionRol.usuario_id == usuario_id)
            .order_by(AsignacionRol.id)
        )
        return list((await self.session.exec(statement)).all())

    async def get_abierta(
        self, usuario_id: int, rol: str
    ) -> AsignacionRol | None:
        """Fila con ``revocada_en IS NULL`` para ``(usuario_id, rol)``.

        Puede estar **vencida**: el índice único parcial sólo mira
        ``revocada_en``, así que una fila vencida sigue ocupando el lugar y hay
        que cerrarla antes de abrir la nueva (RN-03 / US-014 CA-2). Que exista
        una fila abierta y **vigente** no se checa acá para responder 409: eso
        lo garantiza la base al insertar.
        """
        statement = select(AsignacionRol).where(
            AsignacionRol.usuario_id == usuario_id,
            AsignacionRol.rol == rol,
            AsignacionRol.revocada_en.is_(None),
        )
        return (await self.session.exec(statement)).first()

    async def contar_vigentes(
        self,
        rol: str,
        ahora: datetime | None = None,
    ) -> int:
        """Cantidad de asignaciones **vigentes** de un rol (autoprotección RN-05)."""
        momento = ahora or datetime.now(timezone.utc)
        statement = (
            select(func.count(AsignacionRol.id))
            .where(
                AsignacionRol.rol == rol,
                AsignacionRol.revocada_en.is_(None),
                or_(
                    AsignacionRol.vence_en.is_(None),
                    AsignacionRol.vence_en > momento,
                ),
            )
        )
        result = await self.session.execute(statement)
        return int(result.scalar_one())


class IntentoAccesoRepository(BaseRepository[IntentoAcceso]):
    """Acceso a ``intento_acceso`` (límite de intentos de login, RN-08).

    Las escrituras de este repositorio se hacen desde una sesión y una
    transacción **propias**, siempre confirmadas (DD-09). El repositorio no
    cambia esa regla: sigue sin confirmar; confirma el UoW de esa sesión.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, IntentoAcceso)

    async def ultimo_exito(self, email: str, ip: str) -> datetime | None:
        """Marca del último login correcto de ese ``(email, ip)``."""
        statement = select(func.max(IntentoAcceso.cuando)).where(
            IntentoAcceso.email == email,
            IntentoAcceso.ip == ip,
            IntentoAcceso.exito.is_(True),
        )
        return (await self.session.execute(statement)).scalar_one()

    async def contar_fallos(
        self,
        email: str,
        ip: str,
        *,
        desde: datetime,
        despues_de: datetime | None = None,
    ) -> tuple[int, datetime | None]:
        """Cuenta fallos y devuelve el más antiguo de la ventana.

        ``desde`` es el inicio de la ventana de 60 s. ``despues_de`` es la marca
        del último login correcto: los fallos anteriores dejan de contar sin
        borrarse de la tabla (RN-08).
        """
        condiciones = [
            IntentoAcceso.email == email,
            IntentoAcceso.ip == ip,
            IntentoAcceso.exito.is_(False),
            IntentoAcceso.cuando >= desde,
        ]
        if despues_de is not None:
            condiciones.append(IntentoAcceso.cuando > despues_de)

        statement = select(
            func.count(IntentoAcceso.id),
            func.min(IntentoAcceso.cuando),
        ).where(*condiciones)
        total, mas_antiguo = (await self.session.execute(statement)).one()
        return int(total or 0), mas_antiguo


class EventoSeguridadRepository(BaseRepository[EventoSeguridad]):
    """Acceso a ``evento_seguridad`` (auditoría de altas y cambios)."""

    _orden_por = (EventoSeguridad.id,)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EventoSeguridad)
