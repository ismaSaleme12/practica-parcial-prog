# Tasks

> Orden TDD: primero la evidencia (`test/ordenes.http` + `test/test_ordenes.py`), después la implementación mínima que la hace pasar. La suite nueva falló primero (fallos de import del módulo inexistente y de rutas no montadas) antes de escribir `app/modules/ordenes/`.

## 1. Contratos de la Épica 8

- [x] 1.1 `OrdenCrear` con **sólo** `vehiculo_id` (`gt=0`), `falla` (1..2000) e `items` (`min_length=1`); `ItemOrdenCrear` con `repuesto_id` y `cantidad` (`gt=0`), **sin** precio. Verificación: `POST /ordenes` con `precio_unitario`, `total`, `estado` o `mecanico_id` → 422 nombrando el campo (4 casos parametrizados).
- [x] 1.2 Validador de `items` que rechaza el mismo `repuesto_id` repetido. Verificación: alta con el repuesto 1 dos veces → 422 y el detalle del error menciona `items`.
- [x] 1.3 `EstadoOrdenCodigo(StrEnum)` con `PENDIENTE`, `EN_REPARACION`, `TERMINADA`, `CANCELADA`, usado también como tipo del query `estado`. Verificación: `GET /ordenes?estado=VOLANDO` → 422 (caso C-17), no 409 ni lista vacía.
- [x] 1.4 Salidas `OrdenResumen`, `OrdenDetalle`, `ItemOrdenLeer` (con `subtotal`), `HistorialEstadoLeer` y `EstadoOrdenLeer`; dinero con `Dinero` (string, dos decimales). Verificación: `total`, `precio_unitario` y `subtotal` viajan como `"6000.00"`, nunca como número.
- [x] 1.5 Alta con `items: []` o `falla: ""` → 422; alta con `items` de cantidad 0 o negativa → 422. Verificación: 3 casos parametrizados en la suite.

## 2. Repositorios y UoW

- [x] 2.1 `OrdenTrabajoRepository` con `get_con_vehiculo` (1 consulta), `get_con_dueno` (1, con vehículo y cliente), `get_con_items` (2, con ítems y repuesto) y `get_detalle` (3 fijas: orden+vehículo+cliente, ítems+repuesto, historial). Verificación: el detalle de una orden con 2 ítems y 2 líneas de historial responde completo sin `MissingGreenlet`.
- [x] 2.2 `listar` propio con `joinedload(vehiculo)` porque `BaseRepository.list_page` no acepta opciones de carga; orden `creada_en DESC, id DESC` y los mismos filtros en `count` y en la página. Verificación: página 1 con `size=1` y página 2 traen órdenes distintas; `total` coincide con la cantidad real.
- [x] 2.3 `ItemOrdenRepository` e `HistorialEstadoOrdenRepository` con orden determinista (`ItemOrden.id`; `HistorialEstadoOrden.cuando, id`) y `listar_por_orden`. Verificación: los ítems del detalle salen en orden de id y el historial en orden cronológico.
- [x] 2.4 `EstadoOrdenRepository` **sin** `BaseRepository` (DD-07), con sólo `get(codigo)` y `listar()` por `posicion`. Verificación: el catálogo responde en el orden del seed y ninguna ruta permite escribirlo.
- [x] 2.5 `OrdenesUnitOfWork` con `ordenes`, `items`, `historial`, `estados`, `clientes`, `vehiculos`, `repuestos` y `movimientos`, todos sobre `self.session`. Verificación: el caso C-11 revierte stock, movimiento, estado e historial juntos (ninguna fila queda escrita).

## 3. Servicios

- [x] 3.1 `crear(uow, datos, usuario_id)`: catálogo `PENDIENTE` → vehículo vigente → repuestos vigentes, antes de escribir; copia el precio, suma el total con `Decimal`, inserta orden + ítems + primera línea de historial y relee el detalle. Verificación: 201 con total `"6000.00"`; catálogo vacío → 409 (C-09); repuesto/vehículo inexistente o dado de baja → 409 sin orden (C-10, 4 casos).
- [x] 3.2 `listar(uow, params, estado)`: filtro por estado ya validado por contrato y página con patente. Verificación: `?estado=TERMINADA` devuelve sólo las terminadas; el listado ordena por `creada_en` descendente.
- [x] 3.3 `obtener(uow, id, usuario_id)`: 404 → roles vigentes + dueño → 403. Verificación: el cliente ve su orden, no la ajena (C-06); personal de taller ve cualquiera; id inexistente → 404.
- [x] 3.4 `iniciar(uow, id, usuario_id)`: 404 → sólo PENDIENTE → estado EN_REPARACION, `mecanico_id` de la sesión e historial. Verificación: 200 con mecánico asignado; segunda llamada → 409; RECEPCION → 403.
- [x] 3.5 `terminar(uow, id, usuario_id)`: 404 → 403 (ADMIN o mecánico asignado, SU-04) → 409 de estado → **validación de todos los stock** → descuento + un `movimiento_stock` negativo por ítem (`cantidad=-item.cantidad`, `orden_id`, motivo `"Salida por orden N"`) + historial. Verificación: stock 2 con 4 pedidas → 409 y cero escrituras (C-11); con stock suficiente descuenta y deja exactamente un movimiento por ítem (RN-13/RN-14); ADMIN terminando una orden ajena → 200.
- [x] 3.6 `cancelar(uow, id, usuario_id)`: 404 → 403 (ADMIN/RECEPCION o dueño, **sin** `requiere_rol`) → 409 (sólo PENDIENTE) → estado CANCELADA + historial. Verificación: el dueño cancela la propia (C-13); mecánico ajeno y cliente ajeno → 403; ya cancelada o terminada como RECEPCION → 409; terminada ajena como cliente → 403.
- [x] 3.7 `listar_estados(uow)` y `listar_mis_ordenes(uow, params, usuario_id)`: catálogo por posición; órdenes de los vehículos del cliente de la sesión, página vacía si no tiene ficha. Verificación: 4 estados en orden; el cliente sólo ve las de sus vehículos (RN-17); admin sin ficha → página vacía con `total: 0`.
- [x] 3.8 `avisar_cliente(orden_id)`: `await asyncio.sleep(0.5)` + `logger.info`. Verificación: la terminación exitosa deja la línea del aviso en `caplog` y una rechazada no la deja (US-026/DD-13).

