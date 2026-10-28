# Spec Delta

## Purpose

Actualizar el requisito del detalle de la orden para que el número fijo de consultas sea un **criterio medible** y no sólo una intención de diseño: el detalle de 2 y de 4 ítems debe producir el mismo conteo (caso C-15).

## MODIFIED Requirements

### Requirement: El detalle se arma con un número fijo de consultas

`GET /ordenes/{id}` SHALL responder la orden con su vehículo, el cliente, los ítems con código, descripción, precio y `subtotal`, y el historial cronológico. El repositorio MUST precargar esas relaciones en tres consultas fijas y MUST NOT usar carga perezosa. La petición completa MUST mantenerse en cinco consultas con 2 y con 4 ítems.

#### Scenario: Detalle completo

- **WHEN** se consulta una orden con dos ítems y dos líneas de historial
- **THEN** la respuesta es 200 con `cliente`, `items` (cada uno con `codigo`, `descripcion`, `precio_unitario` y `subtotal` como string) e `historial` ordenado por `cuando` e `id`

#### Scenario: El conteo no crece con los ítems (caso C-15)

- **WHEN** se mide el detalle de una orden con 2 ítems y el de otra con 4 ítems del mismo vehículo, con la misma sesión y un contador `before_cursor_execute` sobre `engine.sync_engine`
- **THEN** el conteo es el mismo en ambos casos (5 consultas), la sentencia sobre `item_orden` aparece una sola vez y la sentencia sobre `historial_estado_orden` también

#### Scenario: Orden inexistente

- **WHEN** se consulta un id que no existe
- **THEN** la respuesta es 404 con un mensaje propio y no una respuesta vacía
