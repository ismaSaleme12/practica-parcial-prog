# security-events Specification

## Purpose
Define qué operaciones dejan un evento en `evento_seguridad`, con qué actor y acción, y cómo se consulta el historial. El objetivo es que las altas, los cambios de rol y los cambios de contraseña sean auditables y que sólo un ADMIN pueda leerlos, en el envoltorio de paginación uniforme.

## Requirements

### Requirement: Las operaciones sensibles dejan un evento en el mismo Unit of Work

El alta de personal, la asignación de rol, la revocación de rol y el cambio de contraseña SHALL escribir un `evento_seguridad` **dentro** de la transacción de la operación. Si la operación falla, el evento MUST NOT quedar; si la operación se confirma, el evento MUST quedar.

#### Scenario: Alta de personal

- **WHEN** un ADMIN crea un usuario que se confirma
- **THEN** queda un evento con el correo del ADMIN como actor y la acción del alta con el id creado

#### Scenario: Operación rechazada

- **WHEN** una asignación responde 409 por el índice parcial
- **THEN** no queda ningún evento de asignación

#### Scenario: Cambio de contraseña

- **WHEN** un usuario cambia su contraseña correctamente
- **THEN** queda un evento con su correo como actor y la acción del cambio de contraseña

### Requirement: El actor es un texto legible y acotado

El campo `actor` SHALL ser el correo del usuario que ejecuta la operación, recortado a 120 caracteres, o `'SISTEMA'` para los eventos de carga inicial. MUST NOT provocar un error de datos por un correo más largo que la columna.

#### Scenario: Correo de más de 120 caracteres

- **WHEN** el usuario que ejecuta la operación tiene un correo de más de 120 caracteres
- **THEN** el evento se guarda con el correo recortado y la operación responde su código normal, sin 500

#### Scenario: Evento del seed

- **WHEN** se consulta el historial tras `seed.py`
- **THEN** el primer evento tiene `actor: "SISTEMA"`

### Requirement: Las acciones se identifican por un texto estable

Cada evento SHALL registrar una acción con un texto fijo que incluya el rol y el id del usuario afectado cuando corresponda, de forma que el historial se pueda filtrar por acción.

#### Scenario: Asignación y revocación

- **WHEN** un ADMIN asigna y luego revoca MECANICO al usuario 3
- **THEN** quedan dos eventos de ese ADMIN, en ese orden: la asignación de MECANICO al usuario 3 y la revocación de MECANICO al usuario 3

### Requirement: El historial de eventos es paginado y sólo ADMIN

`GET /eventos` SHALL exigir ADMIN y responder 200 con el envoltorio `{items, total, page, size, pages}`, ordenado para que el primer elemento sea el evento más antiguo. Con un rol insuficiente MUST responder 403; sin sesión, 401.

#### Scenario: Consulta de un ADMIN

- **WHEN** un ADMIN pide `GET /eventos?page=1&size=1`
- **THEN** la respuesta es 200 con `size: 1`, `total` mayor o igual a 1 y claves exactamente `items`, `total`, `page`, `size` y `pages`

#### Scenario: Consulta de un mecánico

- **WHEN** un usuario con rol MECANICO pide `GET /eventos`
- **THEN** la respuesta es 403

#### Scenario: Página fuera de rango con rol insuficiente

- **WHEN** un usuario sin ADMIN pide `GET /eventos?page=99`
- **THEN** la respuesta es 403, porque el permiso se decide antes que la paginación

### Requirement: Ninguna respuesta de auditoría expone datos de credenciales

Las respuestas de `/eventos` y de las rutas de administración SHALL NOT incluir `password_hash`, el hash ni el token.

#### Scenario: Historial de eventos

- **WHEN** `GET /eventos` responde 200
- **THEN** ningún elemento trae `password_hash` ni un valor que empiece con `$2b$`
