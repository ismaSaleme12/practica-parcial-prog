# Proposal

## Why

`C-08` dejó la autorización resuelta: hay dos grupos de rutas, `requiere_rol` decide en la base en cada petición y el grupo protegido aporta el 401 y el 403 del cambio obligatorio. Pero el dominio del taller sigue sin endpoints: las tablas `cliente` y `vehiculo` existen desde `C-03`/`C-04`, y `ClienteRepository` sólo se usa para la ficha que crea el auto-registro de `C-07`. Hoy **no hay forma de abrir una orden real**: recepción no puede dar de alta a un cliente ni a su vehículo, y el comprador de un auto vendido no puede registrar la misma patente.

La Épica 6 pide cuatro reglas que sólo se sostienen juntas:

1. **Unicidad garantizada por la base** (RN-01): `cliente.documento` es UNIQUE y `vehiculo.patente` es único **entre los vigentes** por un índice único parcial `WHERE borrado_en IS NULL`. Una consulta previa de unicidad no sólo está prohibida por las reglas duras: sería una carrera y, en el caso de la patente, rompería el caso C-19.
2. **Carga anticipada** (regla dura, requisito no funcional): las relaciones usan `lazy="raise_on_sql"`; la ficha del cliente **con sus vehículos** tiene que resolverse con `selectinload` en el repositorio, con un número fijo de consultas. Un acceso perezoso lanza, no dispara SQL escondido.
3. **Baja lógica con precondición de negocio** (RN-16): dar de baja un vehículo escribe `borrado_en` y conserva la fila y sus órdenes; un vehículo con órdenes **abiertas** (`estado_orden.es_final = false`) responde 409 sin escribir nada.
4. **Lo propio** (RN-17): `GET /mis-vehiculos` sólo pide estar autenticado y devuelve únicamente los vehículos del cliente dueño de la sesión (`Cliente.usuario_id`). Una cuenta sin ficha de cliente recibe una lista vacía, no un 404 ni un 500.

Sin este change, `C-11 ordenes-trabajo` no puede empezar: el alta de una orden exige un `vehiculo_id` válido y vigente que hoy nadie puede crear por la API.

## What Changes

- **`app/modules/clientes/schemas.py`** (nuevo): `ClienteCrear`, `VehiculoCrear`, `ClienteLeer` (ficha plana del alta), `ClienteFicha` (con `vehiculos`) y `VehiculoLeer`. Entradas con `extra="forbid"`; `anio` con los límites del CHECK (1950–2100) para que fuera de rango sea **422** y no un 409 de integridad.
- **`app/modules/clientes/repository.py`** (extendido):
  - `ClienteRepository.get_ficha`: cliente con sus vehículos **vigentes** precargados con `selectinload(Cliente.vehiculos.and_(Vehiculo.borrado_en.is_(None)))` (dos consultas fijas).
  - `ClienteRepository.get_by_usuario_id`: la ficha dueña de una cuenta de sesión, con la misma precarga (o `None` sin ficha).
  - `VehiculoRepository(SoftDeleteRepository[Vehiculo])` nuevo: lecturas sólo de vigentes, `soft_delete` y `tiene_ordenes_abiertas` (un `SELECT ... LIMIT 1` propio que cruza `orden_trabajo` con el catálogo por `es_final`). El servicio no importa lógica del módulo `ordenes`.
- **`app/modules/clientes/unit_of_work.py`** (nuevo): `ClientesUnitOfWork` con `clientes` y `vehiculos` sobre la misma sesión.
- **`app/modules/clientes/service.py`** (nuevo): `crear_cliente`, `obtener_ficha`, `crear_vehiculo`, `dar_de_baja_vehiculo` y `listar_mis_vehiculos`. Ninguna comprobación de unicidad previa; 404/409 con `RecursoNoEncontrado`/`Conflicto`; el UoW se abre con `async with`.
- **`app/modules/clientes/router.py`** (nuevo): tres routers por prefijo (`/clientes`, `/vehiculos` y `/mis-vehiculos`), como el `eventos_router` de `usuarios`. `POST /clientes`, `GET /clientes/{id}`, `POST /clientes/{id}/vehiculos` y `DELETE /vehiculos/{id}` exigen ADMIN o RECEPCION; `GET /mis-vehiculos` sólo sesión válida.
- **`main.py`**: los tres routers se montan en el grupo **protegido** (cambio aditivo: no se reordena ni se reescribe lo existente).
- **Evidencia**: `test/clientes.http` (con bloque 0 de login, porque las rutas están en el grupo protegido) y `test/test_clientes.py` (14 tests) como réplica automatizada.

## Capabilities

### New Capabilities

- `customer-management`: alta de cliente con documento único y ficha con sus vehículos vigentes resueltos por carga anticipada en el repositorio.
- `vehicle-lifecycle`: alta de vehículo con año validado y patente única entre vigentes, baja lógica con `borrado_en`, bloqueo por órdenes abiertas y reutilización de la patente después de la baja (caso C-19).
- `own-resources`: `GET /mis-vehiculos` acotado al cliente dueño de la sesión, sin `requiere_rol`, con lista vacía para cuentas sin ficha.

### Modified Capabilities

- Ninguna. Se reutilizan sin cambios `request-contracts` y `error-handling` (`C-06`: `extra="forbid"`, traducción de `IntegrityError` a 409, 422 de contrato), `core-persistence` (`C-02`: `SoftDeleteRepository`, UoW como único punto de confirmación), `route-groups`/`role-requirement` (`C-08`: grupo protegido y `requiere_rol`) y `auth-session` (`C-07`).

## Impact

- **Código**: `app/modules/clientes/{schemas,repository,service,unit_of_work,router}.py` y `main.py` (tres `include_router` en el grupo protegido). No se toca `app/modules/clientes/models.py` (los modelos ya existen y son contrato).
- **Base de datos**: **sin migraciones y sin cambios de esquema**. Se usan `cliente` y `vehiculo` creadas en `C-04`, con su UNIQUE de `documento`, su índice único parcial de patente y el CHECK de `anio`.
- **Dependencias**: ninguna nueva.
- **Rutas nuevas** (todas en el grupo protegido): `POST /clientes`, `GET /clientes/{id}`, `POST /clientes/{id}/vehiculos`, `DELETE /vehiculos/{id}` y `GET /mis-vehiculos`.
- **Habilitado**: `C-11 ordenes-trabajo` (necesita vehículos vigentes y la baja lógica de RN-16) y `C-12 detalle-sin-n1` (reutiliza la precarga de la ficha y de `/mis-*`).
- **Límite conocido**: la comprobación de órdenes abiertas corre antes de la baja sin bloquear filas; una orden creada en paralelo entre el `SELECT` y el `UPDATE` de `borrado_en` no se detectaría. Se documenta en `design.md` (D5); la ventana sólo existe mientras `C-11` cree órdenes concurrentes sobre el mismo vehículo.
