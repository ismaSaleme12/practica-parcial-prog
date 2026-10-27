# auth-registration Specification

## Purpose
Define el auto-registro abierto de un cliente: la creación atómica de usuario, rol CLIENTE y ficha de cliente, el conflicto con datos ya guardados sin apropiarse de una ficha existente y el límite de la contraseña medido en bytes.

## Requirements

### Requirement: El auto-registro crea las tres filas en un solo Unit of Work

`POST /auth/registro` SHALL crear, en una única transacción, la fila `usuario`, la fila `asignacion_rol` con `rol='CLIENTE'` y la fila `cliente` vinculada a ese usuario. Si una de las tres no se puede crear, MUST NOT quedar ninguna de las otras dos.

#### Scenario: Registro válido

- **WHEN** se envía un email, un nombre, una contraseña válida, un documento y un teléfono que no chocan con nada guardado
- **THEN** la respuesta es 201 con el usuario creado y la base tiene exactamente una fila `usuario`, una asignación abierta `CLIENTE` y una ficha `cliente` con el mismo `usuario_id`

#### Scenario: Falla una de las tres escrituras

- **WHEN** cualquiera de las tres inserciones viola una restricción de la base
- **THEN** el Unit of Work revierte la transacción completa y la respuesta es 409, sin usuario, sin rol y sin ficha nuevos

### Requirement: El registro no se apropia de una ficha existente

Cuando el documento ya pertenece a un cliente del taller, `POST /auth/registro` SHALL responder 409 y MUST NOT asignar el `usuario_id` nuevo a esa ficha ni reutilizarla.

#### Scenario: Documento de un cliente sin usuario

- **WHEN** se intenta registrar una cuenta con el documento de un cliente que existe en el taller y no tiene usuario
- **THEN** la respuesta es 409 y la ficha de ese cliente conserva `usuario_id` nulo

#### Scenario: Email repetido

- **WHEN** se intenta registrar una cuenta con un email que ya existe
- **THEN** la respuesta es 409 y no queda ninguna ficha de cliente suelta del intento

### Requirement: El rol del auto-registro es siempre CLIENTE

El contrato de registro SHALL NOT declarar `rol`: el servicio asigna `CLIENTE` y `extra="forbid"` rechaza cualquier intento de elegir otro rol o de enviar `password_hash`.

#### Scenario: Intento de elegir rol

- **WHEN** el cuerpo del registro incluye `rol`, `password_hash` o cualquier campo no declarado
- **THEN** la respuesta es 422 y no se crea ninguna fila

### Requirement: La contraseña del registro se limita en bytes

La contraseña del registro SHALL aceptar como máximo **72 bytes** en UTF-8, medidos sobre los bytes y no sobre los caracteres, y MUST rechazarse con 422 antes de cualquier llamada a bcrypt cuando los supere.

#### Scenario: Contraseña de 73 bytes

- **WHEN** se envía una contraseña de 73 bytes
- **THEN** la respuesta es 422 con un mensaje propio y no se calcula ningún hash

#### Scenario: Contraseña multibyte

- **WHEN** se envía una contraseña de 37 caracteres «ñ» (74 bytes)
- **THEN** la respuesta es 422: el límite es de bytes, no de caracteres

### Requirement: La respuesta del registro no expone el hash

La respuesta 201 SHALL declarar sólo los campos públicos del usuario y MUST NOT incluir `password_hash`, ni el hash completo, ni parcial, ni en un campo anidado.

#### Scenario: Alta exitosa

- **WHEN** el registro responde 201
- **THEN** el cuerpo trae id, email, nombre, `activo` y `debe_cambiar_password`, y no trae `password_hash` ni ningún valor que empiece con `$2b$`
