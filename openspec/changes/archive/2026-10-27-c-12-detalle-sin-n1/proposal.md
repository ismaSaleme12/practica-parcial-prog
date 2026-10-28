# Proposal

## Why

La API ya funciona de punta a punta: autentica, autoriza, administra clientes, vehículos, repuestos y órdenes, y la terminación de una orden descuenta stock en una sola transacción. Pero el Ejercicio 8 de la consigna no pide una funcionalidad nueva: pide **demostrar** que las lecturas no se degradan con el volumen de datos y que las tareas de fondo no mienten.

Hoy esa garantía existe en el código —`get_detalle` precarga con `joinedload`/`selectinload`, las relaciones declaran `lazy="raise_on_sql"`, el router agenda el aviso después del `await` del servicio y `Settings.SQL_ECHO` alimenta el `echo` del motor—, pero **no está medida**. Sin medición:

1. **El caso C-15 queda como una afirmación.** «2 y 4 ítems dan las mismas consultas» es exactamente lo que hay que probar: si alguien reemplaza un `selectinload` por un acceso directo, la lectura sigue respondiendo 200 con pocos datos y sólo se degrada en producción. Un contador `before_cursor_execute` sobre el motor real convierte la promesa en una prueba que falla sola.
2. **La ficha y «lo propio» nunca se contaron.** `GET /clientes/{id}`, `/mis-vehiculos` y `/mis-ordenes` dicen «sin carga perezosa» en su documentación, pero nadie comprobó que el conteo no crezca al agregar vehículos u órdenes. Un `selectinload` olvidado en una rama nueva no lo detecta ningún test funcional si la respuesta sigue siendo correcta.
3. **El aviso post-commit se verifica por el log, no por el aislamiento.** Los dos tests de `C-11` prueban «se agendó» y «no se agendó», pero no prueban **cuándo**: una tarea que corriera dentro del UoW también dejaría la línea del log. Abrir una **sesión nueva** desde la tarea y leer el estado muestra la diferencia: dentro de la transacción vería `EN_REPARACION`; después del commit ve `TERMINADA`.
4. **`SQL_ECHO` es un requisito de diagnóstico de la KB** («las consultas se pueden ver en la consola») y no tenía prueba ni documentación del default. Activarlo por error en la suite o en producción cambiaría el rendimiento y la salida; hay que fijar que el default es `false` y que se enciende sólo por entorno.

Este change cierra el gate 9 del roadmap: sin él, `C-13` no puede presentar la evidencia de C-15 ni de C-12 como casos automatizados.

## What Changes

- **`test/test_detalle.py`** (nuevo, 8 tests): es el único artefacto ejecutable del change. No se toca código de producción porque el comportamiento ya está implementado y verificado en `C-09`, `C-11` y `C-12` de la KB; la suite **mide** y falla si se rompe.
  - Contador `before_cursor_execute` registrado sobre `motor.sync_engine` (`sqlalchemy.event.listen`), sin mocks de base ni dependencias nuevas.
  - **C-15**: dos órdenes creadas por API sobre el mismo vehículo, una con 2 ítems y otra con 4 (los cuatro repuestos del seed, cantidad 1), medidas con el mismo cliente y la misma sesión. El conteo es **idéntico**; además se comprueba que la orden, los ítems y el historial se traen en **una** consulta cada uno.
  - El detalle no crece con el historial (1 → 2 líneas tras `iniciar`).
  - `GET /clientes/{id}` con 1 y 3 vehículos; `/mis-vehiculos` con 2 y 3; `/mis-ordenes` con 1 y 2 órdenes visibles.
  - **C-12**: `monkeypatch` de `service.avisar_cliente` por una corrutina que abre una sesión nueva desde `app.state.session_maker` y registra el estado que ve. El aviso ve `TERMINADA`; un control previo, también con sesión nueva, ve `EN_REPARACION` mientras la orden está en reparación.
  - US-026 CA-3: introspección de `app.routes` para comprobar que **todos** los endpoints son `async def`.
  - `SQL_ECHO`: default `false` en `Settings`, activable con `SQL_ECHO=true` y cableado al `echo` del motor.
- **Sin cambios de producción**: no se agregan ni modifican endpoints, contratos, modelos, repositorios, servicios, migraciones, `seed.py` ni `test/conftest.py`. La auditoría de asincronía encontró que todos los handlers son `async def`, que bcrypt corre en `asyncio.to_thread` y que no hay `time.sleep`, `open()`, `subprocess` ni clientes HTTP síncronos.
- **Sin N+1 que corregir**: las lecturas medidas ya usan precargas fijas. Si la medición hubiera detectado una consulta por fila, el arreglo habría ido al repositorio con `selectinload`/`joinedload` y quedaría documentado acá; no fue necesario.

## Capabilities

### New Capabilities

- `read-performance`: invariantes medibles de lectura — conteo fijo de consultas en el detalle y en las lecturas con filas hijas, prohibición de carga perezosa, verificación con un contador de cursor, handlers asincrónicos y `SQL_ECHO` habilitable con default `false`.

### Modified Capabilities

- `work-order-management`: el requisito del detalle fija ahora el **criterio medible** (cinco consultas en la petición completa, idénticas con 2 y 4 ítems) además de las tres consultas del repositorio.
- `work-order-lifecycle`: el requisito del aviso agrega la evidencia de **post-commit por aislamiento** —una sesión nueva ve `TERMINADA`— y mantiene el rechazo (403/404/409) sin aviso.

## Impact

- **Código de producción**: ninguno. El change es una verificación (TDD de medición): el test se escribió primero, se observó el conteo real y se fijó la igualdad entre casos con un techo holgado.
- **Evidencia**: `test/test_detalle.py` (8 tests nuevos; la suite pasa de 189 a 197).
- **Base de datos**: sin migraciones ni cambios de esquema. La medición usa la base de test real; el `TRUNCATE`/seed del andén corre antes de cada test y queda fuera del contador, igual que el login.
- **Dependencias**: ninguna nueva. `sqlalchemy.event` viene con SQLAlchemy 2.0; `fastapi.routing.APIRoute` y `inspect` son de la biblioteca estándar.
- **Contratos**: sin cambios. El detalle, la ficha, `/mis-vehiculos` y `/mis-ordenes` responden exactamente igual que en `C-11`/`C-09`.
- **Diagnóstico**: `SQL_ECHO=true` (entorno o `.env`) imprime las sentencias del motor; el default sigue siendo `false` y la suite lo fija en `false`.
- **Habilitado**: `C-13 casos-de-prueba`, que consolida la matriz C-01..C-19 con la evidencia de C-15 y C-12.
