-- =====================================================================
-- Caso C-14 — Sólo agregado verificado en psql (RN-15 / RN-19, Flujo 13)
-- =====================================================================
--
-- Qué demuestra este script
-- ------------------------
-- 1. UPDATE y DELETE sobre las TRES tablas de auditoría
--    (`historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto`)
--    los rechaza el disparador de la migración `0002_solo_agregado.py`.
--    Son seis intentos: uno de UPDATE y uno de DELETE por tabla.
-- 2. Un INSERT de `orden_trabajo` con un `estado` que NO está en el catálogo
--    `estado_orden` lo rechaza la clave foránea `fk_orden_trabajo_estado`.
-- 3. Al final, las filas siguen exactamente como las dejó el seed: los errores
--    no escriben nada (cada sentencia falla y PostgreSQL revierte su propia
--    transacción implícita).
--
-- Cómo ejecutarlo
-- ---------------
--   Requisitos: base migrada (`alembic upgrade head`) y sembrada (`python seed.py`).
--
--   psql -U postgres -d taller_mecanico -f test/solo_agregado.sql
--
--   En PowerShell (psql no está en el PATH de este equipo):
--
--   $env:PGPASSWORD="postgres"
--   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost `
--       -d taller_mecanico -f test/solo_agregado.sql
--
--   `psql` sigue después de un error (ON_ERROR_STOP está en `off` por defecto;
--   se fija explícito abajo para que no dependa de psqlrc). Cada error imprime
--   `ERROR:` y el script continúa con el bloque siguiente; por eso el proceso
--   termina con **código 0** aunque haya siete errores: los errores son el
--   resultado buscado. En PowerShell los `ERROR:` salen por stderr y pueden
--   aparecer al final de la salida; el orden de los `\echo` es el del script.
--
-- Salida esperada (resumen)
-- -------------------------
--   UPDATE historial_estado_orden      → ERROR: La tabla historial_estado_orden
--                                        es de sólo agregado: UPDATE no está permitido
--   DELETE historial_estado_orden      → ERROR: ... : DELETE no está permitido
--   UPDATE movimiento_stock            → ERROR: La tabla movimiento_stock es de
--                                        sólo agregado: UPDATE no está permitido
--   DELETE movimiento_stock            → ERROR: ... : DELETE no está permitido
--   UPDATE historial_precio_repuesto   → ERROR: La tabla historial_precio_repuesto
--                                        es de sólo agregado: UPDATE no está permitido
--   DELETE historial_precio_repuesto   → ERROR: ... : DELETE no está permitido
--   INSERT con estado 'INVENTADO'      → ERROR: inserción o actualización en la
--                                        tabla «orden_trabajo» viola la llave
--                                        foránea «fk_orden_trabajo_estado»
--                                        DETALLE: La llave (estado)=(INVENTADO)
--                                        no está presente en la tabla
--                                        «estado_orden». (En inglés: DETAIL.)
--
--   (Los mensajes del servidor están localizados por `lc_messages`; el código
--   de error es el contrato: 23000 para el disparador, 23503 para la FK.)
--
-- Nota sobre TRUNCATE
-- -------------------
--   El disparador es `BEFORE UPDATE OR DELETE` y **no** cubre `TRUNCATE`. Por
--   eso `seed.py` puede reiniciar la base con
--   `TRUNCATE ... RESTART IDENTITY CASCADE`: el vaciado de puesta en marcha no
--   se bloquea, pero corregir o borrar una fila de auditoría, sí. La réplica
--   automatizada de esta nota está en
--   `test/test_solo_agregado.py::test_truncate_no_dispara_el_disparador_y_el_seed_puede_reiniciar`.
--
-- Réplica automatizada (sin psql)
-- -------------------------------
--   python -m pytest test/test_solo_agregado.py -q
--   Cubre los seis rechazos, el de la FK y la integridad de las filas.
-- =====================================================================

\set ON_ERROR_STOP off

\echo ''
\echo '=== C-14: las tres tablas de auditoría son de sólo agregado ==='
\echo ''

\echo '--- 1/6 UPDATE historial_estado_orden (esperado: ERROR 23000) ---'
UPDATE historial_estado_orden SET usuario_id = usuario_id;

\echo '--- 2/6 DELETE historial_estado_orden (esperado: ERROR 23000) ---'
DELETE FROM historial_estado_orden;

\echo '--- 3/6 UPDATE movimiento_stock (esperado: ERROR 23000) ---'
UPDATE movimiento_stock SET motivo = motivo;

\echo '--- 4/6 DELETE movimiento_stock (esperado: ERROR 23000) ---'
DELETE FROM movimiento_stock;

\echo '--- 5/6 UPDATE historial_precio_repuesto (esperado: ERROR 23000) ---'
UPDATE historial_precio_repuesto SET precio_nuevo = precio_nuevo;

\echo '--- 6/6 DELETE historial_precio_repuesto (esperado: ERROR 23000) ---'
DELETE FROM historial_precio_repuesto;

\echo ''
\echo '=== C-14: el estado de una orden lo impone el catálogo (RN-19) ==='
\echo ''

\echo '--- INSERT orden_trabajo con estado INVENTADO (esperado: ERROR 23503) ---'
INSERT INTO orden_trabajo (vehiculo_id, estado, falla, total)
VALUES (
    (SELECT id FROM vehiculo ORDER BY id LIMIT 1),
    'INVENTADO',
    'Estado fuera del catálogo',
    0
);

\echo ''
\echo '=== Integridad: las filas siguen como las dejó el seed ==='
\echo ''

-- Los conteos del seed son 3 / 4 / 1 (historial de estados, movimientos de
-- stock e historial de precios del filtro).
SELECT 'historial_estado_orden' AS tabla, count(*) AS filas
  FROM historial_estado_orden
UNION ALL
SELECT 'movimiento_stock', count(*) FROM movimiento_stock
UNION ALL
SELECT 'historial_precio_repuesto', count(*) FROM historial_precio_repuesto
ORDER BY tabla;

-- Además de los conteos, un valor concreto de cada tabla: si un UPDATE hubiera
-- pasado, el precio del filtro o el motivo del movimiento habrían cambiado.
SELECT id, repuesto_id, precio_anterior, precio_nuevo
  FROM historial_precio_repuesto
 ORDER BY id;

SELECT id, repuesto_id, cantidad, motivo
  FROM movimiento_stock
 ORDER BY id;

-- Esperado en los conteos: 3, 4 y 1. En el historial de precios: la línea del
-- seed 8000.00 → 8500.00. En los movimientos: los cuatro «Stock inicial» del
-- seed (10, 4, 2 y 20). Ninguna fila con el valor que intentaron escribir los
-- UPDATE de arriba.
