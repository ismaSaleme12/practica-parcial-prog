# work-order-management Specification

## Purpose
Define el alta y la lectura de órdenes de trabajo (US-023, US-025 y RN-17): el alta PENDIENTE con el precio y el total calculados por el servidor, el listado paginado con patente, el detalle completo sin carga perezosa y la consulta de «mis órdenes» acotada al dueño del vehículo. El objetivo es que un cliente no pueda inventar la factura ni ver órdenes ajenas, y que el detalle se arme con un número fijo de consultas.

## Requirements

### Requirement: El alta calcula el precio y el total en el servidor

`POST /ordenes` SHALL aceptar únicamente `vehiculo_id`, `falla` e `items`, donde cada ítem sólo declara `repuesto_id` y `cantidad > 0`. El servicio MUST copiar el `precio_unitario` vigente de cada repuesto y MUST calcular `total` como la suma de `precio_unitario × cantidad` con `Decimal`. El cuerpo MUST NOT aceptar `precio_unitario`, `subtotal`, `total`, `estado`, `mecanico_id`, `cliente_id` ni `creada_en`.

#### Scenario: Alta válida

- **WHEN** un ADMIN envía `POST /ordenes` con un vehículo vigente, una falla y dos repuestos distintos con cantidades 1 y 4
- **THEN** la respuesta es 201, cada ítem trae el precio copiado del repuesto y `total` es la suma calculada como string con dos decimales (caso C-10)

#### Scenario: El cliente intenta fijar el precio o el total

- **WHEN** el cuerpo incluye `precio_unitario`, `total`, `estado` o `mecanico_id`
- **THEN** la respuesta es 422 nombrando el campo no declarado y no se crea ninguna orden

#### Scenario: Repuesto repetido

- **WHEN** dos ítems declaran el mismo `repuesto_id`
- **THEN** la respuesta es 422 y el detalle del error menciona `items`

#### Scenario: Lista de ítems vacía

- **WHEN** el cuerpo envía `items: []`
- **THEN** la respuesta es 422 y no se crea ninguna orden

### Requirement: El alta nace PENDIENTE y deja su primera línea de historial

`POST /ordenes` SHALL crear la orden en estado `PENDIENTE`, sin mecánico asignado, y SHALL insertar una línea de `historial_estado_orden` con `desde_estado: null`, `hasta_estado: "PENDIENTE"` y el usuario de la sesión, en la misma transacción que la orden y sus ítems. Si el catálogo no contiene `PENDIENTE`, SHALL responder 409 y no crear nada. Si el vehículo o algún repuesto no existe o está dado de baja, SHALL responder 409 y no crear nada.

#### Scenario: Orden recién creada

- **WHEN** se consulta el detalle de una orden recién creada
- **THEN** su estado es `PENDIENTE`, `mecanico_id` es `null` y el historial tiene una línea con `desde_estado: null` y `hasta_estado: "PENDIENTE"`

#### Scenario: Catálogo de estados vacío

- **WHEN** la tabla `estado_orden` no tiene filas y se intenta crear una orden
- **THEN** la respuesta es 409 con un mensaje que nombra el catálogo y no existe ninguna orden nueva (caso C-09)

#### Scenario: Vehículo o repuesto inválido

- **WHEN** el `vehiculo_id` o un `repuesto_id` no existe o está dado de baja
- **THEN** la respuesta es 409 y no se escribe la orden, ni sus ítems, ni el historial (caso C-10)

### Requirement: El listado es paginado, filtrable por estado y trae la patente

`GET /ordenes` SHALL responder el envoltorio `{items, total, page, size, pages}` con las órdenes ordenadas por `creada_en` descendente y, ante marcas iguales, por `id` descendente. Cada fila SHALL incluir la patente del vehículo precargada. El filtro `estado` SHALL aceptar sólo un código declarado del catálogo y SHALL responder 422 con cualquier otro valor. Una página fuera de rango SHALL responder 422.

#### Scenario: Página determinista

