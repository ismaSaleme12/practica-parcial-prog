# Proposal

## Why

El TP está implementado de punta a punta y la suite pasa, pero **la entrega no está armada**. La consigna evalúa con una tabla de ocho criterios y exige, como condición dura, que el proyecto levante, que cree su esquema con `alembic upgrade head` sobre una base vacía y que no contenga credenciales reales; además pide los casos de prueba como archivos `.http` con la respuesta esperada en comentarios y un `test/solo_agregado.sql` para el C-14. Hoy:

1. **La evidencia está dispersa y tiene huecos.** Los `.http` existen por módulo, pero no hay ninguno para C-01 (`/health`), no hay bloque para C-15 (conteo de consultas con `SQL_ECHO`) y el de C-03 (Bearer vs cookie) se puede ejecutar de una forma que no prueba nada si la cookie del login sigue en el tarro. Un corrector que abra `test/` no tiene un índice que le diga dónde está cada caso.
2. **El caso C-14 no tiene script.** El Flujo 13 pide `test/solo_agregado.sql` con los seis rechazos de `UPDATE`/`DELETE`, el rechazo de la clave foránea del catálogo y la captura de psql. Sin ese archivo, el criterio de Integridad (10 %) queda sin su evidencia específica.
3. **La réplica automatizada de C-14 no existe.** Los otros 18 casos tienen test; el disparador de sólo agregado y la FK del catálogo no. Si alguien quitara la migración `0002`, la suite seguiría verde.
4. **Nadie corrió la verificación final de la entrega.** No hay registro de: suite completa, ciclo `upgrade head → downgrade base → upgrade head` sobre una base vacía, `seed.py` corrido dos veces (idempotencia), ni comprobación de que `SECRET_KEY`/`POSTGRES_PASSWORD` siguen siendo obligatorios y que el repo no versiona credenciales.
5. **Falta el checklist de los 8 criterios.** La KB tiene la tabla de evaluación; el proyecto no dice, criterio por criterio, dónde se cumple y cómo se verificó.

Este change no agrega funcionalidad: cierra la entrega. Es el último del camino crítico (`C-13` depende de `C-12`).

## What Changes

- **`test/solo_agregado.sql`** (nuevo): script ejecutable con psql contra la base sembrada. Seis intentos de `UPDATE`/`DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` (el disparador de la migración `0002` los rechaza con SQLSTATE `23000`), un `INSERT` de `orden_trabajo` con `estado = 'INVENTADO'` rechazado por la FK (SQLSTATE `23503`) y conteos finales que prueban que no se escribió nada. Cabecera con el comando, la salida esperada, el detalle de que psql sigue tras cada error (exit code 0) y la nota de que `TRUNCATE` **no** dispara el disparador (por eso el seed puede reiniciar).
- **`test/test_solo_agregado.py`** (nuevo, 10 tests): réplica automatizada de C-14 con SQL crudo vía el motor (`sqlalchemy.text`), sin psql y sin dependencias nuevas. Cada intento en su propia transacción (`motor.begin()`), assert del SQLSTATE además del mensaje, filas intactas al final, `TRUNCATE` permitido dentro de una transacción que revierte e `INSERT` que sigue permitido.
- **`test/health.http`** (nuevo): evidencia de C-01 —arranque sin secretos, `/health/live`, `/health/ready` y el 503 con la base caída— con los comandos y la salida esperada.
- **`test/ordenes.http`**: bloque 21 nuevo para C-15 (levantar con `SQL_ECHO=true`, crear una orden de 2 ítems y otra de 4, contar las 5 sentencias), renumeración del bloque destructivo de C-09 a 22 y aclaración de cómo ver la línea de log del aviso de C-12 (uvicorn no muestra los loggers de la app en INFO con la configuración por defecto).
- **`test/auth.http`**: el bloque 8 (C-03) ahora dice explícitamente que hay que borrar la cookie antes de enviar el `Bearer`; si no, la petición responde 200 y no demuestra nada.
- **`test/repuestos.http`**: referencia al C-14 y a los dos archivos donde vive.
- **`test/MATRIZ_CASOS.md`** (nuevo): tabla de paridad de los 19 casos (qué verifica, `.http`/`.sql` con bloque, prueba pytest, estado), justificación de los casos que no son 100 % HTTP, orden de ejecución de la evidencia y checklist de los 8 criterios de evaluación con dónde se cumple y cómo se verificó.
- **Sin cambios de producción**: no se tocan `app/`, `main.py`, `seed.py`, `migrations/`, `test/conftest.py`, `pytest.ini`, la KB ni el roadmap. No hay endpoints, contratos, esquema ni dependencias nuevas.

## Capabilities

### New Capabilities

- `delivery-evidence`: la entrega tiene evidencia ejecutable y localizable para cada caso C-01 a C-19, una matriz que la enlaza con su prueba automatizada, y una verificación integral reproducible (suite, ciclo Alembic sobre base vacía, seed idempotente, secretos obligatorios y repo sin credenciales).

### Modified Capabilities

- `append-only-enforcement`: se agregan los requisitos de **evidencia** del caso C-14 —demostración en psql y réplica automatizada, rechazo del catálogo por clave foránea, filas intactas tras los intentos y el alcance real del disparador (`BEFORE UPDATE OR DELETE`, no `TRUNCATE`)— sin cambiar el comportamiento de la base.

## Impact

- **Código de producción**: ninguno. El change es verificación y documentación ejecutable.
- **Evidencia**: `test/solo_agregado.sql`, `test/test_solo_agregado.py`, `test/health.http` y `test/MATRIZ_CASOS.md` nuevos; bloques agregados en `test/auth.http`, `test/repuestos.http` y `test/ordenes.http`.
- **Suite**: pasa de **197** a **207** tests (10 nuevos de C-14).
- **Base de datos**: sin migraciones. La verificación usa una base descartable `taller_mecanico_verif` que se crea y se elimina; no se toca `taller_mecanico` ni `taller_mecanico_test`.
- **Dependencias**: ninguna nueva. `sqlalchemy.text` y `pytest` ya están en el stack.
- **Riesgo**: bajo. El único cambio de comportamiento posible es el de un test que se equivoque de transacción; se mitiga abriendo cada intento con `motor.begin()` y verificando las filas al final.
- **Habilitado**: el cierre del TP y el archivo de `C-13` por el orquestador.
