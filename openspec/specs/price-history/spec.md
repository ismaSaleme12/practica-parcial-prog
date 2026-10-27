# price-history Specification

## Purpose
Define el historial de precios del catálogo (RN-20): cada cambio efectivo de precio deja **una** línea con el anterior, el nuevo, el usuario y el instante, en la misma transacción que el cambio; un PATCH que no cambia el precio no deja ninguna. El objetivo es que el precio de un repuesto tenga la misma trazabilidad que el stock y que el historial no se ensucie con operaciones que no cambiaron nada.

## Requirements

### Requirement: Un cambio efectivo de precio deja exactamente una línea

`PATCH /repuestos/{id}` SHALL insertar una fila en `historial_precio_repuesto` cuando el precio enviado difiera del actual, con `precio_anterior`, `precio_nuevo`, `usuario_id` de la sesión y `cuando` con zona horaria. La fila MUST insertarse en el mismo Unit of Work que el cambio del repuesto.

#### Scenario: Cambio de precio

- **WHEN** un repuesto de `"8500.00"` recibe `precio: "9000.00"`
- **THEN** la respuesta es 200 y el historial gana una línea con `precio_anterior: "8500.00"` y `precio_nuevo: "9000.00"` (caso B-02)

#### Scenario: Dos cambios consecutivos

- **WHEN** el precio cambia dos veces seguidas
- **THEN** el historial gana exactamente dos líneas, encadenadas por el anterior y el nuevo

#### Scenario: Descripción y precio en el mismo PATCH

- **WHEN** un PATCH envía descripción y precio nuevos
- **THEN** la respuesta es 200 con los dos campos actualizados y una sola línea de historial

### Requirement: Un PATCH sin cambio efectivo no deja línea

Si el precio enviado es idéntico al actual, o si el cuerpo no trae `precio`, `PATCH /repuestos/{id}` SHALL responder 200 y MUST NOT insertar ninguna fila en el historial (RN-20). La operación no SHALL fallar por el CHECK `precio_nuevo <> precio_anterior`.

#### Scenario: Mismo precio

- **WHEN** se envía `precio` igual al actual
- **THEN** la respuesta es 200 y el total del historial no cambia (caso B-03)

#### Scenario: Sólo descripción

- **WHEN** el cuerpo trae únicamente `descripcion`
- **THEN** la respuesta es 200 y el total del historial no cambia

#### Scenario: El CHECK de la base no se dispara

- **WHEN** se envía el mismo precio dos veces
- **THEN** la segunda respuesta es 200, no un 409 de integridad

### Requirement: El historial se consulta paginado y con el dinero como string

`GET /repuestos/{id}/precios` SHALL responder el envoltorio `{items, total, page, size, pages}` ordenado por `cuando` e `id`, con `precio_anterior` y `precio_nuevo` como string Decimal, y SHALL responder 404 si el repuesto no existe o está dado de baja.

#### Scenario: Historial del seed más los cambios

- **WHEN** `FA-001` tiene la línea del seed y recibe dos cambios
- **THEN** `GET /repuestos/1/precios` devuelve `total: 3` en orden cronológico

#### Scenario: Repuesto inexistente

- **WHEN** se piden los precios de un id que no existe
- **THEN** la respuesta es 404, no una página vacía

#### Scenario: Página fuera de rango

- **WHEN** se pide una página posterior a la última del historial
- **THEN** la respuesta es 422 con el mensaje de paginación propio

### Requirement: El historial es de sólo agregado y sólo lo consulta ADMIN

La API MUST NOT exponer ninguna operación de UPDATE o DELETE sobre `historial_precio_repuesto` (RN-15) y `GET /repuestos/{id}/precios` MUST exigir ADMIN.

#### Scenario: Recepción pide el historial

- **WHEN** un usuario con RECEPCION pide `GET /repuestos/1/precios`
- **THEN** la respuesta es 403

#### Scenario: El disparador protege la tabla

- **WHEN** se intenta `UPDATE` o `DELETE` sobre `historial_precio_repuesto` desde psql
- **THEN** la base lo rechaza con el disparador de `C-04` (caso C-14)
