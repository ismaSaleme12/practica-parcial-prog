# Tasks

> Orden TDD: primero la evidencia (`test/repuestos.http` + `test/test_repuestos.py`), después la implementación mínima que la hace pasar. La suite nueva falló primero (36 de 46) antes de tocar el módulo.

## 1. Contratos de la Épica 7

- [x] 1.1 Agregar `stock_inicial: int = 0` con `ge=0` a `RepuestoCrear`, **sin** declarar `stock`. Verificación: `POST /repuestos` con `stock_inicial: 7` → 201 y stock 7; con `stock: 5` → 422 con el campo en `errores`.
- [x] 1.2 Mantener `RepuestoPatch` con sólo `descripcion` y `precio`. Verificación: `PATCH` con `stock` → 422 (caso C-16); `PATCH` con `stock_inicial` → 422.
- [x] 1.3 Agregar `ReponerStock` (`cantidad` con `gt=0`), `MovimientoStockLeer` e `HistorialPrecioLeer` (dinero como string Decimal). Verificación: `cantidad: 0` → 422; `precio_anterior`/`precio_nuevo` viajan como `"8500.00"`.

## 2. Repositorios y UoW

- [x] 2.1 `MovimientoStockRepository(BaseRepository[MovimientoStock])` con `_orden_por = (cuando, id)` y `listar_por_repuesto(repuesto_id, params)`. Verificación: dos movimientos con el mismo instante no se repiten entre páginas.
- [x] 2.2 `HistorialPrecioRepository(BaseRepository[HistorialPrecioRepuesto])` con el mismo orden y `listar_por_repuesto`. Verificación: `GET /repuestos/1/precios?size=2` pagina el historial del seed + los cambios.
- [x] 2.3 `RepuestosUnitOfWork.movimientos` y `historial_precios` sobre la misma sesión. Verificación: el alta con stock inicial y su movimiento se confirman juntos.

## 3. Servicios

- [x] 3.1 `crear(uow, datos, usuario_id)`: repuesto con `stock = stock_inicial`; si es mayor que cero, `MovimientoStock` «Stock inicial», usuario actual y `cuando` con zona, **en el mismo UoW**. Verificación: 201 con stock 7 y un movimiento de cantidad 7, motivo «Stock inicial», `orden_id: null`.
- [x] 3.2 `actualizar(uow, id, datos, usuario_id)`: 404 si no existe; `cambios_enviados` para aplicar sólo lo enviado; si el precio cambió, línea de historial con anterior/nuevo/usuario; si es idéntico, ninguna línea. Verificación: 2 cambios → 2 líneas; mismo precio → 0; sólo descripción → 0 (caso C-18).
- [x] 3.3 `eliminar(uow, id)`: `soft_delete` (204) y 404 si no existe o ya estaba de baja. Verificación: la fila conserva `borrado_en` y el código se reutiliza en un alta nueva.
- [x] 3.4 `reponer(uow, id, datos, usuario_id)`: suma al stock y deja el movimiento «Reposición» en el mismo UoW; 404 si no existe. Verificación: stock 2 → 7 con `cantidad: 5` y un movimiento nuevo.
- [x] 3.5 `listar_movimientos` y `listar_precios`: 404 si el repuesto no existe (o está dado de baja) y página ordenada por `cuando`/`id`. Verificación: `/repuestos/999999/movimientos` → 404.

## 4. Rutas

- [x] 4.1 `PATCH /repuestos/{id}` (ADMIN) → 200/404/422. Verificación: 200 al cambiar descripción, 404 con id inexistente, 422 con `stock` o `precio` 0.
- [x] 4.2 `DELETE /repuestos/{id}` (ADMIN) → 204/404 con cuerpo vacío. Verificación: 204, después `GET /repuestos/1` → 404.
- [x] 4.3 `POST /repuestos/{id}/reponer` (ADMIN) → 200 con el repuesto actualizado. Verificación: 200 y stock incrementado; 403 con RECEPCION.
- [x] 4.4 `GET /repuestos/{id}/movimientos` y `GET /repuestos/{id}/precios` (ADMIN) → 200 paginado/404. Verificación: envoltorio `{items,total,page,size,pages}`; página fuera de rango → 422.
- [x] 4.5 `POST /repuestos` firma el movimiento con el usuario de la sesión. Verificación: `usuario_id` del movimiento = id de `GET /auth/yo` del ADMIN.
- [x] 4.6 **No** se toca `main.py`: el router ya está en el grupo protegido. Verificación: sin cookie → 401; RECEPCION/MECANICO → 403 en las seis rutas de ADMIN.

## 5. Evidencia y verificación

- [x] 5.1 Escribir `test/repuestos.http`: bloque 0 de login ADMIN, catálogo, inyección `q`, alta con `stock_inicial`, B-01 (`stock` en PATCH → 422), B-02 (cambio de precio visible en `/precios`), B-03 (PATCH sin cambio sin línea), reposición, historiales, baja lógica con código reutilizable, B-04 (RECEPCION → 403) y 401 sin sesión.
- [x] 5.2 Escribir `test/test_repuestos.py` (46 tests) como réplica automatizada con `client`, `login`, `token_*` y `motor`: C-16 (`stock` en PATCH → 422 y `q` con inyección → `total: 0`), C-18, alta con `stock_inicial`, reposición con movimiento, baja lógica con código reutilizable, 409 de código repetido, paginación de los dos historiales y la matriz 401/403.
- [x] 5.3 Correr `python -m pytest test/test_repuestos.py -q` con `TEST_POSTGRES_DB=taller_mecanico_c10`: 46 passed.
- [x] 5.4 Correr `python -m pytest test/ -q` con `TEST_POSTGRES_DB=taller_mecanico_c10`: **124 passed**.
- [x] 5.5 `openspec validate 2026-10-27-c-10-repuestos-stock --strict` en verde.

## Workflow follow-up

- **Pendiente explícito de `C-11`**: terminar una orden descuenta stock y deja **un movimiento negativo por cada salida** (RN-13) reutilizando este punto único de escritura; el `orden_id` del movimiento se completa ahí.
- **Pendiente explícito de `C-13`**: consolidar la evidencia `.http` y mapear la matriz C-01..C-19; refrescar `test/contracts.http` (deuda anotada en `README.md` desde `C-08`).
- Revisar los artefactos y archivar con `/opsx:archive c-10-repuestos-stock` cuando el orquestador lo pida (no archivar desde este change).
- No commitear: el orquestador lo hace.
