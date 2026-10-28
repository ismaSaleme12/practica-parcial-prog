# Tasks

> TDD de medición: primero se escribió `test/test_detalle.py` con el contador y la medición impresa, se corrieron los tests contra PostgreSQL real y se observaron los conteos. Recién entonces se reemplazaron las impresiones por aserciones de igualdad, techo y piso. No hubo que tocar código de producción porque el comportamiento ya cumplía: el change es una **verificación**, no un cambio de comportamiento.

## 0. Punto de partida

- [x] 0.1 Confirmar la línea base antes de tocar nada: `python -m pytest test/ -q` desde la raíz → **189 passed**. Verificación: ningún test previo se modificó.
- [x] 0.2 Escribir el contador `before_cursor_execute` sobre `motor.sync_engine` con alta y baja por bloque (`event.listen` / `event.remove`), sin mocks ni dependencias nuevas. Verificación: el listener sólo ve las sentencias de la petición medida.
- [x] 0.3 Correr la versión con impresiones (`python -m pytest test/test_detalle.py -q -s`) y registrar los números reales: detalle 5/5, ficha 4/4, `/mis-vehiculos` 3/3, `/mis-ordenes` 5/5, aviso `TERMINADA`.

## 1. Detalle con conteo fijo (C-15, US-025 CA-1)

- [x] 1.1 Crear por API dos órdenes sobre el vehículo de Laura (`AAA111`): una con 2 ítems (`FA-001`, `PF-002`) y otra con 4 (`FA-001`, `PF-002`, `BU-003`, `AC-004`), todas con `cantidad: 1` para no alterar el stock del caso C-11. Verificación: ambas altas responden 201.
- [x] 1.2 Medir el `GET /ordenes/{id}` de cada orden con la misma sesión de ADMIN y el login fuera del contador. Verificación: **5 consultas en ambos casos** (sesión + tres del detalle + roles vigentes); la igualdad se asserta y además no supera el techo de 6.
- [x] 1.3 Comprobar que las precargas ocurrieron: una sola sentencia sobre `item_orden` y una sola sobre `historial_estado_orden`. Verificación: `_consulta_sobre(consultas, "item_orden") == 1` en ambos casos.
- [x] 1.4 Medir el detalle antes y después de `iniciar` (1 → 2 líneas de historial). Verificación: mismo conteo (5) y una sola sentencia sobre `historial_estado_orden`.
- [x] 1.5 Evitar que un listener roto apruebe la prueba: piso mínimo de 3 consultas y techo documentado. Verificación: `_verificar_conteo` falla si el conteo es 0 o si crece con las filas hijas.

## 2. Ficha y «lo propio» sin crecimiento (US-025 CA-2)

- [x] 2.1 `GET /clientes/{id}` con 1 vehículo (Jorge) y con 3 (se agregan dos por API). Verificación: **4 consultas** en ambos casos (sesión + roles + ficha + vehículos) y una sola sentencia sobre `vehiculo`.
- [x] 2.2 `GET /mis-vehiculos` con 2 vehículos (Laura) y con 3. Verificación: **3 consultas** en ambos casos (sesión + ficha + vehículos).
- [x] 2.3 `GET /mis-ordenes` con 1 orden visible y con 2 (se crea una en `AAB222`). Verificación: **5 consultas** en ambos casos (sesión + ficha + vehículos + `count` + página) y `total` correcto en cada respuesta.
- [x] 2.4 Confirmar que no hay N+1 que corregir: las precargas de `C-09`/`C-11` ya son fijas y las relaciones son `lazy="raise_on_sql"`. Verificación: todos los conteos son iguales; no se modificó ningún repositorio.

## 3. Aviso después del commit (C-12, US-026 CA-2)

- [x] 3.1 Control previo: con la orden `EN_REPARACION` ya confirmada, abrir una sesión nueva con `app.state.session_maker` y leer el estado. Verificación: ve `EN_REPARACION` (una sesión distinta sólo ve lo confirmado).
- [x] 3.2 Sustituir `app.modules.ordenes.service.avisar_cliente` con `monkeypatch` por una corrutina que abre una sesión nueva, lee `orden_trabajo.estado` y lo registra. Verificación: el `monkeypatch` se revierte solo y la sesión se cierra con `async with`.
- [x] 3.3 Terminar la orden y comprobar qué vio el aviso. Verificación: respuesta 200 con `TERMINADA` y el aviso registró **`TERMINADA`**; si corriera dentro del UoW habría visto `EN_REPARACION`.
- [x] 3.4 No duplicar el caso de rechazo: `test_ordenes.py::test_terminar_rechazado_no_agenda_el_aviso` sigue cubriendo que un 409 no agenda la tarea. Verificación: no se modificó `test_ordenes.py`.

## 4. Asincronía y diagnóstico (US-026 CA-3)

- [x] 4.1 Auditar handlers y servicios: todos los endpoints son `async def`; los `def` restantes son helpers puros sin IO. Verificación: test de introspección sobre `app.routes` (`APIRoute` + `inspect.iscoroutinefunction`) → sin bloqueantes.
- [x] 4.2 Auditar IO bloqueante: bcrypt corre en `asyncio.to_thread`; no hay `time.sleep`, `open()`, `subprocess`, `requests`, `urllib` ni `smtplib` en `app/` ni en `main.py`. Verificación: búsqueda en el árbol y revisión de `app/core/security.py`.
- [x] 4.3 `SQL_ECHO`: comprobar el default `false`, la activación con `SQL_ECHO=true` y el cableado al `echo` del motor del lifespan. Verificación: `Settings.model_fields["SQL_ECHO"].default is False`, `Settings(SQL_ECHO="true").SQL_ECHO is True`, `motor.sync_engine.echo is False`.
- [x] 4.4 No activar `SQL_ECHO` en la suite ni por defecto. Verificación: `test/conftest.py` sigue fijando `SQL_ECHO=false` y no se modificó.

## 5. Evidencia y verificación

- [x] 5.1 `test/test_detalle.py` con **8 tests**: C-15 (2 vs 4 ítems), historial, ficha 1 vs 3, `/mis-vehiculos` 2 vs 3, `/mis-ordenes` 1 vs 2, aviso post-commit, handlers asincrónicos y `SQL_ECHO`.
- [x] 5.2 `python -m pytest test/test_detalle.py -q` → **8 passed**.
- [x] 5.3 `python -m pytest test/ -q` desde la raíz → **197 passed** (189 previos + 8 nuevos), sin tocar tests existentes.
- [x] 5.4 `openspec validate 2026-10-27-c-12-detalle-sin-n1 --strict` en verde.

## Workflow follow-up

- **Pendiente de `C-13 casos-de-prueba`**: usar `test/test_detalle.py` como evidencia automatizada de C-15 (2 vs 4 ítems) y C-12 (aviso post-confirmación), y escribir el `.http` equivalente con la respuesta esperada comentada.
- **Deuda conocida (no bloqueante)**: el conteo incluye las consultas de autenticación; si `get_usuario_actual` cambia, los números se mueven. La prueba compara igualdad y usa techo con margen, y `design.md` (D2) documenta la composición.
- **Deuda conocida (no bloqueante)**: el listener es global al motor; la suite es secuencial. Correr con `pytest-xdist` exigiría una base por worker, fuera de alcance.
- Revisar los artefactos y archivar con `/opsx:archive 2026-10-27-c-12-detalle-sin-n1` cuando el orquestador lo pida (no archivar desde este change).
- No commitear: el orquestador lo hace.
