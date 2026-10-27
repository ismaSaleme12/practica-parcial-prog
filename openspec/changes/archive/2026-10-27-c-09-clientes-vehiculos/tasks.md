# Tasks

> Orden TDD: primero la evidencia (`test/clientes.http` + `test/test_clientes.py`), después la implementación mínima que la hace pasar. La suite nueva falló primero (**12 fallos de 14**: las rutas no existían y respondían 404) antes de escribir el módulo.

## 1. Contratos de la Épica 6

- [x] 1.1 Crear `app/modules/clientes/schemas.py` con `ClienteCrear`, `VehiculoCrear`, `ClienteLeer`, `ClienteFicha` y `VehiculoLeer`; entradas con `extra="forbid"`. Verificación: `POST /clientes` con `usuario_id` → 422; `POST /clientes/{id}/vehiculos` con `borrado_en` → 422.
- [x] 1.2 Validar `anio` con los límites del CHECK (`ge=1950, le=2100`) para que fuera de rango sea 422 y no 409 de integridad. Verificación: 1949 → 422; 2101 → 422; 2100 → válido.

## 2. Repositorios

- [x] 2.1 `ClienteRepository.get_ficha(cliente_id)`: cliente con `selectinload(Cliente.vehiculos.and_(Vehiculo.borrado_en.is_(None)))`, dos consultas fijas, sin carga perezosa. Verificación: `GET /clientes/1` → 200 con AAA111 y AAB222; el vehículo dado de baja no aparece.
- [x] 2.2 `ClienteRepository.get_by_usuario_id(usuario_id)`: ficha dueña de la cuenta, con la misma precarga; `None` si la cuenta no tiene ficha. Verificación: `GET /mis-vehiculos` de Laura trae sus dos vehículos; el de recepción, lista vacía.
- [x] 2.3 `VehiculoRepository(SoftDeleteRepository[Vehiculo])` con `tiene_ordenes_abiertas(vehiculo_id)`: `SELECT ... LIMIT 1` que cruza `orden_trabajo` con `estado_orden` por `es_final = false`. Verificación: vehículo 1 (orden PENDIENTE) y vehículo 3 (EN_REPARACION) → 409; vehículo 2 (sin órdenes) → 204.
- [x] 2.4 Ninguna consulta previa de unicidad: el documento y la patente chocan contra el UNIQUE/índice parcial y el handler central traduce a 409. Verificación: documento repetido → 409; patente vigente repetida → 409; patente repetida tras la baja → 201 (C-19).

## 3. Unit of Work y servicios

- [x] 3.1 `ClientesUnitOfWork` con `clientes` y `vehiculos` sobre la misma sesión, sin construir el UoW ni confirmar. Verificación: el alta de vehículo lee el cliente y escribe el vehículo en la misma transacción.
- [x] 3.2 `crear_cliente`, `obtener_ficha` (404 propio) y `crear_vehiculo` (404 si el cliente de la ruta no existe, sin dejar filas). Verificación: `GET /clientes/999999` → 404; `POST /clientes/999999/vehiculos` → 404 y la tabla sigue igual.
- [x] 3.3 `dar_de_baja_vehiculo`: 404 si no existe(o ya está dado de baja), 409 si tiene órdenes abiertas (antes de escribir), y `soft_delete` (escribe `borrado_en`, no borra). Verificación: tras 204 la fila sigue en `vehiculo` con `borrado_en`; una segunda baja → 404.
- [x] 3.4 `listar_mis_vehiculos`: ficha por `Cliente.usuario_id`; sin ficha → `[]` (200, ni 404 ni 500). Verificación: recepción y admin → `[]`; Laura → sólo AAA111 y AAB222.

## 4. Router y grupos de rutas

- [x] 4.1 `app/modules/clientes/router.py` con tres routers: `/clientes` (POST alta, GET ficha, POST vehículos), `/vehiculos` (DELETE baja lógica, 204 sin cuerpo) y `/mis-vehiculos` (GET sin `requiere_rol`). Verificación: sin cookie → 401 en las cinco; con CLIENTE o MECANICO → 403 en las cuatro de administración; con RECEPCION o ADMIN → el código esperado.
- [x] 4.2 `main.py`: montar los tres routers en el grupo **protegido** (cambio aditivo; no se reordena ni se reescribe lo existente, y no se toca `app/modules/repuestos/`). Verificación: las rutas heredan el 401 de la sesión y el 403 del cambio obligatorio.

## 5. Evidencia y verificación

- [x] 5.1 Escribir `test/clientes.http` con bloque 0 de login (las rutas están en el grupo protegido) y la respuesta esperada comentada: alta cliente, documento repetido, alta vehículo, patente vigente repetida, ficha con vehículos, cliente inexistente, año fuera de rango, baja con orden abierta (409), patente repetida tras la baja (C-19), `/mis-vehiculos` (aislamiento y lista vacía), matriz de permisos.
- [x] 5.2 Escribir `test/test_clientes.py` (14 tests) como réplica automatizada con `client`, `login` y `motor` de `C-05`: documento duplicado → 409, patente vigente duplicada → 409, patente repetida tras la baja → 201 (C-19), baja con orden abierta → 409, ficha con vehículos (carga anticipada), año fuera de rango → 422, cliente/vehículo inexistente → 404, aislamiento de `/mis-vehiculos`, 401 sin sesión y 403 con CLIENTE/MECANICO.
- [x] 5.3 Correr la suite con la base aislada: `$env:TEST_POSTGRES_DB="taller_mecanico_c09"; python -m pytest test/test_clientes.py -q` → **14 passed**; y la suite completa `python -m pytest test/ -q` → **124 passed** (incluye los tests de `C-10`, que conviven en el repo; no se modificó ningún archivo de ese change).
- [x] 5.4 `openspec validate 2026-10-27-c-09-clientes-vehiculos --strict` en verde.

## Workflow follow-up

- **Pendiente explícito de `C-11`**: el alta de una orden debe rechazar un vehículo dado de baja (RN-16) y `GET /mis-ordenes` reutiliza la misma resolución de dueño por `Cliente.usuario_id` que `/mis-vehiculos`.
- **Pendiente explícito de `C-12`**: medir con `SQL_ECHO`/contador que `GET /clientes/{id}` y `/mis-vehiculos` mantienen el número fijo de consultas con distinta cantidad de vehículos (el diseño ya es de dos consultas).
- **Pendiente explícito de `C-13`**: `test/contracts.http` sigue desactualizado frente al RBAC; el `.http` de este change ya incluye el bloque de login.
- Revisar los artefactos y archivar con `/opsx:archive` cuando el orquestador lo pida (no archivar desde este change).
- No commitear: el orquestador lo hace.
