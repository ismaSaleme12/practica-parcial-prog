# Spec Delta

## Purpose

Define el ABM del catálogo de repuestos sobre el esquema de `C-04`: listado y detalle con búsqueda parametrizada, alta con stock inicial, edición limitada a descripción y precio, baja lógica con código reutilizable y la matriz de permisos de la Épica 7. El objetivo es que el catálogo se pueda mantener sin abrir ninguna puerta que permita editar el stock a mano ni inyectar SQL.

## ADDED Requirements

### Requirement: El listado se pagina con el envoltorio uniforme y búsqueda parametrizada

`GET /repuestos` SHALL aceptar `q`, `page` y `size`, responder `{items, total, page, size, pages}` y aplicar el filtro de descripción con **parámetros ligados**. `total` MUST contar con los mismos filtros que la página.

#### Scenario: Búsqueda con comillas no inyecta SQL

- **WHEN** se pide `GET /repuestos?q=' OR '1'='1`
- **THEN** la respuesta es 200 con `items: []` y `total: 0`

#### Scenario: Página fuera de rango

- **WHEN** se pide una página posterior a la última
- **THEN** la respuesta es 422 con el mensaje de paginación propio

#### Scenario: Dinero como string

- **WHEN** se consulta un repuesto
- **THEN** `precio` viaja como string Decimal (por ejemplo `"8500.00"`), nunca como número

### Requirement: El alta acepta stock_inicial y rechaza stock

`POST /repuestos` SHALL aceptar `codigo`, `descripcion`, `precio` y `stock_inicial` (`int`, `>= 0`, por defecto 0) y MUST NOT declarar `stock`. El repuesto SHALL nacer con `stock` igual a `stock_inicial`.

#### Scenario: Alta con stock inicial

- **WHEN** se da de alta un repuesto con `stock_inicial: 7`
- **THEN** la respuesta es 201 con `stock: 7`

#### Scenario: Alta sin stock inicial

- **WHEN** se omite `stock_inicial`
- **THEN** la respuesta es 201 con `stock: 0`

#### Scenario: Stock negativo

- **WHEN** se envía `stock_inicial: -1`
- **THEN** la respuesta es 422 y el campo `stock_inicial` aparece en los errores

#### Scenario: Stock directo en el alta

- **WHEN** se envía `stock` en lugar de `stock_inicial`
- **THEN** la respuesta es 422 porque el campo no está declarado (`extra="forbid"`)

### Requirement: La edición sólo cambia descripción y precio, y sólo lo enviado

`PATCH /repuestos/{id}` SHALL aplicar la convención `exclude_unset`: sólo las claves presentes en el cuerpo. `RepuestoPatch` MUST NOT declarar `stock` ni `stock_inicial`. SHALL responder 404 si el repuesto no existe o está dado de baja y 200 con el repuesto actualizado en caso contrario.

#### Scenario: Stock en el cuerpo del PATCH

- **WHEN** se envía `{"stock": 99}`
- **THEN** la respuesta es 422 con el campo `stock` en los errores y el stock guardado no cambia (caso C-16)

#### Scenario: Sólo descripción

- **WHEN** se envía únicamente `descripcion`
- **THEN** la respuesta es 200 y el precio no cambia

#### Scenario: Repuesto inexistente

- **WHEN** se hace PATCH sobre un id que no existe
- **THEN** la respuesta es 404 con un mensaje propio

### Requirement: La baja es lógica y el código queda libre

`DELETE /repuestos/{id}` SHALL responder 204 sin cuerpo y MUST escribir `borrado_en` sin borrar la fila. El repuesto dado de baja MUST dejar de aparecer en el listado y en el detalle (404), y su `codigo` SHALL poder reutilizarse en un alta nueva gracias al índice único parcial.

#### Scenario: Baja y detalle posterior

- **WHEN** se da de baja un repuesto y después se pide su detalle
- **THEN** la baja responde 204 y el detalle responde 404

#### Scenario: Reutilización del código

- **WHEN** se da de baja `FA-001` y se vuelve a crear un repuesto con ese código
- **THEN** el alta responde 201 y la base conserva las dos filas, con `borrado_en` sólo en la primera

#### Scenario: Código repetido entre vigentes

- **WHEN** se intenta crear un repuesto con el código de otro vigente
- **THEN** la respuesta es 409 con el mensaje propio y sin texto del motor

### Requirement: La matriz de permisos se aplica por ruta

El listado y el detalle SHALL aceptar ADMIN, RECEPCION y MECANICO. El alta, la edición, la baja, la reposición y los dos historiales MUST exigir ADMIN.

#### Scenario: Sin sesión

- **WHEN** se pide cualquiera de las seis rutas de ADMIN sin cookie
- **THEN** la respuesta es 401, antes de evaluar el rol

#### Scenario: Recepción en una ruta de ADMIN

- **WHEN** un usuario con RECEPCION pide `POST`, `PATCH`, `DELETE`, `/reponer`, `/movimientos` o `/precios`
- **THEN** la respuesta es 403 con el mensaje de permiso (caso B-04)

#### Scenario: Recepción consultando el catálogo

- **WHEN** un usuario con RECEPCION pide `GET /repuestos` o `GET /repuestos/{id}`
- **THEN** la respuesta es 200
