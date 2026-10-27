# stock-ledger Specification

## Purpose
Define el punto único de escritura del stock (RN-14): el alta con `stock_inicial` y la reposición, cada una con su `movimiento_stock` en el mismo Unit of Work, y la consulta paginada de los movimientos de un repuesto. El objetivo es que todo cambio de stock tenga una fila que lo explique y que no exista ninguna ruta que escriba el stock sin dejar movimiento.

## Requirements

### Requirement: El stock sólo cambia por movimientos

El `stock` de un repuesto SHALL cambiar únicamente por `movimiento_stock`: el alta con `stock_inicial` y la reposición. No MUST existir ninguna ruta que acepte `stock` en el cuerpo de una alta o de una edición.

#### Scenario: PATCH intenta escribir el stock

- **WHEN** se envía `stock` en `PATCH /repuestos/{id}`
- **THEN** la respuesta es 422 y el stock guardado queda igual (caso C-16)

#### Scenario: Reposición

- **WHEN** se pide `POST /repuestos/{id}/reponer` con `cantidad: 5` sobre un stock de 2
- **THEN** la respuesta es 200 con `stock: 7`

### Requirement: Cada escritura de stock deja su movimiento en el mismo UoW

El alta con `stock_inicial > 0` SHALL insertar un `movimiento_stock` con `cantidad` igual al stock inicial, motivo `"Stock inicial"` y el usuario de la sesión. La reposición SHALL insertar un movimiento con `cantidad` positiva y motivo `"Reposición"`. Las dos escrituras MUST confirmarse o revertirse junto con el repuesto.

#### Scenario: Alta con stock inicial

- **WHEN** se crea un repuesto con `stock_inicial: 7`
- **THEN** su historial de movimientos tiene una fila con `cantidad: 7`, motivo `"Stock inicial"`, `usuario_id` de la sesión y `orden_id: null`

#### Scenario: Reposición

- **WHEN** se repone un repuesto con `cantidad: 5`
- **THEN** su historial tiene una fila nueva con `cantidad: 5`, motivo `"Reposición"` y el usuario de la sesión

#### Scenario: Alta sin stock inicial

- **WHEN** se omite `stock_inicial` o se envía 0
- **THEN** el repuesto nace con stock 0 y no se escribe ningún movimiento

### Requirement: La reposición exige una cantidad positiva

`POST /repuestos/{id}/reponer` SHALL aceptar únicamente un cuerpo `{cantidad: int}` con `cantidad > 0` y SHALL responder 404 si el repuesto no existe o está dado de baja.

#### Scenario: Cantidad cero o negativa

- **WHEN** se envía `cantidad: 0` o `cantidad: -2`
- **THEN** la respuesta es 422 y no se escribe ningún movimiento

#### Scenario: Repuesto inexistente

- **WHEN** se repone un id que no existe
- **THEN** la respuesta es 404 con un mensaje propio

### Requirement: Los movimientos se consultan paginados y ordenados

`GET /repuestos/{id}/movimientos` SHALL responder el envoltorio `{items, total, page, size, pages}` con los movimientos del repuesto ordenados por `cuando` e `id`, y SHALL responder 404 si el repuesto no existe o está dado de baja.

#### Scenario: Orden determinista

- **WHEN** un repuesto tiene tres movimientos y se piden dos páginas de tamaño 1
- **THEN** las dos páginas traen filas distintas, en orden de `cuando` e `id`

#### Scenario: Repuesto inexistente

- **WHEN** se piden los movimientos de un id que no existe
- **THEN** la respuesta es 404, no una página vacía

### Requirement: Las filas de movimiento no se modifican ni se borran

La API MUST NOT exponer ninguna operación de UPDATE o DELETE sobre `movimiento_stock`; esas filas son de sólo agregado (RN-15) y el disparador de la base rechaza cualquier intento.

#### Scenario: La API no edita movimientos

- **WHEN** se revisan las rutas del módulo
- **THEN** ninguna acepta modificar ni borrar un movimiento; sólo el alta y la reposición agregan filas

#### Scenario: El disparador protege la tabla

- **WHEN** se intenta `UPDATE` o `DELETE` sobre `movimiento_stock` desde psql
- **THEN** la base lo rechaza con el disparador de `C-04` (caso C-14)
