"""Unit of Work base.

Reglas duras que este módulo implementa:

- **Ningún servicio construye su UoW**: el router lo arma con una dependencia y
  se lo pasa al servicio, que lo abre con ``async with``.
- **El UoW no cierra la sesión**: no la creó. La sesión pertenece a la petición.
- **Un solo punto de confirmación**: al salir sin excepción confirma; con
  excepción revierte. Los repositorios nunca confirman.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, TypeVar

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.repository import BaseRepository

Repo = TypeVar("Repo", bound=BaseRepository[Any])


class UnitOfWork:
    """Gestor de contexto asincrónico que delimita una transacción de negocio.

    Uso esperado en un servicio::

        async with uow:
            await uow.repositorio(ClienteRepository, Cliente).add(cliente)
            await uow.repositorio(EventoRepository, EventoSeguridad).add(evento)

    Los módulos de dominio heredan de esta clase y declaran sus repositorios
    concretos; la sesión es siempre la misma para todos.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> "UnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        # Sale con excepción: se revierte todo y la excepción sigue su curso
        # (devolver None desde __aexit__ no la silencia).
        if exc_type is not None:
            await self.session.rollback()
            return

        try:
            await self.session.commit()
        except Exception:
            # Un commit fallido no puede quedar como éxito: se revierte y se relanza.
            await self.session.rollback()
            raise
        # La sesión NO se cierra acá: pertenece a la petición que la abrió.

    def repositorio(self, repositorio_cls: type[Repo], model: type[Any]) -> Repo:
        """Compone un repositorio sobre la sesión compartida del UoW."""
        return repositorio_cls(self.session, model)
