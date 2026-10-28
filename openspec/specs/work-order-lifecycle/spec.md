# work-order-lifecycle Specification

## Purpose
Define el ciclo de vida de una orden de trabajo (US-024, US-026, RN-12, RN-13 y SU-04): iniciar, terminar y cancelar, con la asignación del mecánico, la identidad evaluada antes que el estado, el historial de sólo agregado y el aviso simulado al cliente después de confirmar. El objetivo es que ninguna transición inválida ni ningún usuario no autorizado pueda mover una orden, y que el aviso nunca se envíe por una operación que revirtió.

## Requirements

### Requirement: Iniciar asigna el mecánico de la sesión

`POST /ordenes/{id}/iniciar` SHALL exigir el rol MECANICO y SHALL permitir la transición únicamente desde `PENDIENTE`. La orden SHALL pasar a `EN_REPARACION`, `mecanico_id` SHALL quedar con el usuario de la sesión y SHALL agregarse una línea de historial `PENDIENTE → EN_REPARACION`. Cualquier otro estado de origen SHALL responder 409; un id inexistente, 404.

#### Scenario: Inicio válido

- **WHEN** un MECANICO inicia una orden PENDIENTE
- **THEN** la respuesta es 200 con estado `EN_REPARACION` y `mecanico_id` igual al usuario de la sesión, y el historial gana la línea `PENDIENTE → EN_REPARACION` (US-024)

#### Scenario: Orden ya iniciada

- **WHEN** se intenta iniciar una orden que ya está `EN_REPARACION`
- **THEN** la respuesta es 409 con el mensaje de transición inválida y el historial no cambia

#### Scenario: Rol sin permiso

- **WHEN** un usuario con rol RECEPCION, ADMIN o CLIENTE intenta iniciar
- **THEN** la respuesta es 403

### Requirement: Terminar exige ADMIN o el mecánico asignado, antes de mirar el estado

`POST /ordenes/{id}/terminar` SHALL aceptar la operación sólo para un ADMIN o para el mecánico asignado a la orden. La identidad SHALL evaluarse **antes** que el estado: un usuario que no sea ADMIN ni el asignado SHALL recibir 403 aunque la orden tampoco admita la transición. Sólo después SHALL verificarse que la orden esté `EN_REPARACION` (si no, 409). Un id inexistente SHALL responder 404 antes que cualquier permiso.

#### Scenario: Mecánico no asignado sobre una orden terminada

- **WHEN** un MECANICO distinto del asignado intenta terminar una orden ya `TERMINADA`
- **THEN** la respuesta es 403, no 409 (SU-04)

#### Scenario: Orden PENDIENTE

- **WHEN** el mecánico asignado (o un ADMIN) intenta terminar una orden `PENDIENTE`
- **THEN** la respuesta es 409 y no se escribe nada

#### Scenario: ADMIN no asignado

- **WHEN** un ADMIN termina una orden `EN_REPARACION` asignada a otro mecánico
- **THEN** la respuesta es 200 y el historial registra al ADMIN como usuario de la transición

#### Scenario: Orden inexistente

- **WHEN** se intenta terminar un id que no existe
- **THEN** la respuesta es 404

### Requirement: Cancelar admite al personal de atención o al dueño

`POST /ordenes/{id}/cancelar` SHALL aceptar la operación para ADMIN, RECEPCION o el cliente dueño del vehículo, y SHALL permitirla únicamente desde `PENDIENTE`. La ruta MUST NOT exigir un rol de taller: la decisión es del servicio. La identidad SHALL evaluarse antes que el estado: un cliente ajeno SHALL recibir 403 aunque la orden esté `TERMINADA`. Una orden no PENDIENTE de un usuario autorizado SHALL responder 409.

#### Scenario: El dueño cancela la propia

- **WHEN** el cliente dueño del vehículo cancela su orden PENDIENTE
- **THEN** la respuesta es 200 con estado `CANCELADA` y una línea de historial `PENDIENTE → CANCELADA` (caso C-13 / A-04)

#### Scenario: Cliente ajeno sobre una orden terminada

- **WHEN** un cliente intenta cancelar una orden `TERMINADA` de otro vehículo
- **THEN** la respuesta es 403, no 409 (SU-04)

#### Scenario: Orden ya cancelada

- **WHEN** un usuario autorizado intenta cancelar una orden `CANCELADA`
- **THEN** la respuesta es 409 y el historial no cambia

#### Scenario: Mecánico ajeno

- **WHEN** un MECANICO intenta cancelar una orden que no es suya
- **THEN** la respuesta es 403

### Requirement: El historial registra cada transición y es de sólo agregado

Cada transición efectiva SHALL insertar exactamente una línea en `historial_estado_orden` con `desde_estado`, `hasta_estado`, `usuario_id` y `cuando` con zona horaria, en la misma transacción que el cambio de estado. La API MUST NOT exponer ninguna operación de modificación ni borrado del historial (RN-15).

#### Scenario: Una línea por transición

- **WHEN** una orden pasa de PENDIENTE a EN_REPARACION y luego a TERMINADA
- **THEN** su historial tiene tres líneas: `null → PENDIENTE`, `PENDIENTE → EN_REPARACION` y `EN_REPARACION → TERMINADA`

#### Scenario: Transición rechazada

- **WHEN** una transición responde 403 o 409
- **THEN** no se agrega ninguna línea al historial

### Requirement: El aviso al cliente se agenda después de confirmar

`POST /ordenes/{id}/terminar` SHALL agendar un aviso simulado sólo cuando la terminación fue exitosa y la transacción ya se confirmó. El aviso MUST NOT ejecutarse dentro del Unit of Work ni agendarse con 403, 404 o 409. La tarea MUST poder observar el estado confirmado desde una sesión de base nueva.

#### Scenario: Terminación exitosa

- **WHEN** una orden se termina correctamente
- **THEN** la respuesta es 200 y, después del commit, se registra el aviso simulado para esa orden (caso C-12 / A-03)

#### Scenario: El aviso observa el estado confirmado (caso C-12)

- **WHEN** el aviso abre una sesión nueva desde `app.state.session_maker` y lee el estado de la orden
- **THEN** ve `TERMINADA`; si la tarea corriera dentro del Unit of Work, el aislamiento de PostgreSQL (READ COMMITTED) le mostraría `EN_REPARACION`

#### Scenario: Terminación rechazada

- **WHEN** `terminar` responde 403 por identidad o 409 por estado o stock
- **THEN** no se agenda ningún aviso
