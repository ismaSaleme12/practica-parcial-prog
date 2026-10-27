# work-order-catalog Specification

## Purpose
Define el catálogo de estados de una orden (DD-01, DD-07 y RN-19): su consulta de sólo lectura ordenada por `posicion`, los cuatro códigos que el contrato declara y la validación del filtro de estado. El objetivo es que la API lea el catálogo pero nunca lo escriba, y que un estado que el contrato no declara sea un 422 de entrada y no un 409 ni una lista vacía.

## Requirements

### Requirement: El catálogo se consulta por posición

`GET /estados-orden` SHALL responder una lista con `codigo`, `descripcion`, `posicion` y `es_final` de todos los estados, ordenada por `posicion` ascendente. La ruta SHALL exigir una sesión válida y MUST NOT exigir un rol de taller.

#### Scenario: Catálogo del seed

- **WHEN** cualquier sesión válida consulta `GET /estados-orden`
- **THEN** la respuesta es 200 con cuatro filas en el orden `PENDIENTE`, `EN_REPARACION`, `TERMINADA`, `CANCELADA` y con sus `es_final` correspondientes

#### Scenario: Sin sesión

- **WHEN** se consulta `GET /estados-orden` sin cookie
- **THEN** la respuesta es 401

### Requirement: El catálogo es de sólo lectura desde la API

La API MUST NOT exponer ninguna ruta de alta, edición o borrado sobre `estado_orden` (RN-19). El repositorio del catálogo MUST NOT ofrecer operaciones de escritura: sólo `get(codigo)` y `listar()`. Las filas se crean y se mantienen por migración y seed.

#### Scenario: No hay rutas de escritura

- **WHEN** se revisan las rutas del módulo de órdenes
- **THEN** ninguna acepta `POST`, `PATCH` ni `DELETE` sobre `/estados-orden`

#### Scenario: El servicio sólo lee el catálogo

- **WHEN** se crea una orden
- **THEN** el servicio verifica que `PENDIENTE` exista con una lectura y no escribe ninguna fila del catálogo

### Requirement: El filtro de estado se valida contra el contrato

El parámetro `estado` de `GET /ordenes` SHALL aceptar únicamente los códigos declarados por el contrato (`PENDIENTE`, `EN_REPARACION`, `TERMINADA`, `CANCELADA`). Cualquier otro valor SHALL responder 422 antes de consultar la base. El catálogo de la tabla es la fuente de verdad de la descripción y la posición; el enum del contrato es la validación de entrada.

#### Scenario: Estado declarado

- **WHEN** se envía `GET /ordenes?estado=EN_REPARACION`
- **THEN** la respuesta es 200 y sólo incluye órdenes en ese estado

#### Scenario: Estado no declarado

- **WHEN** se envía `GET /ordenes?estado=VOLANDO` o cualquier otro valor fuera del enum
- **THEN** la respuesta es 422 (caso C-17) y no se ejecuta ninguna consulta de órdenes
