# Tasks

> Change de entrega: no hay funcionalidad nueva. El orden real de trabajo fue:
> (1) escribir primero la réplica de C-14 y verla pasar contra PostgreSQL real,
> (2) escribir el `.sql` y correrlo con psql, (3) completar los `.http` que
> faltaban y verificar los bloques críticos **contra la app levantada**,
> (4) publicar la matriz y (5) ejecutar la verificación integral. Cada ítem
> registra cómo se comprobó.

## 0. Punto de partida

- [x] 0.1 Confirmar la línea base antes de tocar nada: `python -m pytest test/ -q` desde la raíz → **197 passed** en 61,61 s. Verificación: ninguna prueba previa se modificó y `test/conftest.py` no se tocó.
- [x] 0.2 Inventariar la evidencia existente: `test/contracts.http`, `auth.http`, `rbac.http`, `clientes.http`, `repuestos.http`, `ordenes.http` (29 bloques en total) y 10 archivos `test_*.py`. Verificación: `Select-String` de los `###` de cada archivo; los casos C-02..C-13 y C-16..C-19 ya tenían bloque.
- [x] 0.3 Detectar los huecos: sin evidencia de C-01 (`/health`), sin bloque de C-15 (`SQL_ECHO`), sin `solo_agregado.sql`, sin réplica de C-14 y sin índice/matriz. Verificación: búsqueda de `health.http`, `SQL_ECHO` y `solo_agregado` en `test/` → sin resultados antes de este change.

## 1. C-14 — réplica automatizada (TDD)

- [x] 1.1 Escribir primero `test/test_solo_agregado.py` con SQL crudo (`sqlalchemy.text`) y sin dependencias nuevas. Verificación: el archivo usa `motor` de `conftest.py`; no agrega imports fuera de `pytest` y `sqlalchemy`.
- [x] 1.2 Sondear el error real antes de escribir las aserciones: `UPDATE`/`DELETE` sobre las tres tablas devuelven `IntegrityError` con `sqlstate = 23000`; el `INSERT` con `'INVENTADO'` devuelve `ForeignKeyViolationError` con `sqlstate = 23503` y el nombre `fk_orden_trabajo_estado`. Verificación: script de sonda descartable; se conservó el SQLSTATE como contrato y el texto localizado (`lc_messages = Spanish_Argentina.1252`) sólo como comprobación de tabla y operación.
- [x] 1.3 Un intento por transacción: `async with motor.begin()` en cada caso, para que una transacción abortada no arrastre a la siguiente. Verificación: 10 tests verdes seguidos, sin `ROLLBACK` manual.
- [x] 1.4 Cubrir los seis rechazos con `parametrize` (3 tablas × UPDATE/DELETE), la FK del catálogo, la integridad de las filas (conteos y valores: precio 8500.00, stock 2, orden 2 en EN_REPARACION), `TRUNCATE` permitido dentro de una transacción que revierte e `INSERT` permitido. Verificación: `python -m pytest test/test_solo_agregado.py -q` → **10 passed**.
- [x] 1.5 Confirmar que los tests no dejan basura: la transacción de `TRUNCATE` y la del `INSERT` terminan en `rollback` y el test siguiente vuelve a sembrar. Verificación: correr el archivo dos veces seguidas → 10 passed en ambas.

## 2. C-14 — evidencia psql

- [x] 2.1 Crear `test/solo_agregado.sql` con los seis `UPDATE`/`DELETE` (uno por tabla y operación), el `INSERT` con `'INVENTADO'` y los conteos finales. Verificación: ejecutado con psql 18 contra `taller_mecanico_verif`.
- [x] 2.2 Cabecera con el comando exacto (`psql -U postgres -d taller_mecanico -f test/solo_agregado.sql`, y la variante con la ruta completa de psql en PowerShell), la salida esperada y `\set ON_ERROR_STOP off` explícito. Verificación: el script llega al final pese a los siete errores y el proceso termina con **código 0**.
- [x] 2.3 Documentar que `TRUNCATE` no dispara el disparador y por eso `seed.py` puede reiniciar; remitir a la réplica automatizada de esa nota. Verificación: `test_solo_agregado.py::test_truncate_no_dispara_el_disparador_y_el_seed_puede_reiniciar`.
- [x] 2.4 Verificar que la base queda intacta: los conteos finales dan 3 / 4 / 1 y los valores del seed (8000.00 → 8500.00 en el historial del filtro; cuatro «Stock inicial»). Verificación: salida real pegada en `design.md` (D3).

## 3. Evidencia `.http` completa

