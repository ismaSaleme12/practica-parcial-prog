from collections.abc import AsyncGenerator

from fastapi import Request
from sqlmodel.ext.asyncio.session import AsyncSession


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Entrega una sesión por petición tomada de la fábrica del lifespan.

    La sesión se crea en el lifespan (``app.state.session_maker``) y se cierra
    aquí, al terminar la petición. ``expire_on_commit=False`` evita que los
    objetos queden expirados después del commit y disparen lecturas implícitas.
    """
    session_maker = request.app.state.session_maker
    async with session_maker() as session:
        yield session
