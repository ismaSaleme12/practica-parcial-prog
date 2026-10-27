# request-contracts Specification

## Purpose
Define los contratos de entrada y salida de la API: qué campos acepta cada cuerpo, cómo rechaza lo que no declara, cómo viaja el dinero, cuánto puede medir una contraseña y cómo se aplica un PATCH.

## Requirements

### Requirement: Los contratos de entrada rechazan los campos no declarados

Todo contrato de entrada SHALL declarar `extra="forbid"`: un cuerpo con un campo que el contrato no declara MUST responder 422 y MUST NOT crear ni modificar nada.

#### Scenario: Campo no declarado en el alta de un repuesto

- **WHEN** se envía `POST /repuestos` con `codigo`, `descripcion`, `precio` y además `stock`
- **THEN** la respuesta es 422 con un mensaje propio y el repuesto no se crea

#### Scenario: Campo no declarado en el alta de un usuario

- **WHEN** se envía `POST /usuarios` con `rol`, `password_hash` o cualquier otro campo que el contrato no declare
- **THEN** la respuesta es 422 con un mensaje propio y el usuario no se crea

#### Scenario: Cuerpo válido

- **WHEN** se envía un cuerpo con exactamente los campos declarados y valores válidos
- **THEN** la respuesta es la de éxito del recurso (201 en un alta)

### Requirement: Las respuestas de usuario nunca incluyen el hash

Ninguna respuesta de la API SHALL incluir `password_hash`, ni el modelo de tabla, ni el hash parcial, ni en un campo anidado.

#### Scenario: Alta de usuario

- **WHEN** `POST /usuarios` crea un usuario y responde 201
- **THEN** el cuerpo trae id, email, nombre, `activo` y `debe_cambiar_password`, y NO trae `password_hash` ni el hash en ningún campo

#### Scenario: Contrato de salida explícito

- **WHEN** el handler devuelve la entidad del ORM
- **THEN** el `response_model` filtra los atributos: sólo los campos declarados en el contrato de salida llegan al cliente

### Requirement: El dinero viaja como string Decimal

Todo campo de dinero SHALL ser `Decimal` en Python y MUST serializarse como string con dos decimales en las respuestas; MUST NOT serializarse como número ni usar `float` en ningún punto.

#### Scenario: Precio de un repuesto en un listado

- **WHEN** se lee un repuesto cuyo precio es `8500.00`
- **THEN** el JSON trae `"precio": "8500.00"` (string) y no `8500` ni `8500.0`

#### Scenario: Precio en el alta

- **WHEN** se crea un repuesto con `precio` enviado como número o como string numérico
- **THEN** el valor se convierte a `Decimal`, se valida `> 0` con hasta diez dígitos y dos decimales, y la respuesta lo devuelve como string de dos decimales

#### Scenario: Precio inválido

- **WHEN** el precio es cero, negativo, tiene más de dos decimales o excede los diez dígitos
- **THEN** la respuesta es 422

### Requirement: La contraseña se valida por bytes en el contrato

Todo contrato que reciba una contraseña SHALL rechazar con 422 la que supere **72 bytes** en UTF-8. El límite MUST medirse sobre los bytes y no sobre la cantidad de caracteres, y MUST aplicarse antes de cualquier llamada a bcrypt.

#### Scenario: Contraseña de 73 bytes

- **WHEN** se envía una contraseña de 73 bytes
- **THEN** la respuesta es 422 con un mensaje propio y no se calcula ningún hash

#### Scenario: Contraseña multibyte

- **WHEN** se envía una contraseña de 37 caracteres «ñ» (74 bytes)
- **THEN** la respuesta es 422: el límite es de bytes, no de caracteres

#### Scenario: Contraseña de exactamente 72 bytes

- **WHEN** se envía una contraseña de exactamente 72 bytes
- **THEN** el contrato la acepta y el alta responde 201

### Requirement: Los PATCH aplican sólo los campos enviados

Un contrato de PATCH SHALL declarar todos sus campos opcionales y el servicio SHALL aplicar únicamente los campos presentes en el cuerpo (`exclude_unset`), sin pisar con `null` los que no se enviaron.

#### Scenario: PATCH con un solo campo

- **WHEN** el cuerpo de un PATCH trae sólo `descripcion`
- **THEN** los cambios calculados contienen únicamente `descripcion` y el resto de los campos queda intacto

#### Scenario: PATCH con un campo prohibido

- **WHEN** el cuerpo de un PATCH de repuesto trae `stock`
- **THEN** la respuesta es 422: el stock sólo cambia por movimientos y no se edita por PATCH
