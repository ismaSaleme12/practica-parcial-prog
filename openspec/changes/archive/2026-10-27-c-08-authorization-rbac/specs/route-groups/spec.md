# Spec Delta

## Purpose

Define los dos grupos de rutas de la API y en qué orden se evalúan la identidad (401), el cambio obligatorio de contraseña (403) y el permiso por rol (403). El objetivo es que una ruta nueva del grupo protegido quede protegida por defecto y que el afectado por una clave provisoria no quede encerrado.

## ADDED Requirements

### Requirement: Dos grupos de rutas con el control del cambio obligatorio montado una sola vez

`main.py` SHALL montar dos grupos: uno **abierto** con `/health` y `/auth`, y uno **protegido** con `/usuarios`, `/eventos` y `/repuestos`. El control de `debe_cambiar_password` MUST montarse **una sola vez**, como dependencia del grupo protegido, y MUST NOT repetirse por ruta ni por router.

#### Scenario: Ruta del grupo protegido con clave provisoria

- **WHEN** un usuario con `debe_cambiar_password=true` pide cualquier ruta de `/usuarios`, `/eventos` o `/repuestos` con su cookie
- **THEN** la respuesta es 403 con el mensaje del cambio pendiente, sin llegar al handler ni evaluar el rol

#### Scenario: El grupo abierto sigue accesible con clave provisoria

- **WHEN** el mismo usuario pide `GET /auth/yo` o `POST /auth/cambiar-password`
- **THEN** la respuesta no es 403 por el cambio pendiente y la operación se ejecuta

#### Scenario: Salud no exige sesión

- **WHEN** se pide `GET /health/live` sin cookie
- **THEN** la respuesta es 200

### Requirement: El orden de las respuestas es 401, luego 403 del cambio, luego 403 del rol

La API SHALL responder 401 cuando no hay sesión válida, aunque la ruta también exija un rol o el cambio de contraseña. Cuando la sesión es válida, MUST evaluar primero `debe_cambiar_password` y después `requiere_rol`.

#### Scenario: Sin cookie en una ruta que además exige ADMIN

- **WHEN** se pide `GET /eventos` sin cookie
- **THEN** la respuesta es 401, no 403

#### Scenario: Con sesión de rol insuficiente

- **WHEN** se pide `GET /eventos` con la cookie de un usuario autenticado y activo que no tiene ADMIN vigente
- **THEN** la respuesta es 403 con el mensaje de permiso

#### Scenario: Sin cookie en una ruta del grupo abierto que exige sesión

- **WHEN** se pide `GET /auth/yo` sin cookie
- **THEN** la respuesta es 401

### Requirement: Una ruta nueva del grupo protegido hereda la protección

Toda ruta que se monte en el grupo protegido SHALL quedar sujeta al 401 de la sesión y al 403 del cambio obligatorio sin que la ruta declare esas dependencias. El grupo MUST NOT exponer una forma de quitar esas dependencias por ruta.

#### Scenario: Router agregado al grupo protegido

- **WHEN** un router se incluye en el grupo protegido y una de sus rutas no declara ninguna dependencia de sesión
- **THEN** esa ruta responde 401 sin cookie y 403 con clave provisoria
