# Design

Ver `proposal.md` (Why), la spec nueva `delivery-evidence` y el delta `append-only-enforcement`. Este documento explica **cómo se armó la entrega**, qué se ejecutó de verdad y qué quedó parcial.

## Context

El comportamiento del sistema ya estaba terminado y verificado por los changes `C-01` a `C-12`; lo que faltaba era la **entrega**. Al inventariar `test/` antes de tocar nada quedó claro el estado real:

- 6 archivos `.http` (`contracts`, `auth`, `rbac`, `clientes`, `repuestos`, `ordenes`) con 29 bloques: cubren C-02 a C-13 y C-16 a C-19.
- 10 archivos `test_*.py` y **197 tests** en verde contra PostgreSQL real.
- Sin evidencia de C-01 (`/health`), sin bloque de C-15 (`SQL_ECHO`), sin `test/solo_agregado.sql`, sin réplica automatizada de C-14 y sin un índice que diga dónde vive cada caso.

Restricciones del change:

- **Nada de producción**: no se tocan `app/`, `main.py`, `seed.py`, `migrations/`, `test/conftest.py` ni `pytest.ini`. Si la verificación hubiera encontrado un defecto de negocio, se reporta; no se arregla acá.
- **Stack cerrado**: la réplica de C-14 usa `sqlalchemy.text` y `pytest`, ya instalados. No hay dependencias nuevas.
- **Sin migraciones ni endpoints**: el esquema y el disparador de `0002` son los que ya existen.
- **No commit, no archivo**: el cierre lo hace el orquestador.

## Goals / Non-Goals

**Goals:**

- Que un corrector abra `test/`, encuentre el caso que busca por la matriz y pueda volver a correr la evidencia sin leer código.
- Cubrir los tres huecos reales de evidencia: C-01, C-14 y C-15.
- Que el disparador de sólo agregado y la FK del catálogo tengan réplica en la suite, para que quitar la migración `0002` la ponga roja.
- Ejecutar y registrar la verificación integral: suite, ciclo Alembic sobre base vacía, seed idempotente y secretos.

**Non-Goals:**

- Agregar casos que la consigna no pide ni reescribir los `.http` que ya funcionan.
- Convertir la evidencia en una herramienta de CI, un runner propio de `.http` o un reporte HTML.
- Arreglar el logging de la aplicación (se documenta el defecto; ver D6).
- Archivar el change o commitear.

## Decisions

### D1 — La evidencia existente no se mueve; la matriz es el índice

**Decisión**: los `.http` siguen agrupados por módulo (`auth.http`, `ordenes.http`, …), se agrega `health.http` para C-01 y sólo se **agregan** bloques a los archivos existentes (C-15 en `ordenes.http`) o se corrigen los que podían ejecutarse de forma no concluyente (C-03). `test/MATRIZ_CASOS.md` es el único índice: caso, qué verifica, archivo + bloque, test y estado.

**Por qué**: un archivo por módulo refleja cómo se prueba la API (un login sirve para varios bloques siguientes) y ya era el formato del proyecto; reordenarlo a un archivo por caso rompería las dependencias de estado (cookie, ids, datos creados) y multiplicaría el trabajo sin mejorar la legibilidad. La matriz resuelve el problema real —no saber dónde está cada caso— sin duplicar contenido.

**Consecuencia**: la matriz se mantiene a mano. Es un riesgo aceptado y barato: si se agrega un caso, el `validate` no lo detecta, pero el checklist de tareas del change y la revisión lo hacen visible.

**Alternativa descartada**: un `C-01.http` … `C-19.http`. Diecinueve archivos con su propio login y su propio estado, imposibles de correr en secuencia y con el doble de mantenimiento.

### D2 — C-14 se demuestra dos veces: psql para el corrector, pytest para la suite

**Decisión**:

