# Tasks

> Orden TDD: primero la evidencia (`test/contracts.http` + `test/test_contracts.py`), después la implementación mínima que la hace pasar.

## 1. Piezas compartidas de contrato

- [x] 1.1 Crear `app/core/schemas.py` con `ContratoEntrada` (`extra="forbid"`, `str_strip_whitespace`), `ContratoSalida` (`from_attributes`), el tipo `Dinero` (`Decimal` serializado como string con dos decimales) y `cambios_enviados()` (`exclude_unset`, sin `None`). Verificación: `app.openapi()` declara `RepuestoLeer.precio` como `{"type": "string"}` y `RepuestoLeer.precio` sale `"8500.00"`.

## 2. Manejo central de errores

- [x] 2.1 Crear `app/core/errors.py` con `registrar_manejadores(app)`, los handlers de `IntegrityError` (409), `DataError` (422), `RequestValidationError` (422) y `HTTPException`/`StarletteHTTPException`, y las excepciones `Conflicto` (409) y `RecursoNoEncontrado` (404). Verificación: los seis handlers quedan en `app.exception_handlers` y, contra la app real, `IntegrityError` → 409 sin texto del motor y cuerpo inválido → 422 con `detail` propio.
- [x] 2.2 Registrar los manejadores en `main.py` **antes** de montar los routers, e importar el registro central `app/models.py` (sin él las relaciones entre módulos no se resuelven). Verificación: `POST /repuestos` con `codigo` repetido → 409 (no 500) y el cuerpo no contiene `duplicate key`, el nombre del índice ni el valor.

## 3. Contratos de usuarios

- [x] 3.1 Crear `app/modules/usuarios/schemas.py`: `UsuarioCrear` (`extra="forbid"`, email con patrón y `max_length=320`, nombre `max_length=120`, contraseña de 1 a 72 **bytes** UTF-8) y `UsuarioLeer` **sin `password_hash`**. Verificación: 73 bytes → 422; 72 bytes → 201; 37 «ñ» (74 bytes) → 422; `password_hash`/`rol` en el cuerpo → 422 con ambos campos identificados; `UsuarioLeer` no declara `password_hash`.
- [x] 3.2 Crear `app/modules/usuarios/{repository,unit_of_work,service,router}.py` con `POST /usuarios` (201): el hash se calcula **antes** de abrir el UoW. Verificación: alta correcta → 201 sin `password_hash` (ni `$2b$` en el cuerpo); email repetido → 409.

## 4. Contratos de repuestos y listado paginado

- [x] 4.1 Crear `app/modules/repuestos/schemas.py`: `RepuestoCrear` (sin `stock`), `RepuestoLeer` (`precio` como `Dinero`), `RepuestoPatch` (sólo `descripcion` y `precio`). Verificación: `{"stock": 5}` en el alta → 422; `stock` en el PATCH → `ValidationError`; `precio` de salida como string.
- [x] 4.2 Crear `app/modules/repuestos/repository.py` con `filtro_busqueda(q)` que compile a `ILIKE $1` (parámetro ligado) y `_orden_por = (Repuesto.id,)` para que las páginas sean deterministas. Verificación: la sentencia compilada con dialecto PostgreSQL muestra `restriccion ILIKE %(descripcion_1)s` y el patrón aparece sólo en `params`, nunca en el texto del SQL; las páginas 1 y 2 con `size=2` devuelven `FA-001, PF-002` y `BU-003, AC-004` sin repetir.
- [x] 4.3 Crear `app/modules/repuestos/{unit_of_work,service,router}.py` con `GET /repuestos` (envoltorio de `Page`, `q`, `page`, `size`), `GET /repuestos/{id}` (200/404) y `POST /repuestos` (201, stock 0). Verificación: `size=2` → `total: 4`, `pages: 2`; `page=3` → 422 «La página 3 no existe: hay 2.»; `q=' OR '1'='1` → `total: 0`; id inexistente → 404; alta válida → 201 con `precio` string y `stock: 0`.

## 5. Montaje y evidencia

- [x] 5.1 Montar `usuarios_router` y `repuestos_router` en `main.py` con un comentario que declare que `C-08` los moverá al grupo protegido. Verificación: las rutas listadas por `main.app` incluyen `/usuarios`, `/repuestos` (GET y POST) y `/repuestos/{repuesto_id}`.
- [x] 5.2 Escribir `test/contracts.http` con la respuesta esperada comentada en cada bloque: 422 de `extra="forbid"`, contraseña > 72 bytes (incluye multibyte), página fuera de rango, `IntegrityError` → 409, 404, listado y búsqueda con comilla (19 bloques).
- [x] 5.3 Escribir `test/test_contracts.py` como réplica automatizada de los `.http` (19 tests), contra los fixtures `client`/`login` de `C-05`, sin tocar `conftest.py` ni `pytest.ini`.
- [x] 5.4 Verificar contra una base migrada y sembrada (`taller_mecanico_c06_check`, creada para la verificación) con un script temporal fuera del repo: 19/19 tests en verde y respuestas reales de cada caso. La base de verificación y el script se borraron al terminar.
- [x] 5.5 Confirmar que `C-08` re-monta los routers en el grupo protegido (bloqueante de la fase 4, no de este change).

## Workflow follow-up

- Revisar los artefactos y archivar con `/opsx:archive c-06-contracts-and-errors` cuando el usuario lo pida (no archivar desde este change).
- No commitear: el orquestador lo hace.
