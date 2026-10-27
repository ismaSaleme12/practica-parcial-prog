"""Registro central de los modelos del dominio.

Alembic (``C-04``) importa **este módulo** en su ``env.py`` para que el metadata
conozca las trece tablas y las relaciones se resuelvan entre módulos.

Los modelos se reparten por dominio (``app/modules/<dominio>/models.py``) para
que cada módulo sea dueño de sus tablas, pero las relaciones cruzan módulos: por
eso las anotaciones se declaran como cadenas y sólo se importan bajo
``TYPE_CHECKING``. Sin este punto único, importar un solo módulo dejaría las
relaciones sin resolver («expression 'Cliente' failed to locate a name»).
"""

from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.ordenes.models import (
    EstadoOrden,
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)
from app.modules.repuestos.models import (
    HistorialPrecioRepuesto,
    MovimientoStock,
    Repuesto,
)
from app.modules.usuarios.models import (
    AsignacionRol,
    EventoSeguridad,
    IntentoAcceso,
    Usuario,
)

__all__ = [
    "AsignacionRol",
    "Cliente",
    "EstadoOrden",
    "EventoSeguridad",
    "HistorialEstadoOrden",
    "HistorialPrecioRepuesto",
    "IntentoAcceso",
    "ItemOrden",
    "MovimientoStock",
    "OrdenTrabajo",
    "Repuesto",
    "Usuario",
    "Vehiculo",
]