- `test/solo_agregado.sql` es la evidencia que pide el Flujo 13: seis `UPDATE`/`DELETE` (3 tablas × 2 operaciones), el `INSERT` con `estado = 'INVENTADO'` y los conteos finales. Se ejecuta con psql, sin ORM y sin la aplicación.
- `test/test_solo_agregado.py` es la réplica automatizada (10 tests): mismo SQL por `sqlalchemy.text` sobre el motor de la suite, más la comprobación de que las filas y sus valores quedan intactos, que `TRUNCATE` no dispara el disparador y que `INSERT` sigue permitido.

**Por qué las dos**: el `.sql` es lo que el enunciado evalúa y no depende de Python ni de pytest; el test es lo que protege el comportamiento a futuro. Sin la réplica, borrar la migración `0002` dejaría la suite en verde: el caso C-14 sería la única parte del sistema sin red. Con la réplica, el disparador y la FK son parte del contrato ejecutable.

**Decisión de aserción**: se asserta el **SQLSTATE** (`23000` para el disparador, `23503` para la FK) y no el texto. El servidor de este equipo tiene `lc_messages = Spanish_Argentina.1252`, así que el mensaje llega traducido (`«orden_trabajo»`, `llave foránea`) y la consola de PowerShell además lo manglea. El texto se comprueba sólo con fragmentos ASCII estables (`"es de sólo agregado"`, `"UPDATE no está permitido"`), nunca como única aserción.

**Decisión de transacción**: cada intento abre su propia transacción con `motor.begin()`. Un error buscado **aborta** la transacción en PostgreSQL; reutilizar la conexión haría fallar el intento siguiente con «current transaction is aborted» y el test mediría el error equivocado. `TRUNCATE` e `INSERT` también corren en transacciones que terminan en `rollback`, así que la prueba no deja basura ni exige resembrar.

**Alternativa descartada**: usar el ORM para provocar el `UPDATE`. El disparador es de base y el ORM agregaría capas (sesión, flush, UoW) que podrían enmascarar el error; SQL crudo demuestra exactamente lo que pide el caso.

### D3 — Resultado real del script psql

Ejecutado contra una base creada desde cero, migrada y sembrada (`taller_mecanico_verif`). Extracto real (se conservan los acentos; la consola de PowerShell los muestra mangleados, el archivo no):

```text
--- 1/6 UPDATE historial_estado_orden (esperado: ERROR 23000) ---
ERROR:  La tabla historial_estado_orden es de sólo agregado: UPDATE no está permitido
SUGERENCIA:  Agregá una fila nueva en lugar de modificar o borrar la existente.
CONTEXTO:  función PL/pgSQL solo_agregado_rechazar_modificacion() en la línea 3 en RAISE
```

Los seis rechazos salen con la misma forma, cambiando tabla y operación (`DELETE no está permitido` en los pares 2/6, 4/6 y 6/6):

| # | Tabla | Operación | Resultado |
|---|---|---|---|
| 1/6 | `historial_estado_orden` | `UPDATE` | rechazado por el disparador |
| 2/6 | `historial_estado_orden` | `DELETE` | rechazado por el disparador |
| 3/6 | `movimiento_stock` | `UPDATE` | rechazado por el disparador |
| 4/6 | `movimiento_stock` | `DELETE` | rechazado por el disparador |
| 5/6 | `historial_precio_repuesto` | `UPDATE` | rechazado por el disparador |
| 6/6 | `historial_precio_repuesto` | `DELETE` | rechazado por el disparador |
| — | `orden_trabajo` | `INSERT` con `'INVENTADO'` | rechazado por `fk_orden_trabajo_estado` |

Y los conteos finales, que son la prueba de que ninguno escribió nada:

```text
           tabla           | filas
---------------------------+-------
 historial_estado_orden    |     3
 historial_precio_repuesto |     1
 movimiento_stock          |     4

 id | repuesto_id | precio_anterior | precio_nuevo
----+-------------+-----------------+--------------
  1 |           1 |         8000.00 |      8500.00

 id | repuesto_id | cantidad |    motivo
----+-------------+----------+---------------
  1 |           1 |       10 | Stock inicial
  2 |           2 |        4 | Stock inicial
  3 |           3 |        2 | Stock inicial
  4 |           4 |       20 | Stock inicial
```

