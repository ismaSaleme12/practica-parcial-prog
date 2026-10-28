# Spec Delta

## Purpose

Actualizar el requisito del aviso al cliente para que la condición «después de confirmar» sea comprobable por **aislamiento de transacción** y no sólo por la existencia de una línea de log: una sesión nueva abierta desde la tarea de fondo debe ver el estado ya confirmado.

## MODIFIED Requirements

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