- **WHEN** se piden dos páginas consecutivas de tamaño 1
- **THEN** cada página trae una orden distinta, en orden de `creada_en` e `id` descendente, y `total` coincide con la cantidad real

#### Scenario: Filtro por estado

- **WHEN** se envía `GET /ordenes?estado=TERMINADA`
- **THEN** la respuesta es 200 y todas las filas tienen estado `TERMINADA`

#### Scenario: Estado no declarado

- **WHEN** se envía `GET /ordenes?estado=VOLANDO`
- **THEN** la respuesta es 422 y no se consulta la base (caso C-17)

### Requirement: El detalle se arma con un número fijo de consultas

`GET /ordenes/{id}` SHALL responder la orden con su vehículo, el cliente, los ítems con código, descripción, precio y `subtotal`, y el historial cronológico. El repositorio MUST precargar esas relaciones en tres consultas fijas y MUST NOT usar carga perezosa. La petición completa MUST mantenerse en cinco consultas con 2 y con 4 ítems.

#### Scenario: Detalle completo

- **WHEN** se consulta una orden con dos ítems y dos líneas de historial
- **THEN** la respuesta es 200 con `cliente`, `items` (cada uno con `codigo`, `descripcion`, `precio_unitario` y `subtotal` como string) e `historial` ordenado por `cuando` e `id`

#### Scenario: El conteo no crece con los ítems (caso C-15)

- **WHEN** se mide el detalle de una orden con 2 ítems y el de otra con 4 ítems del mismo vehículo, con la misma sesión y un contador `before_cursor_execute` sobre `engine.sync_engine`
- **THEN** el conteo es el mismo en ambos casos (5 consultas), la sentencia sobre `item_orden` aparece una sola vez y la sentencia sobre `historial_estado_orden` también

#### Scenario: Orden inexistente

- **WHEN** se consulta un id que no existe
- **THEN** la respuesta es 404 con un mensaje propio y no una respuesta vacía

### Requirement: El acceso al detalle respeta al personal y al dueño

`GET /ordenes/{id}` SHALL permitir la lectura al personal del taller (ADMIN, RECEPCION o MECANICO) y al cliente dueño del vehículo de la orden. Cualquier otra sesión SHALL recibir 403. La existencia de la orden SHALL verificarse antes que el permiso, para no disfrazar un id inexistente de «sin permiso».

#### Scenario: Cliente dueño

- **WHEN** el cliente dueño del vehículo pide el detalle de su orden
- **THEN** la respuesta es 200 (caso C-06)

#### Scenario: Cliente ajeno

- **WHEN** un cliente pide el detalle de una orden de otro vehículo
- **THEN** la respuesta es 403 y el cuerpo no revela datos de la orden

#### Scenario: Personal del taller

- **WHEN** un ADMIN, RECEPCION o MECANICO pide el detalle de cualquier orden existente
- **THEN** la respuesta es 200

### Requirement: Mis órdenes se acota a los vehículos del cliente de la sesión

`GET /mis-ordenes` SHALL responder el envoltorio paginado con las órdenes de los vehículos del cliente asociado a la sesión, ordenadas igual que `GET /ordenes`. Una sesión sin ficha de cliente SHALL recibir 200 con una página vacía (`total: 0`), no un error. La ruta SHALL exigir sesión válida y MUST NOT exigir un rol de taller.

#### Scenario: Cliente con vehículos

- **WHEN** el cliente dueño de dos vehículos consulta `/mis-ordenes`
- **THEN** la respuesta sólo incluye las órdenes de esos vehículos (RN-17)

#### Scenario: Sesión sin ficha de cliente

- **WHEN** una sesión de ADMIN o de un usuario sin ficha consulta `/mis-ordenes`
- **THEN** la respuesta es 200 con `items: []` y `total: 0`

#### Scenario: Sin sesión

- **WHEN** se consulta `/mis-ordenes` sin cookie
- **THEN** la respuesta es 401