El proceso termina con **código 0** pese a los siete errores: `\set ON_ERROR_STOP off` está explícito en el script y los errores son el resultado buscado. La cabecera del `.sql` documenta el comando, el comportamiento de psql y la nota de `TRUNCATE`, para que el corrector no dependa de este documento.

### D4 — La entrega se verifica de punta a punta (resultados reales)

**Ciclo Alembic** sobre `taller_mecanico_verif` (base creada vacía, sin tablas):

```text
upgrade head     → exit 0
  Running upgrade  -> 0001, crea las tablas del dominio
  Running upgrade 0001 -> 0002, sólo agregado: rechaza UPDATE y DELETE en las tablas de auditoría
downgrade base   → exit 0
  Running downgrade 0002 -> 0001, sólo agregado: ...
  Running downgrade 0001 -> , crea las tablas del dominio
upgrade head     → exit 0
  Running upgrade  -> 0001, crea las tablas del dominio
  Running upgrade 0001 -> 0002, sólo agregado: ...
```

Estado final comprobado con psql: `alembic_version = 0002`, **13** tablas de dominio (más `alembic_version`) y **3** disparadores no internos.

**Seed** corrido dos veces sobre esa misma base, con los mismos conteos:

| Tabla | Corrida 1 | Corrida 2 |
|---|---|---|
| `usuario` | 7 | 7 |
| `asignacion_rol` | 7 | 7 |
| `cliente` | 2 | 2 |
| `vehiculo` | 3 | 3 |
| `repuesto` | 4 | 4 |
| `movimiento_stock` | 4 | 4 |
| `orden_trabajo` | 2 | 2 |
| `item_orden` | 1 | 1 |
| `historial_estado_orden` | 3 | 3 |
| `historial_precio_repuesto` | 1 | 1 |
| `evento_seguridad` | 1 | 1 |
| `estado_orden` | 4 | 4 |
| `intento_acceso` | 0 | 0 |

`seed.py` no se modificó: ya reinicia con `TRUNCATE ... RESTART IDENTITY CASCADE`, y el disparador no cubre `TRUNCATE` (por eso el C-14 lo documenta y lo prueba). Conteos distintos de los del enunciado (`historial_estado_orden` = 3, no 4) se registran tal como salen: el script siembra tres transiciones, no cuatro.

**Suite completa**: `python -m pytest test/ -q` desde la raíz → **207 passed** (197 previos + 10 de C-14) en 62,94 s.

**Secretos**: `Settings.model_fields["SECRET_KEY"].is_required()` y `["POSTGRES_PASSWORD"].is_required()` → `True True`; `Settings(_env_file=None)` sin entorno → **2 validation errors** (`SECRET_KEY`, `POSTGRES_PASSWORD`); `.env` en `.gitignore:9`; `git ls-files` (215 archivos) no incluye `.env`, claves ni credenciales.

**Limpieza**: `DROP DATABASE taller_mecanico_verif WITH (FORCE)`; ninguna variable de entorno quedó seteada en la sesión del usuario (cada comando corrió en su propio proceso) y no quedó ningún uvicorn escuchando en 8000.

### D5 — Los bloques críticos se ejecutaron contra la app real, no se copiaron de la suite

**Decisión**: levantar `uvicorn main:app` contra la base sembrada y ejecutar los bloques `.http` que dependen de estado o de detalles de transporte, en vez de confiar en que «el test equivalente ya pasa».

**Qué se comprobó (20/20 OK)**: C-01 (`/health/live` y `/health/ready`), C-02 (409 con documento repetido), C-03 (Bearer sin cookie → **401**; la misma ruta con cookie → **200** y `roles_vigentes: ["ADMIN"]`), C-05 (sexto login → **429** con `Retry-After`), C-06 (orden propia **200** / ajena **403**), C-09 (**409** después de `TRUNCATE estado_orden CASCADE`), C-10 (repuesto inexistente → **409**), C-11 (stock insuficiente → **409**), C-12 (línea de log real), C-13 (terminada → **409**), C-16 (`PATCH` con `stock` → **422**; inyección → lista vacía), C-17 (`estado=INVENTADO` → **422**), C-18 (una línea de historial por cambio, ninguna con el mismo precio) y C-19 (baja de `AAB222`, alta de la misma patente → **201**, segunda alta → **409**).

