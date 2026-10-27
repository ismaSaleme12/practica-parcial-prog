# password-change Specification

## Purpose
Define el cambio de contraseña de la sesión: la verificación de la contraseña actual, la regla de longitud de la nueva, el registro de `password_cambiada_en` y la emisión de un token nuevo que invalida los anteriores.

## Requirements

### Requirement: El cambio exige la contraseña actual correcta

`POST /auth/cambiar-password` SHALL verificar la contraseña actual con bcrypt contra el hash guardado. Si no coincide, MUST responder 401 y MUST NOT modificar la contraseña ni emitir un token nuevo.

#### Scenario: Contraseña actual incorrecta

- **WHEN** el cuerpo trae una `password_actual` que no coincide con el hash del usuario
- **THEN** la respuesta es 401 y la contraseña guardada no cambia

#### Scenario: Sin sesión

- **WHEN** se llama a `/auth/cambiar-password` sin cookie o con un token inválido
- **THEN** la respuesta es 401

### Requirement: La contraseña nueva mide más de 8 bytes y hasta 72 bytes

La contraseña nueva SHALL ser válida sólo si mide **más de 8 bytes** y **como máximo 72 bytes** en UTF-8. Una contraseña de 8 bytes o menos MUST responder 422; una de más de 72 bytes MUST responder 422. El límite SHALL medirse en bytes y no en caracteres.

#### Scenario: Ocho bytes o menos

- **WHEN** la contraseña nueva mide exactamente 8 bytes (por ejemplo, 4 caracteres «ñ») o menos
- **THEN** la respuesta es 422 con un mensaje propio y no se modifica la contraseña

#### Scenario: Más de 72 bytes

- **WHEN** la contraseña nueva mide 73 bytes o más
- **THEN** la respuesta es 422 y nunca 500

#### Scenario: Nueve bytes

- **WHEN** la contraseña nueva mide 9 bytes
- **THEN** el contrato la acepta y el cambio puede completarse

### Requirement: El cambio anota la hora completa y limpia el cambio obligatorio

Un cambio exitoso SHALL guardar `password_cambiada_en` con la hora completa y zona horaria (fracciones de segundo incluidas) y SHALL dejar `debe_cambiar_password=false`.

#### Scenario: Cambio exitoso

- **WHEN** la contraseña actual es correcta y la nueva cumple el contrato
- **THEN** la respuesta es 200, la base guarda el hash nuevo, `password_cambiada_en` queda con hora completa y `debe_cambiar_password` queda en `false`

### Requirement: El token se emite después del cambio e invalida los anteriores

El servicio SHALL emitir el token nuevo **después** de anotar `password_cambiada_en`. A partir de ahí, el token nuevo MUST seguir valiendo y los tokens emitidos antes MUST responder 401, comparando `iat` con `password_cambiada_en` sin truncar, aunque compartan el segundo.

#### Scenario: Token anterior al cambio

- **WHEN** un token emitido antes del cambio se usa después, sin esperar a su vencimiento
- **THEN** la respuesta es 401

#### Scenario: Token emitido por el propio cambio

- **WHEN** se usa el token que devolvió la respuesta del cambio
- **THEN** la petición se resuelve correctamente y `debe_cambiar_password` aparece en `false`

### Requirement: La respuesta del cambio no expone el hash

La respuesta del cambio de contraseña SHALL NOT incluir `password_hash` ni el JWT en el cuerpo; el token viaja sólo en la cookie `access_token`.

#### Scenario: Cambio exitoso inspeccionado

- **WHEN** el cambio responde 200
- **THEN** el cuerpo trae `{mensaje, debe_cambiar_password, expira_en_segundos}` sin `access_token` ni `password_hash`, y el token nuevo está en la cookie
