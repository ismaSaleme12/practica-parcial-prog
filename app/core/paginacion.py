"""Envoltorio uniforme de paginación.

Todo listado de la API responde ``{items, total, page, size, pages}``.
``page`` empieza en 1, ``size`` va de 1 a 100 (default 20) y pedir una página
más allá de la última responde 422 con un mensaje propio.
"""

from __future__ import annotations

import math
from typing import Annotated, Generic, Sequence, TypeVar

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, model_validator

T = TypeVar("T")

# Literal a propósito: el nombre del status en Starlette cambió entre versiones
# (422 pasó de UNPROCESSABLE_ENTITY a UNPROCESSABLE_CONTENT) y el código es el mismo.
HTTP_422 = 422

_PAGE_MIN = 1
_SIZE_MIN = 1
_SIZE_MAX = 100
_SIZE_DEFAULT = 20


class PageParams(BaseModel):
    """Parámetros ``page``/``size`` validados (422 con mensaje propio)."""

    page: int = _PAGE_MIN
    size: int = _SIZE_DEFAULT

    @model_validator(mode="after")
    def _validar_rangos(self) -> "PageParams":
        if self.page < _PAGE_MIN:
            raise HTTPException(
                status_code=HTTP_422,
                detail=f"El número de página debe ser mayor o igual a {_PAGE_MIN}.",
            )
        if self.size < _SIZE_MIN or self.size > _SIZE_MAX:
            raise HTTPException(
                status_code=HTTP_422,
                detail=(
                    f"El tamaño de página debe estar entre {_SIZE_MIN} y {_SIZE_MAX}."
                ),
            )
        return self

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


class Page(BaseModel, Generic[T]):
    """Envoltorio de respuesta de un listado paginado."""

    items: list[T]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def create(
        cls,
        items: Sequence[T],
        total: int,
        params: PageParams,
    ) -> "Page[T]":
        pages = math.ceil(total / params.size) if params.size > 0 else 0
        if pages > 0 and params.page > pages:
            raise HTTPException(
                status_code=HTTP_422,
                detail=f"La página {params.page} no existe: hay {pages}.",
            )
        return cls(
            items=list(items),
            total=total,
            page=params.page,
            size=params.size,
            pages=pages,
        )


def page_params(
    page: Annotated[int, Query(description="Página solicitada, empieza en 1.")] = _PAGE_MIN,
    size: Annotated[
        int, Query(description=f"Tamaño de página, entre {_SIZE_MIN} y {_SIZE_MAX}.")
    ] = _SIZE_DEFAULT,
) -> PageParams:
    """Dependencia de FastAPI que arma y valida ``PageParams`` desde el query string.

    No se usan ``ge``/``le`` en ``Query`` a propósito: la validación (y el
    mensaje de error propio) vive en ``PageParams``, así todos los listados
    responden el mismo 422 aunque FastAPI cambie su formato.
    """
    return PageParams(page=page, size=size)


PageParamsDep = Annotated[PageParams, Depends(page_params)]