**Por qué importa**: los tests usan `httpx.ASGITransport`, que no ejercita exactamente el mismo camino que un servidor real (por ejemplo, el manejo de cookies y el orden de las tareas de fondo). Ejecutar el `.http` contra uvicorn verifica el contrato tal como lo va a ver el corrector.

**Consecuencia**: la base `taller_mecanico` quedó con datos de las pruebas (órdenes nuevas, precios cambiados, `AAB222` dada de baja). Es esperable: los `.http` escriben. La matriz documenta que hay que resembrar entre archivos y después del bloque destructivo de C-09.

**Alternativa descartada**: generar la evidencia con un script que llame a la API y volcar las respuestas a los comentarios. Produciría archivos que parecen `.http` pero no se pueden ejecutar a mano, y el corrector perdería la posibilidad de reproducir el caso.

### D6 — Defecto de evidencia del log de C-12 (documentado, no arreglado en producción)

**Qué pasó**: al ejecutar el bloque de C-12 con el arranque natural (`uvicorn main:app`) no aparecía la línea del aviso, aunque la tarea sí se ejecutaba (el test de C-12 lo prueba por aislamiento y pasa). La causa es de **logging**, no de negocio: `app.ordenes` emite con `logging.getLogger(__name__).info(...)`, pero uvicorn configura sus propios loggers y deja el root en `WARNING`; sin configuración de la aplicación, el `INFO` queda filtrado.

**Cómo se corrigió la evidencia**: el bloque documenta el arranque con el root en `INFO`:

```python
import logging, uvicorn
logging.basicConfig(level=logging.INFO)
uvicorn.run("main:app", host="127.0.0.1", port=8000)
```

Con ese arranque la línea real es:

```text
INFO:app.ordenes:Aviso simulado al cliente: la orden 5 está terminada.
```

**Por qué no se arregla `main.py`**: agregar `basicConfig` o un `dictConfig` es un cambio de producción con efecto en todos los entornos, y C-13 no lo tiene en alcance. Queda anotado como deuda conocida en `tasks.md`; el comportamiento (avisar después del commit) ya está cubierto por el test.

**Alternativa descartada**: dejar el bloque con el comando por defecto y una nota de que «a veces no se ve». Una evidencia que no muestra lo que afirma no sirve; el arranque explícito es reproducible.

### D7 — Casos parciales: qué cubre cada pieza y qué no

| Caso | Parte manual / fuera de HTTP | Por qué es aceptable |
|---|---|---|
| C-01 (503) | Detener el servicio de PostgreSQL para ver el 503 | El `.http` documenta `Stop-Service`/`Start-Service` y la respuesta esperada; la suite prueba el mismo camino con un doble de `get_session`, así que la lógica del 503 no queda sin red |
| C-09 | `TRUNCATE estado_orden CASCADE` por psql antes del bloque | La API es de sólo lectura sobre el catálogo (DD-07): no hay endpoint que lo vacíe. El bloque trae el comando, la salida esperada y el `python seed.py` para restaurar |
| C-12 | Ver la línea de log requiere el arranque con root en INFO | D6. El **cuándo** (post-commit) no lo prueba el log sino el test de aislamiento |
| C-14 | No es HTTP: el disparador se demuestra en la base | Es el diseño del Flujo 13; el `.sql` es ejecutable y la réplica automatizada cubre el mismo contrato |
| C-15 | El `.http` no puede contar consultas: documenta `SQL_ECHO=true` y el conteo esperado (5 con 2 ítems y 5 con 4) | La medición real se hizo con `SQL_ECHO=true` y el test la fija con un contador `before_cursor_execute` |

