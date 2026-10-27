"""Router del módulo de clientes (Épica 6, US-017 a US-019).

Tres routers, todos en el grupo **protegido** de ``main.py`` (que aporta el 401
de la sesión y el 403 del cambio obligatorio, montados una sola vez):

- ``router`` (``/clientes``):
  - ``POST /clientes`` — ADMIN, RECEPCION → 201/409/422.
  - ``GET /clientes/{id}`` — ADMIN, RECEPCION → 200 con los vehículos vigentes
    precargados (sin carga perezosa) / 404.
  - ``POST /clientes/{id}/vehiculos`` — ADMIN, RECEPCION → 201/404/409/422.
- ``vehiculos_router`` (``/vehiculos``):
  - ``DELETE /vehiculos/{id}`` — ADMIN, RECEPCION → 204 (baja lógica) / 404/
    409 si tiene órdenes abiertas.
- ``propios_router`` (``/mis-vehiculos``):
  - ``GET /mis-vehiculos`` — cualquier sesión válida, **sin** ``requiere_rol``
    (RN-17): sólo los vehículos del cliente dueño de la sesión.

Los permisos salen de la matriz de ``03_actores_y_roles.md``. ``requiere_rol``
consulta los roles vigentes en la base en cada petición (RN-04).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.dependencies import (
    SessionDep,
    UsuarioActual,
    UsuarioActualDep,
    requiere_rol,
)
from app.modules.clientes import service
from app.modules.clientes.schemas import (
    ClienteCrear,
    ClienteFicha,
    ClienteLeer,
    VehiculoCrear,
    VehiculoLeer,
)
from app.modules.clientes.unit_of_work import ClientesUnitOfWork

router = APIRouter(prefix="/clientes", tags=["Clientes"])
vehiculos_router = APIRouter(prefix="/vehiculos", tags=["Clientes"])
# ``GET /mis-vehiculos`` no comparte prefijo con los otros dos: es el router de
# «lo propio» (RN-17) y no lleva ``requiere_rol``, sólo sesión válida.
propios_router = APIRouter(tags=["Clientes"])

# La matriz concede estas rutas a ADMIN y RECEPCION. El alias vive acá y no en
# ``app/core/dependencies.py`` porque es una necesidad local del módulo:
# ``PersonalDep`` incluye MECANICO y estas rutas no lo admiten.
AtencionDep = Depends(requiere_rol("ADMIN", "RECEPCION"))


async def get_uow(session: AsyncSession = SessionDep) -> ClientesUnitOfWork:
    """Arma el UoW del módulo con la sesión de la petición, sin abrirlo."""
    return ClientesUnitOfWork(session)


UoWDep = Annotated[ClientesUnitOfWork, Depends(get_uow)]


@router.post(
    "",
    response_model=ClienteLeer,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de cliente (ADMIN, RECEPCION)",
)
async def crear_cliente(
    uow: UoWDep,
    datos: ClienteCrear,
    actual: UsuarioActual = AtencionDep,
) -> ClienteLeer:
    cliente = await service.crear_cliente(uow, datos)
    return ClienteLeer.model_validate(cliente)


@router.get(
    "/{cliente_id}",
    response_model=ClienteFicha,
    status_code=status.HTTP_200_OK,
    summary="Ficha del cliente con sus vehículos vigentes (ADMIN, RECEPCION)",
)
async def obtener_ficha(
    uow: UoWDep,
    cliente_id: int,
    actual: UsuarioActual = AtencionDep,
) -> ClienteFicha:
    cliente = await service.obtener_ficha(uow, cliente_id)
    return ClienteFicha.model_validate(cliente)


@router.post(
    "/{cliente_id}/vehiculos",
    response_model=VehiculoLeer,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de un vehículo del cliente (ADMIN, RECEPCION)",
)
async def crear_vehiculo(
    uow: UoWDep,
    cliente_id: int,
    datos: VehiculoCrear,
    actual: UsuarioActual = AtencionDep,
) -> VehiculoLeer:
    vehiculo = await service.crear_vehiculo(uow, cliente_id, datos)
    return VehiculoLeer.model_validate(vehiculo)


@vehiculos_router.delete(
    "/{vehiculo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Baja lógica de un vehículo (ADMIN, RECEPCION)",
)
async def dar_de_baja_vehiculo(
    uow: UoWDep,
    vehiculo_id: int,
    actual: UsuarioActual = AtencionDep,
) -> Response:
    await service.dar_de_baja_vehiculo(uow, vehiculo_id)
    # 204 sin cuerpo: FastAPI no admite un ``response_model`` para este status.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@propios_router.get(
    "/mis-vehiculos",
    response_model=list[VehiculoLeer],
    status_code=status.HTTP_200_OK,
    summary="Vehículos del cliente dueño de la sesión (cualquier rol)",
)
async def listar_mis_vehiculos(
    uow: UoWDep,
    actual: UsuarioActual = UsuarioActualDep,
) -> list[VehiculoLeer]:
    vehiculos = await service.listar_mis_vehiculos(uow, actual.usuario.id)
    return [VehiculoLeer.model_validate(vehiculo) for vehiculo in vehiculos]
