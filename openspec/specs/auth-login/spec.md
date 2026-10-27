# auth-login Specification

## Purpose
Define el login abierto: el orden de sus pasos, el límite de intentos con `Retry-After`, la respuesta uniforme con hash ficticio, la anotación del intento en su propia transacción y la entrega del JWT sólo en la cookie HttpOnly.

## Requirements

### Requirement: El límite de intentos se evalúa antes de calcular cualquier hash

El login SHALL contar los fallos con el mismo `(email, ip)` en los últimos 60 segundos **antes** de verificar la contraseña. Cuando haya 5 o más, MUST responder 429 con la cabecera `Retry-After` y MUST NOT calcular ni verificar ningún hash.

#### Scenario: Quinto fallo y sexto intento

- **WHEN** se acumulan 5 intentos fallidos con el mismo email desde la misma IP en menos de 60 s y llega un sexto intento
- **THEN** la respuesta es 429 con `Retry-After` y el servicio no ejecuta bcrypt

#### Scenario: Por debajo del límite

- **WHEN** hay menos de 5 fallos vigentes con ese `(email, ip)`
- **THEN** el login continúa con la verificación de la contraseña

### Requirement: La respuesta no revela si el correo existe

El login SHALL responder con el mismo código y el mismo cuerpo exista o no el correo. Cuando el correo no existe, MUST verificar la contraseña contra el **hash ficticio** calculado una vez en el lifespan, para que la duración sea parecida.

#### Scenario: Correo inexistente

- **WHEN** se intenta iniciar sesión con un correo que no está en la base
- **THEN** la respuesta es 401 con el mismo cuerpo que una contraseña incorrecta y la verificación se hizo contra el hash ficticio

#### Scenario: Contraseña incorrecta

- **WHEN** el correo existe y la contraseña no coincide
- **THEN** la respuesta es 401 con ese mismo cuerpo, sin indicar cuál de los dos datos falló

### Requirement: El intento se anota en su propia transacción, siempre confirmada

Cada intento de login que llega a la verificación SHALL anotarse en `intento_acceso` en una sesión y una transacción propias, confirmadas siempre, con independencia del resultado de la petición. Esa escritura MUST NOT compartir la transacción de la petición.

#### Scenario: Login fallido

- **WHEN** el login responde 401 por credenciales inválidas
- **THEN** queda una fila en `intento_acceso` con `exito=false`, aunque la transacción de la petición se haya revertido

#### Scenario: Login correcto

- **WHEN** el login responde 200
- **THEN** queda una fila en `intento_acceso` con `exito=true`

### Requirement: Un login correcto reinicia la cuenta de fallos

Un login correcto SHALL hacer que los fallos anteriores de ese `(email, ip)` dejen de contar para el límite, sin borrarlos de la tabla.

#### Scenario: Fallos antes de un login correcto

- **WHEN** hay fallos viejos, luego un login correcto y después nuevos fallos
- **THEN** el límite sólo cuenta los fallos posteriores al login correcto

### Requirement: El JWT viaja sólo en la cookie HttpOnly

El login correcto SHALL emitir un JWT con `sub`, `iat` sin truncar, `exp` y los roles vigentes al emitirlo, y MUST entregarlo únicamente en la cookie `access_token` con `HttpOnly`, `SameSite=Lax`, `Max-Age` igual a la duración del token y `Secure` según la configuración. El cuerpo MUST NOT incluir el token.

#### Scenario: Login correcto

- **WHEN** las credenciales son válidas
- **THEN** la respuesta es 200 con `{mensaje, debe_cambiar_password, expira_en_segundos}` y un `Set-Cookie` de `access_token` con los atributos indicados

#### Scenario: Intento de leer el token del cuerpo

- **WHEN** el cliente inspecciona el cuerpo del login
- **THEN** no encuentra `access_token` ni el JWT: el token sólo está en la cookie

### Requirement: La contraseña del login se limita en bytes

La contraseña del login SHALL aceptar como máximo 72 bytes en UTF-8 y MUST rechazarse con 422 cuando los supere, antes de llegar a bcrypt.

#### Scenario: Contraseña de más de 72 bytes

- **WHEN** el cuerpo del login trae una contraseña de 73 bytes
- **THEN** la respuesta es 422 y no se ejecuta la verificación
