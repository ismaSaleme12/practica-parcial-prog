# Proposal

## Why

`C-06` dejó los contratos de `repuestos` y `C-08` les puso roles, pero el módulo quedó **a medio ABM**: hay listado, detalle y un alta que siempre nace con stock 0. La Épica 7 (US-020 a US-022) pide las dos operaciones que explican el stock y el precio de un taller:

1. **El stock tiene que tener una sola puerta de entrada** (RN-14). Editar `stock` por PATCH es exactamente el atajo que rompe la trazabilidad: después nadie puede explicar de dónde salieron las 4 bujías que faltan. El stock sólo cambia por el alta con `stock_inicial`, por la reposición y —más adelante, en `C-11`— por la terminación de una orden; cada uno deja su `movimiento_stock`.
2. **Cada cambio de precio tiene que quedar auditado** (RN-20) con el valor anterior, el nuevo, quién lo cambió y cuándo, en la misma transacción. Un PATCH que no cambia el precio **no** debe ensuciar el historial con una línea inútil (caso C-18).

Sin este change, el catálogo no se puede mantener: no hay forma de dar de baja un repuesto, de corregir un precio, de reponer stock ni de auditar ninguna de las dos cosas. Y `C-11` no podría descontar stock con un punto único de escritura ya probado.

## What Changes

- **`app/modules/repuestos/schemas.py`**:
  - `RepuestoCrear` suma `stock_inicial: int = 0` con `ge=0`; **sigue sin declarar** `stock` (enviarlo es 422 por `extra="forbid"`, caso C-16).
  - `RepuestoPatch` no cambia: sólo `descripcion` y `precio`, aplicados con `cambios_enviados` (`exclude_unset`).
  - Nuevos `ReponerStock` (`cantidad` con `gt=0`), `MovimientoStockLeer` e `HistorialPrecioLeer` (dinero como string Decimal).
- **`app/modules/repuestos/repository.py`**: `MovimientoStockRepository` e `HistorialPrecioRepository` heredan `BaseRepository` (sólo agregado) y exponen `listar_por_repuesto` con orden determinista por `cuando` e `id`.
- **`app/modules/repuestos/unit_of_work.py`**: propiedades `movimientos` e `historial_precios` sobre la misma sesión del UoW.
- **`app/modules/repuestos/service.py`**:
  - `crear` escribe el repuesto con `stock = stock_inicial` y, si es mayor que cero, su `MovimientoStock` «Stock inicial» en el mismo `async with uow`.
  - `actualizar` aplica sólo lo enviado; si el precio cambió, inserta la línea de `historial_precio_repuesto` con anterior/nuevo/usuario; si es idéntico, no inserta nada y responde 200.
  - `eliminar` usa `soft_delete` (`borrado_en`, sin borrar la fila).
  - `reponer` incrementa el stock y agrega el movimiento de entrada «Reposición».
  - `listar_movimientos` y `listar_precios` verifican que el repuesto exista (404) y devuelven la página.
- **`app/modules/repuestos/router.py`**: `PATCH`, `DELETE`, `POST /{id}/reponer`, `GET /{id}/movimientos` y `GET /{id}/precios`, todos con `AdminDep`; el alta pasa a recibir el usuario actual para firmar el movimiento.
- **Evidencia**: `test/repuestos.http` (bloque 0 de login + B-01 a B-04 + endpoints nuevos) y `test/test_repuestos.py` (46 tests) como réplica automatizada.
- **Sin migraciones**: las tres tablas, sus CHECK, el índice único parcial de `codigo` y el disparador de sólo agregado ya existen desde `C-04`. **No se toca `main.py`**: `repuestos_router` ya está montado en el grupo protegido (el 401 y el 403 del cambio obligatorio ya lo cubren).

## Capabilities

### New Capabilities

- `spare-part-management`: listado y detalle con búsqueda parametrizada, alta con `stock_inicial`, PATCH limitado a descripción y precio, baja lógica con código reutilizable y la matriz de permisos de la Épica 7.
- `stock-ledger`: punto único de escritura del stock — alta con stock inicial y reposición, cada uno con su `movimiento_stock` en el mismo UoW — y consulta paginada de los movimientos del repuesto.
- `price-history`: historial de precios que sólo registra cambios efectivos, en la misma transacción que el cambio, y su consulta paginada sólo para ADMIN.

### Modified Capabilities

- Ninguna. `request-contracts` y `error-handling` (de `C-06`) se reutilizan tal cual: el 422 de `extra="forbid"` y el 409 del índice parcial ya los resuelve el handler central. `list-pagination` (de `C-02`) se reutiliza para los dos historiales. `inventory-models` (de `C-03`) no cambia: el esquema es el mismo.

## Impact

- **Código**: `app/modules/repuestos/{schemas,repository,unit_of_work,service,router}.py`, `test/test_repuestos.py` (nuevo) y `test/repuestos.http` (nuevo).
- **Base de datos**: **sin migraciones**. Se usan `repuesto` (índice único parcial `(codigo) WHERE borrado_en IS NULL`), `movimiento_stock` e `historial_precio_repuesto` (las dos de sólo agregado por el disparador de `C-04`).
- **Dependencias**: ninguna nueva.
- **Rutas nuevas**: `PATCH /repuestos/{id}`, `DELETE /repuestos/{id}`, `POST /repuestos/{id}/reponer`, `GET /repuestos/{id}/movimientos` y `GET /repuestos/{id}/precios` (todas ADMIN). `POST /repuestos` acepta `stock_inicial`.
- **Habilitado**: `C-11 ordenes-trabajo` puede descontar stock dejando su movimiento negativo sobre un punto único de escritura ya probado, y copiar el precio del repuesto sabiendo que su historial es auditable.
- **Límite conocido**: el PATCH no permite corregir la descripción de un repuesto dado de baja (responde 404); para eso habría que reabrirlo, y reabrir no está en el alcance del TP.