- [x] 3.1 Crear `test/health.http` para C-01: arranque sin secretos (ValidationError con 2 errores), `live`, `ready` y el 503 con el servicio detenido. Verificación: `live` y `ready` ejecutados contra la app levantada (200/200 y 200/`{"status":"ready"...}`); el caso sin secretos, con `Settings(_env_file=None)` → **2 validation errors**.
- [x] 3.2 Agregar el bloque 21 de C-15 en `test/ordenes.http` (paso previo `SQL_ECHO=true`, alta de una orden de 2 y otra de 4 ítems, conteo esperado) y renumerar el bloque destructivo de C-09 a 22. Verificación: medición real con `SQL_ECHO=true` → **5 SELECT con 2 ítems y 5 con 4**, `item_orden` una sola vez en cada una.
- [x] 3.3 Corregir el bloque 8 de `test/auth.http` (C-03): indicar que hay que borrar la cookie antes de mandar el `Bearer`, porque con la cookie del bloque 4 la respuesta correcta es 200. Verificación: con un cliente sin cookie, `GET /auth/yo` + Bearer → **401**; con cookie → **200** y `roles_vigentes: ["ADMIN"]`.
- [x] 3.4 Documentar en `test/ordenes.http` cómo ver la línea del aviso de C-12 (`logging.basicConfig(level=logging.INFO)` + `uvicorn.run`), porque el comando por defecto no la muestra. Verificación: con ese arranque, el log real es `INFO:app.ordenes:Aviso simulado al cliente: la orden 5 está terminada.` (defecto de evidencia detectado y corregido; ver `design.md` D6).
- [x] 3.5 Agregar en `test/repuestos.http` la referencia a `test/solo_agregado.sql` y `test/test_solo_agregado.py` para el C-14. Verificación: el encabezado del archivo lo menciona junto a RN-15.
- [x] 3.6 Ejecutar los bloques HTTP críticos contra la app real (uvicorn + PostgreSQL, base sembrada): C-01, C-02, C-03, C-05, C-06, C-09, C-10, C-11, C-12 (log), C-13, C-16, C-17, C-18 y C-19 → **20/20 comprobaciones OK**. Verificación: salida real en `design.md` (D5).

## 4. Matriz de paridad y checklist

- [x] 4.1 Crear `test/MATRIZ_CASOS.md` con las columnas **Caso | Qué verifica | Evidencia `.http` (archivo + bloque) | Prueba pytest | Estado** y los **19 casos** (C-01 a C-19). Verificación: 19 filas; ninguna celda de evidencia vacía.
- [x] 4.2 Justificar los casos que no son 100 % HTTP (C-01 503, C-09, C-12, C-14, C-15) en una tabla aparte. Verificación: cada fila dice qué parte cubre el `.http`/`.sql` y qué parte el test.
- [x] 4.3 Agregar el orden de ejecución de los `.http` y el recordatorio de `python seed.py` entre archivos (el bloque 22 de `ordenes.http` vacía el catálogo). Verificación: el orden respeta las dependencias de estado y los ids del seed.
- [x] 4.4 Agregar el checklist de los **8 criterios** de `01_vision_y_objetivos.md` §Métricas de éxito, cada uno con dónde se cumple y cómo se verificó (comando o test). Verificación: 8 filas, con los pesos 8/14/10/16/14/20/10/8.

## 5. Verificación integral (ejecutada)

- [x] 5.1 Suite completa: `python -m pytest test/ -q` desde la raíz → **207 passed** (197 previos + 10 nuevos) en 62,76 s (la última corrida de cierre dio 62,94 s).
- [x] 5.2 Ciclo Alembic sobre base vacía descartable `taller_mecanico_verif`: `upgrade head` (0001 → 0002), `downgrade base` (0002 → 0001 → base), `upgrade head` de nuevo → los tres comandos con exit code 0. Verificación: `alembic_version = 0002`, **13** tablas de dominio + `alembic_version` y **3** disparadores de sólo agregado.
- [x] 5.3 `python seed.py` sobre la base recién migrada → 7 usuarios, 7 asignaciones, 2 clientes, 3 vehículos, 4 repuestos, 4 movimientos, 2 órdenes, 1 ítem, 3 líneas de historial de estados, 1 línea de historial de precios, 1 evento, 4 estados, 0 intentos. Verificación: conteos con psql.
- [x] 5.4 Segunda corrida de `seed.py` → **los mismos conteos** (reinicia sin duplicar); el script es idempotente por sí mismo, no hubo que cambiarlo.
- [x] 5.5 Secretos: `Settings.model_fields["SECRET_KEY"].is_required()` y `["POSTGRES_PASSWORD"].is_required()` → `True`; sin entorno y sin `.env` (`Settings(_env_file=None)`) → **2 validation errors**; `.env` ignorado por git (`.gitignore:9`) y `git ls-files` sin `.env`, claves ni credenciales.
- [x] 5.6 Limpieza: `DROP DATABASE taller_mecanico_verif WITH (FORCE)` y ningún proceso uvicorn escuchando en 8000; no se dejaron variables de entorno seteadas (cada comando corrió en su propio proceso).
- [x] 5.7 `openspec validate 2026-10-27-c-13-casos-de-prueba --strict` en verde.

## Workflow follow-up

- **No archivar ni commitear desde este change**: lo hace el orquestador.
- **Deuda conocida (no bloqueante)**: el log del aviso (`app.ordenes`) queda filtrado con `uvicorn main:app` porque no hay configuración de logging de la aplicación; la evidencia se corrigió documentando el arranque con el root en INFO. Arreglarlo en `main.py` sería un cambio de producción fuera del alcance de C-13.
- **Deuda conocida (no bloqueante)**: existen bases `taller_mecanico_c09/c10/c11` de changes anteriores; no se tocaron. La base descartable de esta verificación (`taller_mecanico_verif`) fue eliminada.
- **Deuda conocida (no bloqueante)**: el 503 de `/health/ready` en `.http` requiere detener el servicio de PostgreSQL; la suite lo cubre con un doble de `get_session`.
