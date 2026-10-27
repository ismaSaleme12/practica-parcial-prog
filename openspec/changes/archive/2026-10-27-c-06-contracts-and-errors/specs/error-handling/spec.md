# Spec Delta

## Purpose

Define cómo la API traduce los errores a códigos y mensajes propios: conflicto de integridad, recurso inexistente, cuerpo o parámetros inválidos, y la garantía de que ninguna entrada inválida termine en 500 ni exponga el esquema.

## ADDED Requirements

### Requirement: El conflicto de integridad responde 409 con mensaje propio

Cuando una escritura viola una restricción de la base, la API SHALL responder 409 con un mensaje propio. MUST NOT devolver el texto de la excepción del motor, el nombre de la tabla, el nombre del índice, el valor duplicado ni una traza.

#### Scenario: Código de repuesto repetido

- **WHEN** se intenta crear un repuesto con un `codigo` que ya tiene un repuesto vigente
- **THEN** la respuesta es 409, el cuerpo trae un mensaje propio y no contiene `duplicate key`, el nombre del índice ni el valor del código

#### Scenario: Email repetido

- **WHEN** se intenta crear un usuario con un email que ya existe
- **THEN** la respuesta es 409 con el mismo mensaje propio y el usuario no se crea

#### Scenario: La transacción no queda a medias

- **WHEN** la violación ocurre dentro de un Unit of Work
- **THEN** el Unit of Work revierte todo lo escrito en esa petición antes de que se emita el 409

### Requirement: El recurso de la ruta inexistente responde 404

Cuando el identificador de la ruta no corresponde a ningún recurso vigente, la API SHALL responder 404 con un mensaje propio.

#### Scenario: Repuesto inexistente

- **WHEN** se pide `GET /repuestos/{id}` con un id que no existe
- **THEN** la respuesta es 404 con un mensaje propio que nombra el recurso y el id

#### Scenario: Ruta inexistente

- **WHEN** se pide una ruta que la aplicación no declara
- **THEN** la respuesta es 404 con un mensaje propio, sin traza

### Requirement: La entrada inválida responde 422, nunca 500

Todo cuerpo, parámetro de ruta o de query que no cumpla el contrato SHALL responder 422 con un mensaje propio y la indicación del campo. Ninguna entrada inválida MUST terminar en 500.

#### Scenario: Validación de Pydantic

- **WHEN** un campo obligatorio falta, tiene un tipo inválido o un texto excede la longitud del esquema
- **THEN** la respuesta es 422 con un mensaje propio y la lista de campos con su motivo

#### Scenario: Parámetros de paginación

- **WHEN** `page` es menor que 1, `size` queda fuera de 1–100, o el valor no es un entero
- **THEN** la respuesta es 422 con un mensaje propio

#### Scenario: Datos que la base rechaza por formato

- **WHEN** un valor pasa el contrato pero el motor lo rechaza por formato o longitud
- **THEN** la respuesta es 422 con un mensaje propio y no una traza del motor

### Requirement: Los códigos de estado son consistentes

La API SHALL usar 201 para un alta creada, 204 para una baja sin cuerpo, 404 para el recurso de la ruta inexistente, 409 para el choque con lo guardado y 422 para el incumplimiento del contrato.

#### Scenario: Alta exitosa

- **WHEN** se crea un recurso con un cuerpo válido
- **THEN** la respuesta es 201 con el recurso creado

#### Scenario: Error de negocio con mensaje específico

- **WHEN** el servicio detecta una regla de negocio que el cliente puede corregir y que no es una violación de integridad
- **THEN** responde con la excepción `Conflicto` (409) o `RecursoNoEncontrado` (404), con el mensaje que declara el servicio
