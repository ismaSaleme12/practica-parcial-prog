# customer-management Specification

## Purpose
Define el alta de clientes del taller y la consulta de su ficha con los vehículos vigentes. El objetivo es que la cartera se cree sobre datos únicos garantizados por la base y que la ficha se lea sin carga perezosa, con un número fijo de consultas.

## Requirements

### Requirement: El alta de cliente exige ADMIN o RECEPCION y responde 201

`POST /clientes` SHALL exigir una sesión válida y uno de los roles ADMIN o RECEPCION. Con un cuerpo válido MUST responder 201 con la ficha plana (`id`, `nombre`, `documento`, `telefono`) y MUST NOT incluir `vehiculos`. Sin sesión MUST responder 401; con CLIENTE o MECANICO MUST responder 403.

#### Scenario: Alta válida por recepción

- **WHEN** una sesión con rol RECEPCION envía nombre, documento y teléfono válidos
- **THEN** la respuesta es 201 con la ficha creada y sin la clave `vehiculos`

#### Scenario: Alta por un rol que no administra la cartera

- **WHEN** una sesión con rol CLIENTE o MECANICO pide `POST /clientes`
- **THEN** la respuesta es 403 y no se crea ninguna fila

#### Scenario: Sin sesión

- **WHEN** se pide `POST /clientes` sin la cookie `access_token`
- **THEN** la respuesta es 401

#### Scenario: Campo no declarado

- **WHEN** el cuerpo incluye `usuario_id` o cualquier campo que el contrato no declara
- **THEN** la respuesta es 422 y no se crea ninguna fila

### Requirement: El documento del cliente es único

`cliente.documento` SHALL ser único y la unicidad MUST garantizarla la base, sin una consulta previa de la API. Un documento repetido MUST responder 409 con el mensaje propio de conflicto, sin texto del motor ni nombre del índice.

#### Scenario: Documento repetido

- **WHEN** una sesión ADMIN o RECEPCION da de alta un cliente con un documento que ya existe
- **THEN** la respuesta es 409 con `{"detail": "La operación entra en conflicto con datos ya guardados."}`

#### Scenario: Documento nuevo

- **WHEN** el documento no existe
- **THEN** la respuesta es 201 y la fila queda guardada

### Requirement: La ficha devuelve los vehículos vigentes por carga anticipada

`GET /clientes/{id}` SHALL exigir ADMIN o RECEPCION y devolver la ficha con `vehiculos`, resueltos por precarga en el repositorio (`selectinload`) en un número fijo de consultas. La lectura MUST NOT depender de la carga perezosa: las relaciones del modelo son `lazy="raise_on_sql"`. Los vehículos con `borrado_en` escrito MUST NOT aparecer. Un id inexistente MUST responder 404 con mensaje propio.

#### Scenario: Ficha con vehículos vigentes

- **WHEN** un ADMIN o RECEPCION consulta la ficha de un cliente con dos vehículos vigentes
- **THEN** la respuesta es 200 con los dos vehículos y se resuelve en dos consultas, sin accesos perezosos

#### Scenario: Vehículo dado de baja

- **WHEN** uno de los vehículos del cliente tiene `borrado_en` escrito
- **THEN** la ficha responde 200 y ese vehículo no aparece en `vehiculos`

#### Scenario: Cliente inexistente

- **WHEN** se consulta la ficha de un id que no existe
- **THEN** la respuesta es 404 con un mensaje propio

#### Scenario: Rol insuficiente

- **WHEN** una sesión con rol CLIENTE o MECANICO consulta una ficha existente
- **THEN** la respuesta es 403 y la ficha no se devuelve