## 4. Rutas

- [x] 4.1 `POST /ordenes` (ADMIN, RECEPCION) → 201 con detalle, total calculado, ítems e historial. Verificación: 201; MECANICO y CLIENTE → 403.
- [x] 4.2 `GET /ordenes` (ADMIN, RECEPCION, MECANICO) → 200 paginado, filtro `estado` y página fuera de rango → 422. Verificación: envoltorio `{items,total,page,size,pages}`; CLIENTE → 403.
- [x] 4.3 `GET /ordenes/{id}` (cualquier sesión; el servicio decide) → 200/403/404. Verificación: detalle con `cliente`, `items` con `subtotal` y `historial`; ajeno → 403; inexistente → 404.
- [x] 4.4 `POST /ordenes/{id}/iniciar` (MECANICO) → 200/403/404/409. Verificación: 200 con `mecanico_id` de la sesión.
- [x] 4.5 `POST /ordenes/{id}/terminar` (ADMIN, MECANICO; el servicio exige ser el asignado salvo ADMIN) → 200/403/404/409 y **agenda el aviso después del `await` del servicio**. Verificación: 403 de identidad antes que 409 de estado (SU-04); 409 de stock sin aviso; 200 con aviso.
- [x] 4.6 `POST /ordenes/{id}/cancelar` (sin `requiere_rol`) → 200/403/404/409. Verificación: el CLIENTE dueño cancela; el CLIENTE ajeno recibe 403; una sesión sin rol de taller no recibe el 403 del cambio obligatorio si es dueña.
- [x] 4.7 `GET /estados-orden` y `GET /mis-ordenes` (cualquier sesión válida) → 200. Verificación: sin cookie → 401 en ambas; CLIENTE → 200 en ambas.
- [x] 4.8 `main.py`: sólo import de `ordenes.router` y tres `include_router` dentro de `grupo_protegido`. Verificación: las ocho rutas responden 401 sin sesión (6 métodos parametrizados + catálogo + `/mis-ordenes`).

## 5. Evidencia y verificación

- [x] 5.1 Escribir `test/ordenes.http` con bloque 0 de login (ADMIN, RECEPCION, MECANICO, CLIENTE y CLIENTE ajeno), A-01→C-10, A-02→C-11, A-03→C-12, A-04→C-13, catálogo, alta válida con total calculado, alta con campos de más (422), estado inválido (422), detalle, `/mis-ordenes`, matriz 401/403, transiciones y bloque destructivo C-09 al final. Cada bloque con la respuesta esperada comentada.
- [x] 5.2 Escribir `test/test_ordenes.py` (65 tests, parametrizaciones incluidas) como réplica automatizada con `client`, `login`, `motor` y `caplog`: C-09, C-10, C-11 (rollback total), C-13, C-17, C-06, SU-04 (403 antes que 409), alta válida e inválida, iniciar/terminar/cancelar con sus 404/403/409, stock y movimientos, `/estados-orden`, `/mis-ordenes`, aviso post-confirmación y matriz 401/403.
- [x] 5.3 Correr `python -m pytest test/test_ordenes.py -q` con `TEST_POSTGRES_DB=taller_mecanico_c11`: 65 passed.
- [x] 5.4 Correr `python -m pytest test/ -q` con `TEST_POSTGRES_DB=taller_mecanico_c11`: **189 passed** (124 de la línea base + 65 nuevos).
- [x] 5.5 `openspec validate 2026-10-27-c-11-ordenes-trabajo --strict` en verde.

## Workflow follow-up

- **Pendiente explícito de `C-12 detalle-sin-n1`**: medir con `SQL_ECHO` que el detalle mantiene **tres** consultas fijas, que el listado mantiene dos (count + página) y que el aviso no corre dentro del UoW.
- **Pendiente explícito de `C-13 casos-de-prueba`**: consolidar la evidencia `.http` de todos los módulos y completar la matriz C-01..C-19; `test/ordenes.http` ya cubre C-10, C-11, C-12 y C-13.
- **Deuda conocida**: no hay bloqueo de fila en la validación de stock (D7); dos terminaciones concurrentes del mismo repuesto pueden chocar contra el CHECK `stock >= 0` y la perdedora revierte entera con 409.
- Revisar los artefactos y archivar con `/opsx:archive 2026-10-27-c-11-ordenes-trabajo` cuando el orquestador lo pida (no archivar desde este change).
- No commitear: el orquestador lo hace.
