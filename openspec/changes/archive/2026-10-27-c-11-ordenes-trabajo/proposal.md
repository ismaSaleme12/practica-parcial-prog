# Proposal

## Why

Hasta acá la API sabe quién es cada usuario, qué puede hacer, qué clientes y vehículos existen y cuánto stock y qué precio tiene cada repuesto. Pero **no puede abrir una orden de trabajo**, que es el hecho que une todo el dominio: un vehículo entra por una falla, recibe repuestos y sale terminado o cancelado. La Épica 8 pide las cuatro operaciones que hacen funcionar el taller, y tres de ellas tienen una regla que no se puede repartir entre capas:

1. **El alta no confía en el cliente** (RN-10). El precio de cada repuesto y el total se calculan en el servidor; el cuerpo sólo lleva `vehiculo_id`, `falla` e `items`. Aceptar `precio_unitario`, `total`, `estado` o `mecanico_id` sería permitir que un cliente invente la factura o salte el flujo.
2. **Terminar es una transacción multi-escritura** (RN-13/RN-14). Hay que descontar cada repuesto, dejar **un** `movimiento_stock` negativo por ítem y una línea de historial, todo junto. Si un solo repuesto no alcanza, no se escribe **nada**: el caso C-11 es exactamente la orden 2 del seed, que pide 4 bujías cuando hay 2, y tiene que responder 409 sin tocar stock, movimientos, estado ni historial.
3. **La identidad se evalúa antes que el estado** (SU-04). Un mecánico no asignado recibe 403 en `terminar` aunque la orden tampoco admita la transición; un cliente ajeno recibe 403 en `cancelar` aunque la orden esté TERMINADA. Invertir el orden filtraría el estado de órdenes ajenas y rompería la matriz de permisos.
4. **El aviso al cliente va después del commit** (US-026/DD-13). El `BackgroundTasks` no puede correr dentro del UoW: un aviso enviado antes de confirmar mentiría si la transacción revierte. Sólo se agenda cuando el servicio devuelve la orden ya confirmada.

Sin este change, `C-12` no tiene detalle que medir y `C-13` no tiene los casos C-10, C-11 y C-13 que la entrega exige.

## What Changes

- **`app/modules/ordenes/schemas.py`** (nuevo): `OrdenCrear` sólo con `vehiculo_id`, `falla` e `items` (`min_length=1` y sin repuestos repetidos); `ItemOrdenCrear` sin precio. `EstadoOrdenCodigo` (los cuatro códigos) se usa también como tipo del filtro de `GET /ordenes`. Salidas `OrdenResumen`, `OrdenDetalle`, `ItemOrdenLeer` con `subtotal`, `HistorialEstadoLeer` y `EstadoOrdenLeer`; el dinero es `Decimal` serializado como string.
- **`app/modules/ordenes/repository.py`** (nuevo):
  - `OrdenTrabajoRepository` con `get_con_vehiculo`, `get_con_dueno`, `get_con_items` y `get_detalle` (precargas fijas, sin carga perezosa) y un `listar` propio con `joinedload(vehiculo)` porque `BaseRepository.list_page` no acepta opciones de carga.
  - `ItemOrdenRepository` e `HistorialEstadoOrdenRepository` (sólo agregado) con orden determinista.
  - `EstadoOrdenRepository` **sin** `BaseRepository` (DD-07): su PK es `codigo` y desde la API no se escribe; sólo expone `get` y `listar` por `posicion`.
- **`app/modules/ordenes/unit_of_work.py`** (nuevo): `OrdenesUnitOfWork` con `ordenes`, `items`, `historial`, `estados`, `clientes`, `vehiculos`, `repuestos` y `movimientos`, todos sobre la misma sesión: una sola transacción para la orden, sus ítems, los movimientos y el historial.
- **`app/modules/ordenes/service.py`** (nuevo): `crear`, `listar`, `obtener`, `iniciar`, `terminar`, `cancelar`, `listar_estados`, `listar_mis_ordenes` y `avisar_cliente`.
  - `crear`: catálogo (`PENDIENTE`) → vehículo vigente → repuestos vigentes, en ese orden; copia el precio, suma el total con `Decimal`, inserta orden + ítems + primera línea de historial y relee el detalle.
  - `terminar`: 404 → 403 (ADMIN o mecánico asignado) → 409 de estado → validación de **todos** los stock → recién entonces descuenta, agrega un movimiento negativo por ítem y la línea de historial.
  - `cancelar`: 404 → 403 (ADMIN/RECEPCION o dueño) → 409 (sólo PENDIENTE).
