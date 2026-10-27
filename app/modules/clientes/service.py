"""Servicios del módulo de clientes (Épica 6, US-017 a US-019).

El router arma el UoW con una dependencia y lo pasa **cerrado**; el servicio lo
abre con ``async with`` (regla dura). Ningún repositorio confirma.

- ``crear_cliente``: la unicidad de ``documento`` la garantiza el UNIQUE de la
  base. Si choca, el ``IntegrityError`` sube y el handler central responde 409
  con mensaje propio (RN-01/RN-18): no hay consulta previa de unicidad.
- ``obtener_ficha``: el repositorio precarga los vehículos vigentes con
  ``selectinload``; el servicio nunca toca una relación sin cargar (las
  relaciones son ``lazy="raise_on_sql"``).
- ``crear_vehiculo``: 404 si el cliente de la ruta no existe; la patente
  vigente repetida es 409 del índice único parcial (caso C-19 al revés: una
  patente **dada de baja** no ocupa el índice).
- ``dar_de_baja_vehiculo``: baja lógica con ``soft_delete`` (escribe
  ``borrado_en``, no borra la fila) y 409 si el vehículo tiene órdenes abiertas
  (RN-16), decidido con un ``SELECT`` del repositorio.
- ``listar_mis_vehiculos``: lo propio (RN-17). La ficha se ubica por
  ``Cliente.usuario_id``; si la cuenta no tiene ficha, la respuesta es una
  lista vacía (no es un error).
"""

from __future__ import annotations

from app.core.errors import Conflicto, RecursoNoEncontrado
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.clientes.schemas import ClienteCrear, VehiculoCrear
from app.modules.clientes.unit_of_work import ClientesUnitOfWork

MENSAJE_ORDENES_ABIERTAS = (
    "El vehículo tiene órdenes abiertas: no se puede dar de baja."
)


async def crear_cliente(uow: ClientesUnitOfWork, datos: ClienteCrear) -> Cliente:
    """Alta de una ficha de cliente (ADMIN/RECEPCION)."""
    cliente = Cliente(**datos.model_dump())

    async with uow:
        return await uow.clientes.add(cliente)


async def obtener_ficha(uow: ClientesUnitOfWork, cliente_id: int) -> Cliente:
    """Ficha con sus vehículos vigentes o 404 con mensaje propio."""
    async with uow:
        cliente = await uow.clientes.get_ficha(cliente_id)

    if cliente is None:
        raise RecursoNoEncontrado("el cliente", cliente_id)
    return cliente


async def crear_vehiculo(
    uow: ClientesUnitOfWork,
    cliente_id: int,
    datos: VehiculoCrear,
) -> Vehiculo:
    """Alta de un vehículo del cliente de la ruta (ADMIN/RECEPCION).

    El cliente se lee **dentro** del mismo UoW: si no existe, la excepción
    revierte y no queda ninguna fila a medio escribir.
    """
    async with uow:
        cliente = await uow.clientes.get_by_id(cliente_id)
        if cliente is None:
            raise RecursoNoEncontrado("el cliente", cliente_id)

        vehiculo = Vehiculo(cliente_id=cliente_id, **datos.model_dump())
        return await uow.vehiculos.add(vehiculo)


async def dar_de_baja_vehiculo(uow: ClientesUnitOfWork, vehiculo_id: int) -> None:
    """Baja lógica del vehículo (ADMIN/RECEPCION).

    Escribe ``borrado_en`` y conserva la fila (RN-16). Con órdenes **abiertas**
    —en un estado que el catálogo no marca final— responde 409 y no escribe
    nada: la comprobación corre antes de la baja.
    """
    async with uow:
        vehiculo = await uow.vehiculos.get_by_id(vehiculo_id)
        if vehiculo is None:
            raise RecursoNoEncontrado("el vehículo", vehiculo_id)

        if await uow.vehiculos.tiene_ordenes_abiertas(vehiculo_id):
            raise Conflicto(MENSAJE_ORDENES_ABIERTAS)

        await uow.vehiculos.soft_delete(vehiculo_id)


async def listar_mis_vehiculos(
    uow: ClientesUnitOfWork, usuario_id: int
) -> list[Vehiculo]:
    """Vehículos vigentes del cliente dueño de la sesión (RN-17).

    Sin ``requiere_rol``: sólo pide estar autenticado. Si la cuenta no tiene
    ficha de cliente devuelve una lista vacía; nunca un 404 (no se pidió un
    recurso por id) ni un 500.
    """
    async with uow:
        cliente = await uow.clientes.get_by_usuario_id(usuario_id)

    if cliente is None:
        return []
    # ``vehiculos`` viene precargado por el repositorio: ningún acceso perezoso.
    return list(cliente.vehiculos)
