# list-pagination-stub Specification

## Purpose
Define el primer listado real de la API: el catálogo de repuestos con el envoltorio uniforme de paginación, búsqueda por texto con parámetros ligados y el error propio de página fuera de rango.

## Requirements

### Requirement: El listado devuelve el envoltorio uniforme

Todo listado SHALL responder `{items, total, page, size, pages}`: `total` cuenta con los mismos filtros que la página, `page` empieza en 1, `size` va de 1 a 100 con 20 por defecto y `pages` es el techo de `total / size`.

#### Scenario: Primera página de repuestos

- **WHEN** se pide `GET /repuestos?size=2` con cuatro repuestos cargados
- **THEN** la respuesta trae dos items, `total: 4`, `page: 1`, `size: 2` y `pages: 2`

#### Scenario: Sin resultados

- **WHEN** el filtro no coincide con ningún repuesto
- **THEN** la respuesta trae `items: []`, `total: 0`, `pages: 0` y la página pedida (con `page: 1`)

### Requirement: Las páginas son deterministas

El repositorio SHALL declarar un orden estable para el listado, de modo que dos páginas consecutivas no repitan ni omitan filas.

#### Scenario: Segunda página

- **WHEN** se piden `size=2` las páginas 1 y 2 de cuatro repuestos
- **THEN** la primera trae los dos primeros en el orden declarado y la segunda los dos siguientes, sin repetir ninguno

### Requirement: La página fuera de rango responde 422

Pedir una página posterior a la última SHALL responder 422 con un mensaje propio que indique la página pedida y la cantidad disponible.

#### Scenario: Página inexistente

- **WHEN** se pide `GET /repuestos?page=3&size=2` con dos páginas disponibles
- **THEN** la respuesta es 422 con el mensaje «La página 3 no existe: hay 2.»

#### Scenario: Parámetros fuera de rango

- **WHEN** `page` es 0 o `size` es 101
- **THEN** la respuesta es 422 con un mensaje propio, antes de consultar la base

### Requirement: La búsqueda usa parámetros ligados

La búsqueda `q` SHALL viajar como parámetro ligado de la consulta. MUST NOT concatenarse en el texto del SQL.

#### Scenario: Intento de inyección

- **WHEN** se busca `q=' OR '1'='1`
- **THEN** la respuesta es 200 con `items: []` y `total: 0`: el valor se trata como texto de búsqueda

#### Scenario: Coincidencia parcial

- **WHEN** se busca un fragmento de la descripción de un repuesto existente
- **THEN** el listado devuelve los repuestos cuya descripción lo contiene y `total` coincide con la cantidad devuelta

### Requirement: El detalle de un repuesto inexistente responde 404

`GET /repuestos/{id}` SHALL devolver 200 con el repuesto vigente o 404 con mensaje propio si el id no existe o el repuesto está dado de baja.

#### Scenario: Detalle existente

- **WHEN** se pide un repuesto que existe y está vigente
- **THEN** la respuesta es 200 con su precio como string Decimal

#### Scenario: Detalle inexistente

- **WHEN** se pide un id que no existe
- **THEN** la respuesta es 404 con un mensaje propio
