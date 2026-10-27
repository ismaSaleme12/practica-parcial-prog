from typing import Generic, TypeVar, Sequence
from pydantic import BaseModel, model_validator
from fastapi import HTTPException, status

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = 1
    size: int = 20

    @model_validator(mode="after")
    def validate_params(self) -> "PageParams":
        if self.page < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El número de página debe ser mayor o igual a 1."
            )
        if self.size < 1 or self.size > 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El tamaño de página debe estar entre 1 y 100."
            )
        return self


class Page(BaseModel, Generic[T]):
    items: Sequence[T]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def create(cls, items: Sequence[T], total: int, params: PageParams) -> "Page[T]":
        pages = (total + params.size - 1) // params.size if params.size > 0 else 0
        if pages > 0 and params.page > pages:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"La página {params.page} excede el total de páginas disponibles ({pages})."
            )
        return cls(
            items=items,
            total=total,
            page=params.page,
            size=params.size,
            pages=pages
        )
