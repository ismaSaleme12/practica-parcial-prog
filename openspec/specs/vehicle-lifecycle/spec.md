# vehicle-lifecycle Specification

## Purpose
Define el ciclo de vida del vehículo: alta con año validado y patente única entre los vigentes, baja lógica que libera la patente para otro comprador y bloqueo de la baja mientras el vehículo tenga órdenes abiertas. El objetivo es que el historial de órdenes no se pierda y que la patente se pueda reutilizar sin duplicar vehículos vigentes.

## Requirements

### Requirement: El alta de vehículo valida el año y exige el cliente de la ruta

`POST /clientes/{id}/vehiculos` SHALL exigir ADMIN o RECEPCION, tomar el `cliente_id` de la URL (nunca del cuerpo) y responder 201 con el vehículo creado. `anio` MUST estar entre 1950 y 2100; fuera de rango MUST responder 422. Si el cliente de la ruta no existe MUST responder 404 sin dejar filas escritas. Los campos no declarados MUST responder 422. Sin sesión MUST responder 401; con CLIENTE o MECANICO MUST responder 403.

#### Scenario: Alta válida

- **WHEN** una sesión ADMIN o RECEPCION envía patente, marca, modelo y un año dentro del rango a un cliente existente
- **THEN** la respuesta es 201 con `cliente_id` igual al de la ruta

#### Scenario: Año fuera de rango

- **WHEN** el año es 1949 o 2101
- **THEN** la respuesta es 422 con el detalle del contrato y no se escribe ninguna fila

#### Scenario: Cliente inexistente

- **WHEN** la URL apunta a un cliente que no existe
- **THEN** la respuesta es 404 y no se escribe ningún vehículo

#### Scenario: Campo no declarado

- **WHEN** el cuerpo incluye `borrado_en` o cualquier campo que el contrato no declara
- **THEN** la respuesta es 422

### Requirement: La patente es única entre los vehículos vigentes

`vehiculo.patente` SHALL ser única **entre los vigentes**, garantizado por el índice único parcial `WHERE borrado_en IS NULL`, sin una consulta previa de la API. Una patente vigente repetida MUST responder 409 con el mensaje propio de conflicto. Una patente cuya fila anterior está dada de baja MUST poder registrarse de nuevo con 201 (caso C-19).

#### Scenario: Patente vigente repetida

- **WHEN** se intenta dar de alta un vehículo con una patente que ya tiene una fila vigente
- **THEN** la respuesta es 409 con `{"detail": "La operación entra en conflicto con datos ya guardados."}`

#### Scenario: Patente repetida después de la baja

- **WHEN** la patente pertenece a un vehículo que ya tiene `borrado_en` escrito y se da de alta de nuevo
- **THEN** la respuesta es 201 y conviven la fila histórica y la nueva vigente

#### Scenario: Segunda patente vigente igual

- **WHEN** después del alta anterior se intenta registrar otra vez la misma patente vigente
- **THEN** la respuesta es 409

### Requirement: La baja del vehículo es lógica

`DELETE /vehiculos/{id}` SHALL exigir ADMIN o RECEPCION y responder 204 sin cuerpo. La baja MUST escribir `borrado_en` y conservar la fila y sus órdenes. Después de la baja el vehículo MUST dejar de aparecer en la ficha del cliente. Un id inexistente o ya dado de baja MUST responder 404.

#### Scenario: Baja válida

- **WHEN** un ADMIN o RECEPCION da de baja un vehículo sin órdenes abiertas
- **THEN** la respuesta es 204, la fila sigue existiendo y `borrado_en` queda escrito

#### Scenario: Vehículo ya dado de baja

- **WHEN** se repite la baja del mismo vehículo
- **THEN** la respuesta es 404

#### Scenario: Vehículo inexistente

- **WHEN** se da de baja un id que no existe
- **THEN** la respuesta es 404

#### Scenario: Rol insuficiente

- **WHEN** una sesión con rol CLIENTE o MECANICO pide la baja
- **THEN** la respuesta es 403 y el vehículo sigue vigente

### Requirement: Un vehículo con órdenes abiertas no se da de baja

La baja SHALL responder 409 con un mensaje propio cuando el vehículo tenga al menos una orden en un estado que el catálogo `estado_orden` marca con `es_final = false`. La comprobación MUST ejecutarse antes de escribir `borrado_en`, y un vehículo sin órdenes o con todas sus órdenes en estados finales MUST poder darse de baja.

#### Scenario: Orden pendiente

- **WHEN** el vehículo tiene una orden PENDIENTE (no final)
- **THEN** la respuesta es 409 y `borrado_en` sigue nulo

#### Scenario: Orden en reparación

- **WHEN** el vehículo tiene una orden EN_REPARACION (no final)
- **THEN** la respuesta es 409 y `borrado_en` sigue nulo

#### Scenario: Sin órdenes abiertas

- **WHEN** el vehículo no tiene órdenes, o todas están TERMINADA o CANCELADA
- **THEN** la respuesta es 204 y la baja se escribe
