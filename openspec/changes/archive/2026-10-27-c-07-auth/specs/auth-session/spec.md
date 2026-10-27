# Spec Delta

## Purpose

Define la sesión de la API: cómo se resuelve el usuario actual desde la cookie, cuándo la sesión es inválida (401), qué devuelve `/auth/yo`, cómo se cierra la sesión y por qué `Authorization: Bearer` no autentica.

## ADDED Requirements

### Requirement: La sesión se lee sólo de la cookie access_token

La dependencia del usuario actual SHALL leer el token únicamente de `request.cookies["access_token"]`. MUST NOT aceptar el token desde la cabecera `Authorization` ni desde el cuerpo de la petición.

#### Scenario: Token válido por Bearer

- **WHEN** se envía un JWT válido en `Authorization: Bearer` y no hay cookie
- **THEN** la respuesta es 401

#### Scenario: Token válido por cookie

- **WHEN** se envía el mismo JWT en la cookie `access_token`
- **THEN** la petición se resuelve con el usuario de la sesión

### Requirement: La sesión inválida responde 401

La API SHALL responder 401 cuando no hay cookie, el token es inválido o venció, el usuario no existe o está inactivo, o el `iat` del token es anterior a `password_cambiada_en`. La comparación de `iat` con `password_cambiada_en` MUST hacerse **sin truncar** a segundos.

#### Scenario: Token anterior al último cambio de contraseña

- **WHEN** un token se emitió antes de que el usuario cambiara su contraseña y se usa después del cambio
- **THEN** la respuesta es 401 aunque el token no haya vencido y aunque se haya emitido en el mismo segundo que el cambio

#### Scenario: Usuario inactivo

- **WHEN** el token es válido pero su usuario tiene `activo=false`
- **THEN** la respuesta es 401

### Requirement: /auth/yo devuelve usuario, roles vigentes y roles del token

`GET /auth/yo` SHALL responder 200 con el usuario, los roles **vigentes** consultados en la base en esa petición y los roles que trae el token. Los roles del token MUST presentarse como informativos.

#### Scenario: Sesión de un mecánico

- **WHEN** un usuario con rol MECANICO vigente pide `/auth/yo` con su cookie
- **THEN** la respuesta trae su usuario, `roles_vigentes: ["MECANICO"]` y `roles_token: ["MECANICO"]`

#### Scenario: Sin sesión

- **WHEN** se pide `/auth/yo` sin cookie o con un token inválido
- **THEN** la respuesta es 401

### Requirement: El logout borra la cookie

`POST /auth/logout` SHALL responder 200 y borrar la cookie `access_token` con `Max-Age=0`.

#### Scenario: Logout

- **WHEN** se llama a `/auth/logout` con o sin sesión
- **THEN** la respuesta es 200 y el `Set-Cookie` deja `access_token` vacía con `Max-Age=0`

#### Scenario: Petición posterior al logout

- **WHEN** el cliente ya no conserva la cookie y pide `/auth/yo`
- **THEN** la respuesta es 401

### Requirement: Ninguna respuesta de sesión expone el hash

`GET /auth/yo` y el resto de las respuestas de autenticación SHALL NOT incluir `password_hash` ni el hash en ningún campo.

#### Scenario: Identidad de la sesión

- **WHEN** `/auth/yo` responde 200
- **THEN** el objeto `usuario` trae sólo los campos públicos y no trae `password_hash`
