"""Manejo central de errores (RN-18).

Reglas duras que este módulo implementa:

- **Ningún error devuelve texto interno de la base**: un ``IntegrityError`` se
  traduce a **409 con mensaje propio**. No se lee ``exc.orig`` ni el texto del
  motor (está en el idioma configurado del servidor y contiene nombres de
  tablas, índices y valores: el mapa del esquema).
- **Ninguna entrada inválida termina en 500**: el ``RequestValidationError`` de
  Pydantic responde 422 con mensaje propio y la lista de campos; un ``DataError``
  del motor (formato o longitud que el contrato no pudo anticipar) también.
- **Los servicios no atrapan ``IntegrityError``**: lo dejan subir; el
  ``UnitOfWork`` revierte la transacción al salir con excepción y este handler
  emite la respuesta. Cuando el servicio **conoce** la regla, lanza ``Conflicto``
  (409) o ``RecursoNoEncontrado`` (404) con su propio mensaje.

Los handlers se registran una sola vez desde ``main.py`` con
``registrar_manejadores(app)``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

# Literales a propósito: el nombre del status 422 cambió entre versiones de
# Starlette (UNPROCESSABLE_ENTITY → UNPROCESSABLE_CONTENT) y el código es el mismo.
STATUS_CONFLICTO = 409
STATUS_VALIDACION = 422

MENSAJE_CONFLICTO = "La operación entra en conflicto con datos ya guardados."
MENSAJE_VALIDACION = "La petición no cumple el contrato."
MENSAJE_DATOS = "Alguno de los datos enviados no es válido para el sistema."
MENSAJE_RUTA = "La ruta solicitada no existe."


class Conflicto(HTTPException):
    """409 con mensaje propio para una regla de negocio que el servicio conoce."""

    def __init__(self, mensaje: str = MENSAJE_CONFLICTO) -> None:
        super().__init__(status_code=STATUS_CONFLICTO, detail=mensaje)


class RecursoNoEncontrado(HTTPException):
    """404 con mensaje propio cuando el id de la ruta no corresponde a nada."""

    def __init__(self, recurso: str, id: Any) -> None:
        super().__init__(status_code=404, detail=f"No existe {recurso} con id {id}.")


def _errores_de_validacion(exc: RequestValidationError) -> list[dict[str, str]]:
    """Resume los errores de Pydantic sin ``ctx`` (puede traer objetos no serializables)."""
    errores: list[dict[str, str]] = []
    for error in exc.errors():
        mensaje = str(error.get("msg", "Valor inválido")).removeprefix("Value error, ")
        errores.append(
            {
                "campo": ".".join(str(parte) for parte in error.get("loc", ())),
                "mensaje": mensaje,
                "tipo": str(error.get("type", "valor_invalido")),
            }
        )
    return errores


async def _integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    """Traduce cualquier violación de integridad a 409 sin filtrar el esquema."""
    return JSONResponse(
        status_code=STATUS_CONFLICTO,
        content={"detail": MENSAJE_CONFLICTO},
    )


async def _data_error_handler(request: Request, exc: DataError) -> JSONResponse:
    """Datos que la base rechaza por formato/longitud: 422, nunca una traza."""
    return JSONResponse(
        status_code=STATUS_VALIDACION,
        content={"detail": MENSAJE_DATOS},
    )


async def _request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422 con mensaje propio y la lista de campos que no cumplieron el contrato."""
    return JSONResponse(
        status_code=STATUS_VALIDACION,
        content={
            "detail": MENSAJE_VALIDACION,
            "errores": _errores_de_validacion(exc),
        },
    )


async def _http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    """Conserva el ``detail`` propio que lanzó el servicio o la paginación."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


async def _starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Uniforma el cuerpo de los errores HTTP y traduce el 404 de ruta."""
    detalle = exc.detail
    if exc.status_code == 404 and detalle in (None, "Not Found"):
        detalle = MENSAJE_RUTA
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detalle},
        headers=getattr(exc, "headers", None),
    )


def registrar_manejadores(app: FastAPI) -> None:
    """Registra todos los handlers. Se llama una sola vez, al construir la app."""
    app.add_exception_handler(IntegrityError, _integrity_error_handler)
    app.add_exception_handler(DataError, _data_error_handler)
    app.add_exception_handler(
        RequestValidationError, _request_validation_error_handler
    )
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(
        StarletteHTTPException, _starlette_http_exception_handler
    )
