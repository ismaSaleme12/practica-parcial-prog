# Spec Delta

## Purpose

Define «lo propio» de la Épica 6: consultar los vehículos del cliente dueño de la sesión. El objetivo es que un cliente vea su cartera y nada más, sin necesitar un rol de personal, y que una cuenta sin ficha reciba una respuesta vacía en vez de un error.

## ADDED Requirements

### Requirement: `GET /mis-vehiculos` sólo exige estar autenticado

`GET /mis-vehiculos` SHALL exigir una sesión válida y MUST NOT exigir un rol: los cuatro roles (ADMIN, RECEPCION, MECANICO, CLIENTE) MUST poder llamarla. Sin sesión MUST responder 401.

#### Scenario: Cliente autenticado

- **WHEN** una sesión con rol CLIENTE pide `GET /mis-vehiculos`
- **THEN** la respuesta es 200

#### Scenario: Personal autenticado

- **WHEN** una sesión con rol ADMIN, RECEPCION o MECANICO pide `GET /mis-vehiculos`
- **THEN** la respuesta es 200 con la lista de su ficha o vacía, nunca 403 por el rol

#### Scenario: Sin sesión

- **WHEN** se pide `GET /mis-vehiculos` sin la cookie `access_token`
- **THEN** la respuesta es 401

### Requirement: La lista se acota al cliente dueño de la sesión

La ruta SHALL ubicar la ficha por `cliente.usuario_id` igual al id del usuario de la sesión y devolver únicamente sus vehículos **vigentes** (`borrado_en IS NULL`), precargados en el repositorio sin carga perezosa. Una cuenta sin ficha de cliente MUST recibir una lista vacía con 200: ni 404 ni 500.

#### Scenario: El cliente ve sus vehículos

- **WHEN** el cliente dueño de dos vehículos vigentes pide `GET /mis-vehiculos`
- **THEN** la respuesta es 200 con esos dos vehículos

#### Scenario: No ve los vehículos de otro cliente

- **WHEN** existe un vehículo de otro cliente (con o sin cuenta propia)
- **THEN** ese vehículo no aparece en la respuesta del cliente de la sesión

#### Scenario: Vehículo propio dado de baja

- **WHEN** uno de los vehículos del cliente tiene `borrado_en` escrito
- **THEN** la respuesta es 200 y ese vehículo no aparece

#### Scenario: Cuenta sin ficha de cliente

- **WHEN** la sesión es de una cuenta de personal que no tiene ficha de cliente
- **THEN** la respuesta es 200 con `[]`
