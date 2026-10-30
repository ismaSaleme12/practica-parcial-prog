# Spec Delta

## Purpose

Agregar los requisitos de **evidencia** del caso C-14 sobre el comportamiento de sólo agregado que ya existe: el rechazo de `UPDATE`/`DELETE` y la FK del catálogo se demuestran con un script ejecutable de psql y con una réplica automatizada en la suite, se fija el SQLSTATE como contrato (los mensajes del servidor están localizados), se comprueba que las filas quedan intactas y se documenta el alcance real del disparador (`BEFORE UPDATE OR DELETE`, no `TRUNCATE`). No cambia el comportamiento de la base ni la migración.

## ADDED Requirements

### Requirement: El caso C-14 se demuestra con un script ejecutable de psql

`test/solo_agregado.sql` SHALL ejecutarse con psql contra una base sembrada y MUST contener los seis intentos de modificación (tres tablas × `UPDATE`/`DELETE`), el `INSERT` del catálogo con un estado inexistente y los conteos finales que prueban que no se escribió nada. La cabecera MUST indicar el comando exacto, la salida esperada y que el proceso termina con código 0 aunque haya errores.

#### Scenario: El script llega al final pese a los rechazos

- **WHEN** se ejecuta `psql -U postgres -d taller_mecanico -f test/solo_agregado.sql` sobre una base sembrada
- **THEN** las seis modificaciones y el `INSERT` fallan, el script sigue tras cada error (`ON_ERROR_STOP off`) y el proceso termina con **código 0**

#### Scenario: Los conteos prueban que no se escribió nada

- **WHEN** el script termina
- **THEN** los conteos finales de `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` son los del seed (3 / 4 / 1) y el valor del historial de precios sigue siendo `8500.00`

### Requirement: El rechazo se identifica por SQLSTATE, no por el texto del mensaje

La evidencia y la réplica automatizada SHALL afirmar el SQLSTATE del rechazo (`23000` para el disparador, `23503` para la clave foránea) porque el servidor puede estar configurado con mensajes localizados. El texto MUST usarse sólo como comprobación complementaria y no como la única aserción.

#### Scenario: Disparador de sólo agregado

- **WHEN** un `UPDATE` o un `DELETE` sobre `historial_estado_orden`, `movimiento_stock` o `historial_precio_repuesto` es rechazado
- **THEN** el error tiene SQLSTATE `23000` y la fila conserva sus valores originales (`precio_nuevo = 8500.00`, `stock = 2`, orden `2` en `EN_REPARACION`)

#### Scenario: Clave foránea del catálogo

- **WHEN** se inserta una `orden_trabajo` con `estado = 'INVENTADO'`
- **THEN** el error tiene SQLSTATE `23503` y nombra la restricción `fk_orden_trabajo_estado`

### Requirement: El caso C-14 tiene una réplica automatizada en la suite

`test/test_solo_agregado.py` SHALL reproducir el caso con SQL crudo sobre el motor de la suite, sin psql y sin dependencias nuevas. Cada intento MUST correr en su propia transacción para que una transacción abortada no arrastre al siguiente, y la prueba MUST comprobar además que el `INSERT` sigue permitido.

#### Scenario: Un intento por transacción

- **WHEN** se ejecuta `python -m pytest test/test_solo_agregado.py -q`
- **THEN** los diez tests pasan y ninguno deja una transacción abortada para el siguiente

#### Scenario: Sólo agregado significa que agregar sigue permitido

- **WHEN** la réplica verifica el alcance del disparador
- **THEN** un `INSERT` nuevo en `movimiento_stock` es aceptado y un `TRUNCATE` no es rechazado por el disparador (dentro de una transacción que revierte, para no tocar los datos del seed)

### Requirement: El alcance real del disparador queda documentado

La evidencia SHALL decir que el disparador es `BEFORE UPDATE OR DELETE` y que **no** cubre `TRUNCATE`, y MUST explicar por qué eso permite que `seed.py` reinicie los datos sin desactivar la protección.

#### Scenario: Reinicio del seed

- **WHEN** se lee la evidencia de C-14 o la nota de la réplica
- **THEN** queda explícito que el seed puede vaciar y recargar las tablas de historial mediante `TRUNCATE` y que la protección sigue vigente para `UPDATE` y `DELETE` en la operación normal