**Por qué se documentan y no se esconden**: la matriz tiene una columna «Estado» que dice «Completo con paso previo» en vez de fingir que el `.http` hace todo. Un corrector que lea la limitación sabe exactamente qué ejecutar.

### D8 — Sin cambios de producción, sin dependencias, sin migraciones

**Decisión**: el change sólo agrega `test/solo_agregado.sql`, `test/test_solo_agregado.py`, `test/health.http`, `test/MATRIZ_CASOS.md` y los artefactos OpenSpec; agrega bloques a `test/ordenes.http` y `test/repuestos.http`, y corrige el bloque 8 de `test/auth.http`.

**Por qué**: la funcionalidad ya cumple. Tocar código para que una prueba «luzca» sería introducir riesgo en la última semana del TP. La disciplina de TDD se aplicó a la parte nueva: primero la réplica de C-14 con el error impreso, se observaron SQLSTATE `23000`/`23503`, después se fijaron las aserciones, y recién entonces se escribió el `.sql`.

**Consecuencia**: el rollback es borrar los cuatro archivos nuevos, revertir los tres `.http` y borrar la carpeta del change. La aplicación queda exactamente como en `C-12`.

## Risks / Trade-offs

- **La matriz se desincroniza a mano** → no hay validación automática de que cada caso siga apuntando a un test existente. Mitigación: es un documento de entrega, no de ejecución; el `openspec validate` cubre la spec y la suite cubre el comportamiento.
- **Los `.http` dependen del estado del seed** → ejecutarlos fuera de orden da falsos negativos (ids, catálogo vacío, patente ya usada). Mitigación: `test/MATRIZ_CASOS.md` §1 fija el orden y recuerda `python seed.py` entre archivos.
- **La réplica de C-14 usa el motor de la suite** → comparte la base con el resto de los tests y depende de los conteos del seed (3/4/1). Mitigación: `test/conftest.py` resiembra por test; si el seed cambia, la prueba falla de forma explícita y no silenciosa.
- **El SQLSTATE es estable, el mensaje no** → una actualización de PostgreSQL o un cambio de `lc_messages` no rompe la aserción principal. Es deliberado.
- **El 503 de `/health/ready` no se ejecutó contra un PostgreSQL detenido** → se documenta como manual; el test con doble cubre la rama. Detener el servicio del equipo durante la verificación habría afectado otros procesos.
- **La base `taller_mecanico` queda con datos de las pruebas** → los `.http` escriben por diseño. No se limpia porque es la base de trabajo del usuario; la verificación integral se hizo sobre una base descartable.

## Migration Plan

Ya ejecutado, en este orden:

1. Línea base: `python -m pytest test/ -q` → 197 passed.
2. Escribir `test/test_solo_agregado.py`, sondear los SQLSTATE reales y dejarlo en verde (10 passed).
3. Escribir `test/solo_agregado.sql` y correrlo con psql sobre una base sembrada (7 errores buscados, exit 0).
4. Crear `test/health.http`; agregar C-15 a `ordenes.http` y renumerar C-09; corregir C-03 en `auth.http`; referenciar C-14 en `repuestos.http`.
5. Ejecutar los bloques críticos contra uvicorn + PostgreSQL real (20/20 OK).
6. Publicar `test/MATRIZ_CASOS.md` (19 casos + parciales + 8 criterios).
7. Verificación integral: ciclo Alembic sobre base vacía, seed dos veces, secretos, suite completa (207 passed).
8. `openspec validate 2026-10-27-c-13-casos-de-prueba --strict` en verde.
9. Limpieza: `DROP DATABASE taller_mecanico_verif`, sin procesos en 8000.

**Rollback**: borrar `test/solo_agregado.sql`, `test/test_solo_agregado.py`, `test/health.http`, `test/MATRIZ_CASOS.md` y la carpeta `openspec/changes/2026-10-27-c-13-casos-de-prueba/`; revertir los tres `.http`. Sin migraciones ni cambios de producción, la aplicación queda igual que en `C-12`.

## UI Mockups

Decision: no (no UI). Es una API sin frontend; no aplica el gate de mockups.
