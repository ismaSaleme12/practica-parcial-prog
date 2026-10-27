# Spec Delta

## Purpose

Define la administración de personal y de roles: alta con clave provisoria, historial, asignación con vigencia validada, revocación que no borra y autoprotección del último administrador. El objetivo es que el historial de permisos sea auditable y que el sistema nunca se quede sin un ADMIN vigente por una operación aceptada.

## ADDED Requirements

### Requirement: El alta de personal usa una contraseña provisoria

`POST /usuarios` SHALL exigir ADMIN y responder 201 con el usuario creado, `debe_cambiar_password=true` y sin `password_hash`. El hash MUST calcularse antes de abrir la transacción. La respuesta MUST NOT incluir ningún hash.

#### Scenario: Alta válida

- **WHEN** un ADMIN envía email, nombre y contraseña válidos
- **THEN** la respuesta es 201 con `debe_cambiar_password: true` y sin `password_hash`

#### Scenario: Recepción intenta dar de alta personal

- **WHEN** un usuario con rol RECEPCION pide `POST /usuarios`
- **THEN** la respuesta es 403

#### Scenario: La clave provisoria bloquea el grupo protegido

- **WHEN** el usuario recién creado usa su clave provisoria para pedir `GET /repuestos`
- **THEN** la respuesta es 403 hasta que cambie la contraseña

### Requirement: El historial de roles no borra filas

`GET /usuarios/{id}/roles` SHALL exigir ADMIN y devolver todas las asignaciones del usuario, incluidas las revocadas y las vencidas, cada una con `rol`, `desde`, `vence_en`, `revocada_en` y `vigente`. MUST responder 404 si el usuario no existe.

#### Scenario: Usuario con un rol vigente

- **WHEN** un ADMIN consulta el historial de un usuario con MECANICO abierto
- **THEN** la respuesta es 200 con una fila `vigente: true` y `revocada_en: null`

#### Scenario: Usuario inexistente

- **WHEN** un ADMIN consulta el historial de un id que no existe
- **THEN** la respuesta es 404

### Requirement: La asignación valida la vigencia y choca con el índice parcial

`POST /usuarios/{id}/roles` SHALL exigir ADMIN y aceptar `rol` más `desde` y `vence_en` opcionales. Si `vence_en` o `desde` vienen sin zona horaria, o si `vence_en` no es futura, la respuesta MUST ser 422. Una asignación **vigente** repetida del mismo rol MUST responder 409 por el índice único parcial, sin consulta previa de unicidad. Si la fila abierta está **vencida**, la API MUST cerrarla escribiendo `revocada_en` y abrir una fila nueva. MUST responder 404 si el usuario no existe.

#### Scenario: Vencimiento sin zona horaria

- **WHEN** un ADMIN envía `vence_en: "2026-12-31T23:59:59"` sin offset
- **THEN** la respuesta es 422 con un mensaje que pide zona horaria

#### Scenario: Vencimiento en el pasado

- **WHEN** un ADMIN envía `vence_en` anterior al momento actual
- **THEN** la respuesta es 422 con un mensaje que pide una fecha futura

#### Scenario: Asignación vigente repetida

- **WHEN** un ADMIN asigna un rol que el usuario ya tiene vigente y abierto
- **THEN** la respuesta es 409 con el mensaje propio de conflicto, sin texto del motor ni nombre del índice

#### Scenario: Reasignación de un rol vencido

- **WHEN** un ADMIN asigna un rol cuya fila abierta ya venció
- **THEN** la respuesta es 201 y quedan dos filas: la vieja con `revocada_en` y la nueva abierta

#### Scenario: Rol desconocido

- **WHEN** un ADMIN envía un `rol` que no está entre ADMIN, RECEPCION, MECANICO y CLIENTE
- **THEN** la respuesta es 422

### Requirement: Revocar escribe revocada_en y nunca borra

`DELETE /usuarios/{id}/roles/{rol}` SHALL exigir ADMIN, escribir `revocada_en` en la asignación abierta y conservar la fila. MUST responder 404 si el usuario no existe o si no hay una asignación abierta con ese rol.

#### Scenario: Revocación válida

- **WHEN** un ADMIN revoca un rol abierto de otro usuario
- **THEN** la respuesta es 200 y la fila sigue en la tabla con `revocada_en` escrito

#### Scenario: Revocación repetida

- **WHEN** un ADMIN revoca otra vez un rol que ya fue revocado
- **THEN** la respuesta es 404 porque no hay una asignación abierta

#### Scenario: Rol nunca asignado

- **WHEN** un ADMIN revoca un rol que el usuario nunca tuvo
- **THEN** la respuesta es 404

### Requirement: Autoprotección del último administrador

La revocación de ADMIN SHALL responder 409 cuando el administrador intenta revocarse **su propio** rol ADMIN, y SHALL responder 409 cuando la operación dejaría el sistema con **0 ADMINs vigentes**. Las comprobaciones MUST ejecutarse antes de escribir `revocada_en`.

#### Scenario: ADMIN se revoca a sí mismo

- **WHEN** un ADMIN pide revocar su propio ADMIN
- **THEN** la respuesta es 409 y su asignación sigue abierta

#### Scenario: Revocar el ADMIN de otro con dos vigentes

- **WHEN** hay dos ADMINs vigentes y uno revoca el del otro
- **THEN** la respuesta es 200 y el afectado pierde el permiso en su petición siguiente

#### Scenario: Quedaría sin administradores

- **WHEN** la revocación dejaría 0 ADMINs vigentes
- **THEN** la respuesta es 409 y no se escribe ninguna revocación