- **`app/modules/ordenes/router.py`** (nuevo): tres routers (`/ordenes`, `/estados-orden`, `/mis-ordenes`) con la matriz de permisos, el mapeo explícito ORM → contrato y `BackgroundTasks` en `terminar` **después** de que el servicio devuelve.
- **`main.py`**: sólo se agregan el import y tres `include_router` al grupo protegido existente.
- **Evidencia**: `test/ordenes.http` (bloque 0 de login, A-01 a A-04, C-10, C-11, C-13, catálogo, filtro inválido, `/mis-ordenes`, 401/403) y `test/test_ordenes.py` (65 tests) como réplica automatizada.
- **Sin migraciones ni cambios de esquema**: las cuatro tablas de la Épica 8, sus FK, CHECK, índices y el disparador de sólo agregado existen desde `C-03`/`C-04`. **No se toca** ningún modelo, `seed.py` ni `test/conftest.py`.

## Capabilities

### New Capabilities

- `work-order-management`: alta PENDIENTE con precio copiado y total Decimal, listado paginado, detalle con vehículo/cliente/ítems/historial, `/mis-ordenes` acotado al dueño y la matriz de permisos de la Épica 8.
- `work-order-lifecycle`: máquina de estados `iniciar`/`terminar`/`cancelar`, asignación del mecánico, identidad antes que estado (SU-04), historial de sólo agregado y aviso simulado post-confirmación.
- `work-order-catalog`: `GET /estados-orden` por posición, filtro `estado` validado contra el enum del contrato (422) y catálogo de sólo lectura.

### Modified Capabilities

- `stock-ledger`: la terminación de una orden es un camino más de escritura del stock. Se modifica la regla «el stock sólo cambia por movimientos» para incluir la salida por orden y se agrega el requisito de la transacción multi-escritura con rollback total, un movimiento negativo por ítem y `orden_id` en el movimiento.

## Impact

- **Código**: `app/modules/ordenes/{schemas,repository,unit_of_work,service,router}.py` (nuevos) y `main.py` (import + tres `include_router`). No se modifican los modelos de órdenes ni los módulos de clientes/repuestos/usuarios: se reutilizan sus repositorios.
- **Base de datos**: **sin migraciones**. Se usan `estado_orden`, `orden_trabajo`, `item_orden`, `historial_estado_orden` y `movimiento_stock` tal como quedaron en `C-04`; el `stock >= 0` y el disparador de sólo agregado siguen siendo la última defensa.
- **Dependencias**: ninguna nueva. `BackgroundTasks` viene con FastAPI/Starlette.
- **Rutas nuevas** (grupo protegido): `POST /ordenes`, `GET /ordenes`, `GET /ordenes/{id}`, `POST /ordenes/{id}/iniciar`, `POST /ordenes/{id}/terminar`, `POST /ordenes/{id}/cancelar`, `GET /estados-orden` y `GET /mis-ordenes`.
- **Habilitado**: `C-12 detalle-sin-n1` (mide las precargas del detalle y el aviso post-confirmación) y `C-13 casos-de-prueba` (consolida los casos C-10, C-11 y C-13).
- **Nomenclatura del enunciado**: el PDF **no** etiqueta esta épica con A-01..A-04; usa C-10 (alta), C-11 (stock insuficiente), C-12 (aviso) y C-13 (cancelar). En `test/ordenes.http` se conserva esa numeración y se documenta el alias A-01→C-10, A-02→C-11, A-03→C-12 y A-04→C-13 que pedía el roadmap. Es la única ambigüedad detectada y no bloquea el change.
- **Límite conocido**: no se usan bloqueos de fila (`SELECT ... FOR UPDATE`) al validar el stock. Dos terminaciones concurrentes sobre el mismo repuesto podrían pasar la validación y chocar contra el CHECK `stock >= 0` de la base; la transacción que pierde revierte entera y el handler central responde 409. Se documenta en `design.md` (D7).
