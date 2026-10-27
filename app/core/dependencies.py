from fastapi import Depends

from app.core.database import get_session

# Dependencia de sesión lista para usar en los routers:
#     async def handler(session: AsyncSession = SessionDep) -> ...
SessionDep = Depends(get_session)
