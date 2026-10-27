from typing import Generic, TypeVar, Type, Optional, Sequence, Any
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

T = TypeVar("T", bound=SQLModel)


class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model: Type[T]):
        self.session = session
        self.model = model

    async def get_by_id(self, id: Any) -> Optional[T]:
        return await self.session.get(self.model, id)

    async def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[T]:
        statement = select(self.model).offset(skip).limit(limit)
        result = await self.session.exec(statement)
        return result.all()

    async def add(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def update(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, id: Any) -> bool:
        entity = await self.get_by_id(id)
        if not entity:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True


class SoftDeleteRepository(BaseRepository[T], Generic[T]):
    async def get_by_id(self, id: Any) -> Optional[T]:
        entity = await super().get_by_id(id)
        if entity and getattr(entity, "borrado_en", None) is not None:
            return None
        return entity

    async def get_by_id_including_deleted(self, id: Any) -> Optional[T]:
        return await super().get_by_id(id)

    async def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[T]:
        statement = select(self.model).where(self.model.borrado_en == None).offset(skip).limit(limit)  # type: ignore[attr-defined]
        result = await self.session.exec(statement)
        return result.all()

    async def soft_delete(self, id: Any) -> Optional[T]:
        entity = await self.get_by_id_including_deleted(id)
        if not entity or getattr(entity, "borrado_en", None) is not None:
            return None
        entity.borrado_en = datetime.now(timezone.utc)  # type: ignore[attr-defined]
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity
