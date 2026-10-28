# Design

Ver `proposal.md` (Why) y las specs `read-performance` (nueva), `work-order-management` y `work-order-lifecycle` (modificadas). Este documento explica **cómo se mide** y qué se comprobó.

## Context

El comportamiento que este change verifica ya estaba implementado por los changes anteriores:

- `get_detalle` (`C-11`) precarga `vehiculo → cliente` con `joinedload`, `items → repuesto` con `selectinload(...).joinedload(...)` y `historial_estados` con `selectinload`.
- `get_ficha` / `get_by_usuario_id` (`C-09`) precargan los vehículos vigentes con un `selectinload` filtrado por `borrado_en IS NULL`.
- `listar` de órdenes (`C-11`) hace `count` + página con `joinedload(vehiculo)`, y `/mis-ordenes` lo reutiliza con `vehiculo_id IN (...)`.
- Todas las relaciones de los modelos declaran `lazy="raise_on_sql"`: un acceso no precargado **lanza**, no emite una consulta silenciosa.
- `router.terminar_orden` hace `await service.terminar(...)` y **después** `background_tasks.add_task(...)`; el UoW confirma al salir del `async with` del servicio (`C-11`, DD-13).
- `Settings.SQL_ECHO: bool = False` y el lifespan pasa `echo=settings.SQL_ECHO` a `create_async_engine`.

Lo que faltaba era la **medición**. El Ejercicio 8 y el caso C-15 no piden optimizar: piden demostrar que el número de consultas es fijo y que el aviso corre después de confirmar. Este change es, por lo tanto, un change de verificación: escribe la prueba que mide, observa el resultado y lo fija como criterio.

Restricciones:

- **Stack cerrado**: la medición usa `sqlalchemy.event` (ya instalado) y `inspect` (biblioteca estándar). No se agregan dependencias.
- **Base real**: la suite corre contra PostgreSQL 16; no hay mocks ni repositorios falsos. El contador mide las sentencias que llegan de verdad al cursor.
- **Sin cambios de producción**: no se toca ningún handler, servicio ni repositorio; si la medición hubiera encontrado un N+1, el arreglo habría sido una precarga en el repositorio.

## Goals / Non-Goals

**Goals:**

- Medir con un contador `before_cursor_execute` que `GET /ordenes/{id}` usa el **mismo** número de consultas con 2 y 4 ítems (caso C-15).
- Medir que `GET /clientes/{id}`, `/mis-vehiculos` y `/mis-ordenes` no agregan consultas al crecer las filas hijas.
- Demostrar por aislamiento que el aviso de `BackgroundTasks` corre **después del commit** (caso C-12).
- Comprobar que todos los handlers son `async def` y que no se introdujo IO bloqueante.
- Dejar documentado que `SQL_ECHO` se activa por entorno y que su default es `false`.

**Non-Goals:**

- Optimizar consultas: no hay N+1 que corregir; el conteo ya es fijo.
- Cachear resultados, agregar índices o reescribir `selectinload` como `joinedload` (ver D4).
- Probar concurrencia o latencia: lo que se mide es cantidad de sentencias, no tiempo.
- Duplicar el caso «un 409 no agenda el aviso»: ya vive en `test_ordenes.py`.

## Decisions

### D1 — Se cuenta sobre `motor.sync_engine`, no sobre el motor asincrónico

**Decisión**: el contador se registra con `sqlalchemy.event.listen(motor.sync_engine, "before_cursor_execute", listener)` y se retira con `event.remove(...)` al salir del bloque `with`.

**Por qué**: `AsyncEngine` no es un target de eventos de SQLAlchemy; es un envoltorio que delega en un `Engine` síncrono. Las conexiones que usa `AsyncSession` son las mismas conexiones del `sync_engine`, así que el evento `before_cursor_execute` se dispara una vez por sentencia ejecutada, con la sentencia SQL ya compilada. El listener se agrega **sólo alrededor de la petición medida**: el `TRUNCATE`/seed del `conftest` y el login quedan fuera. `BEGIN`/`COMMIT` no pasan por el cursor, así que el conteo es de sentencias SQL, que es exactamente lo que interesa.

**Consecuencia**: no hace falta un proxy, un `echo` parseado ni una extensión. El listener se retira siempre en el `finally`, de modo que una aserción fallida no deja el contador pegado en el motor compartido.

**Alternativa descartada**: activar `SQL_ECHO` y contar líneas de log. Acopla la prueba al formato del logger, no distingue el nivel de log del pool y contamina la salida de toda la suite.

### D2 — El detalle hace cinco consultas y no crece con los ítems

**Decisión**: se crean por API dos órdenes sobre el mismo vehículo (Laura, `AAA111`): una con 2 ítems (`FA-001`, `PF-002`) y otra con 4 (`FA-001`, `PF-002`, `BU-003`, `AC-004`), todas con `cantidad: 1` para no alterar el stock del caso C-11. Se mide el `GET /ordenes/{id}` de cada una con la misma sesión de ADMIN. **Medición: 5 consultas en ambos casos.**

Composición de esas cinco consultas:

| # | Origen | Sentencia |
|---|---|---|
| 1 | `get_usuario_actual` | `SELECT usuario ... WHERE usuario.id = $1` |
| 2 | `get_detalle` | `SELECT orden_trabajo ... JOIN vehiculo ... JOIN cliente ...` (el `joinedload` anidado no agrega consultas) |
| 3 | `selectinload(items).joinedload(repuesto)` | `SELECT item_orden ... JOIN repuesto ... WHERE item_orden.orden_id IN ($1)` |
| 4 | `selectinload(historial_estados)` | `SELECT historial_estado_orden ... WHERE orden_id IN ($1)` |
| 5 | `_roles` del servicio | `SELECT asignacion_rol.rol ... WHERE usuario_id = $1` |

La dependencia de grupo (`exigir_password_al_dia`) y la de la ruta (`UsuarioActualDep`) comparten la misma instancia cacheada por FastAPI: el usuario se lee **una** vez por petición. `_roles` es la segunda consulta de autorización porque el servicio decide «personal o dueño» con los roles vigentes de la base (RN-04), no con el token.

**Por qué no crece**:

- `joinedload` de muchos-a-uno agrega **columnas** al `SELECT`, no consultas.
- `selectinload` de una colección emite **una** consulta con `IN (ids de los padres)`. El detalle tiene **un** padre (una orden); la cantidad de ítems o de líneas de historial sólo cambia el número de filas del resultado, no el de sentencias.
- El contador se verificó también con 2 líneas de historial (tras `iniciar`): 5 consultas otra vez.

**Consecuencia**: el invariante que se prueba es la **igualdad** `conteo(2 ítems) == conteo(4 ítems)`, con un techo de 6 (lo medido + 1 de margen) y un piso de 3 para que un listener que no dispare no haga pasar `0 == 0`. Además, la prueba comprueba que `item_orden` y `historial_estado_orden` aparecen en **una** sentencia cada uno: si alguien cambia la precarga por un acceso por fila, el conteo sube y la igualdad falla.

**Alternativa descartada**: fijar el número exacto como constante rígida. El conteo incluye las consultas de autenticación; un cambio legítimo en `get_usuario_actual` (por ejemplo, leer roles del token) movería el número sin que haya N+1. La igualdad entre casos y el techo documentado son el criterio correcto.

### D3 — La ficha y «lo propio» tampoco crecen con las filas hijas

**Decisión y medición**:

| Lectura | Consultas | Composición | Comparación |
|---|---|---|---|
| `GET /clientes/{id}` | 4 | usuario + roles (ADMIN/RECEPCION) + ficha + vehículos | 1 vehículo (Jorge) vs 3 (se agregan dos por API) |
| `GET /mis-vehiculos` | 3 | usuario + ficha por `usuario_id` + vehículos | 2 (Laura) vs 3 (se agrega uno) |
| `GET /mis-ordenes` | 5 | usuario + ficha + vehículos + `count` + página | 1 orden visible vs 2 (se crea una en `AAB222`) |

En los tres casos el conteo es **idéntico** antes y después de agregar filas. La página de `/mis-ordenes` usa `joinedload(vehiculo)` (muchos-a-uno), así que sumar órdenes no agrega consultas; el `count` y la página se mantienen como dos sentencias fijas. La ficha y `/mis-vehiculos` usan el mismo `selectinload` filtrado por `borrado_en IS NULL`, de modo que un vehículo dado de baja no aparece ni cambia el conteo.

**Por qué importa la prueba y no sólo la lectura del código**: `lazy="raise_on_sql"` convierte un olvido de precarga en un error visible, pero no detecta una precarga **de más** (por ejemplo, un `selectinload` dentro de un bucle o una consulta por fila explícita). El contador sí.

**Alternativa descartada**: medir con datos sembrados a mano en SQL. La API crea las filas con los mismos caminos que usa la aplicación y respeta las restricciones (patente única, ítems únicos por orden), lo que hace que la prueba sea reproducible con sólo el seed.

### D4 — No se convierte `selectinload` en `joinedload`

**Decisión**: las precargas quedan como están.

**Por qué**: `joinedload` de una colección multiplica filas y exige `UNIQUE`/deduplicación; `selectinload` mantiene una consulta por colección y un resultado limpio. En el detalle hay una sola orden, así que una consulta por colección es óptima y perfectamente fija. Convertirlas sería un cambio de rendimiento sin medición que lo justifique y con riesgo de duplicar filas.

**Alternativa descartada**: `joinedload` para ítems e historial en la misma consulta. Ahorraría dos viajes, pero el producto cartesiano ítems × historial crecería con ambas dimensiones y complicaría el mapeo; no es lo que pide C-15.

### D5 — El aviso corre después del commit: se demuestra por aislamiento, no por el log

**Decisión**: en el test se reemplaza `app.modules.ordenes.service.avisar_cliente` con `monkeypatch.setattr` por una corrutina que abre una **sesión nueva** desde `app_viva.state.session_maker`, lee `orden_trabajo.estado` y lo registra. La prueba:

1. Crea una orden, la inicia con el mecánico y comprueba con una sesión nueva que el estado confirmado es `EN_REPARACION`. Ese es el **control**: una sesión distinta ve el estado confirmado, no el de una transacción abierta.
2. Sustituye el aviso y llama a `POST /ordenes/{id}/terminar`.
3. Verifica `200`, `TERMINADA` en la respuesta y que el aviso registró **`TERMINADA`**.

**Por qué esto prueba el orden**: con `READ COMMITTED` (el nivel por defecto de PostgreSQL), una segunda sesión no ve los cambios de una transacción que todavía no confirmó. Si el router agendara la tarea dentro del `async with` del UoW —antes del `commit()` del `__aexit__`—, la sesión nueva del aviso leería `EN_REPARACION`. Que lea `TERMINADA` sólo es posible si el `commit` ya ocurrió.

**Por qué no alcanza el log**: los dos tests existentes (`test_terminar_agenda_el_aviso_simulado` y `test_terminar_rechazado_no_agenda_el_aviso`) prueban que la tarea se ejecutó o no, pero una tarea ejecutada dentro del UoW también escribiría la línea. Además, `httpx.ASGITransport` espera las tareas de fondo antes de devolver el control, así que en la suite la tarea corre «al final de la petición» aunque en producción Starlette la corra después de enviar la respuesta; el aislamiento es la única evidencia independiente del orden.

**Conexiones**: la corrutina usa `async with fabrica() as sesion`, que cierra la sesión al salir; no quedan conexiones colgadas.

**Consecuencia**: el caso «403/404/409 no agenda» se conserva donde ya estaba y no se duplica; el `design.md` lo referencia. El `monkeypatch` se revierte solo al terminar el test y el `sleep` de medio segundo del aviso real no se ejecuta en esta prueba (por eso es más rápida que la de `C-11`).

**Alternativa descartada**: comparar timestamps del `commit` y del aviso. El reloj del sistema puede repetir la marca (se documentó en `C-08`) y la comparación sería frágil; el aislamiento es determinista.

### D6 — Auditoría de asincronía: nada bloqueante y `SQL_ECHO` con default `false`

**Decisión**:

- Todos los endpoints son `async def`; el test recorre `app.routes`, filtra `APIRoute` y falla si alguno no es corrutina. Los `def` que quedan son helpers puros (`_detalle`, `_resumen`, `_pagina`, `_poner_cookie`, `_segundos_de_sesion`) que no hacen IO.
- bcrypt corre en `asyncio.to_thread` (`hash_password`/`verify_password`) y el hash ficticio se calcula una sola vez en el lifespan.
- La búsqueda de IO bloqueante no encontró `time.sleep`, `open()`, `subprocess`, `requests`, `urllib` ni `smtplib` en `app/` ni en `main.py`.
- `Settings.SQL_ECHO` es `bool` con default `False`; `pydantic-settings` lo lee de la variable de entorno o del `.env` con el mismo nombre. El lifespan lo pasa a `create_async_engine(echo=...)`. El test comprueba el default, que `Settings(SQL_ECHO="true")` lo enciende y que el motor de la suite tiene `echo=False`.
- La suite lo fija en `SQL_ECHO=false` en `test/conftest.py` (no se modificó): activarlo inundaría la salida de los 197 tests y cambiaría el costo de cada sentencia.

**Por qué**: activar `SQL_ECHO` es la herramienta de diagnóstico que pide la KB; su default tiene que ser silencioso. La prueba no enciende el motor para medir: el contador de eventos es independiente de `echo` y no escribe en consola.

**Alternativa descartada**: dejar `SQL_ECHO` sin prueba porque «ya funciona». El requisito es explícito y el default es parte del contrato de despliegue.

### D7 — Sin cambios de esquema, de contrato ni de código

**Decisión**: el change sólo agrega `test/test_detalle.py` y los artefactos OpenSpec. No hay migraciones, modelos, rutas ni contratos nuevos, y no se modifican `test/conftest.py`, `seed.py`, `test/test_ordenes.py` ni `knowledge-base/`.

**Por qué**: el comportamiento ya cumple. Cambiar código para que una prueba «luzca» sería introducir riesgo sin necesidad. La disciplina de TDD se aplicó igual: primero se escribió la prueba con la medición impresa, se observaron los conteos reales (5/5, 4/4, 3/3, 5/5, aviso `TERMINADA`) y recién entonces se fijaron las aserciones de igualdad y techo. Si algún conteo hubiera crecido, el arreglo habría sido una precarga en el repositorio correspondiente.

**Consecuencia**: la suite pasa de 189 a 197 tests sin tocar una sola línea de producción. El rollback es borrar el archivo de test y la carpeta del change.

## Risks / Trade-offs

- **El conteo incluye las consultas de autenticación** → si `get_usuario_actual` cambia (por ejemplo, deja de leer el usuario o empieza a leer roles del token), los números medidos se mueven. Mitigación: la prueba compara **igualdad entre casos** y usa un techo con margen; el docstring y este documento registran la composición para que el ajuste sea consciente.
- **El listener es global al motor** → si la suite se ejecutara en paralelo (`pytest-xdist`) dos tests podrían mezclar conteos. La suite es secuencial por diseño (`asyncio_mode = auto`, base única con `TRUNCATE` por test). Se documenta como límite; agregar xdist exigiría una base por worker, fuera de alcance.
- **`selectinload` escala con los padres, no con los hijos** → el detalle tiene un solo padre; un futuro endpoint que cargue N órdenes y luego N detalles tendría N+1 por diseño. La prueba protege el caso que pide C-15, no un futuro endpoint inexistente.
- **La prueba de post-commit depende de `READ COMMITTED`** → es el nivel por defecto de PostgreSQL y el proyecto no lo cambia. Si se configurara `REPEATABLE READ` a nivel de servidor, el control previo (`EN_REPARACION` con sesión nueva) seguiría siendo válido porque esa transacción ya confirmó.
- **El `sleep` de 0.5 s del aviso real** → la prueba de C-12 lo reemplaza con `monkeypatch`, así que no lo espera; los dos tests de `C-11` siguen pagando ese costo. No es un problema, pero explica por qué esta prueba es la más rápida del módulo.

## Migration Plan

1. Escribir `test/test_detalle.py` con el contador y la medición impresa (TDD de medición).
2. Correr `python -m pytest test/test_detalle.py -q -s` y registrar los conteos: detalle 5/5, ficha 4/4, `/mis-vehiculos` 3/3, `/mis-ordenes` 5/5; aviso `TERMINADA`.
3. Reemplazar las impresiones por aserciones de igualdad, techo y piso, y por las comprobaciones de `item_orden`/`historial_estado_orden`/`vehiculo`/`orden_trabajo`.
4. Correr la suite completa: `python -m pytest test/ -q` → 197 passed.
5. `openspec validate 2026-10-27-c-12-detalle-sin-n1 --strict` en verde.

**Rollback**: borrar `test/test_detalle.py` y `openspec/changes/2026-10-27-c-12-detalle-sin-n1/`. No hay migraciones ni cambios en producción, así que la aplicación queda exactamente como en `C-11`.

## UI Mockups

Decision: no (no UI). Es una API sin frontend; no aplica el gate de mockups.
