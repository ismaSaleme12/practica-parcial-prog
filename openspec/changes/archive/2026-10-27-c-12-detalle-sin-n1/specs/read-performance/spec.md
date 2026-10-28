# Spec Delta

## Purpose

Define los invariantes medibles de lectura y asincronía de la API (US-025 y US-026, casos C-15 y C-12): toda lectura con filas hijas se resuelve con un número fijo de consultas, ninguna depende de la carga perezosa, la suite mide ese conteo contra el motor real sin dependencias extra, todos los handlers son asincrónicos y `SQL_ECHO` es habilitable por entorno con default `false`. El objetivo es que el rendimiento no dependa de la cantidad de ítems, vehículos u órdenes, y que la degradación se detecte como un test rojo y no en producción.

## ADDED Requirements

### Requirement: Las lecturas con filas hijas usan un número fijo de consultas

`GET /ordenes/{id}`, `GET /clientes/{id}`, `GET /mis-vehiculos` y `GET /mis-ordenes` SHALL precargar sus relaciones en el repositorio y MUST mantener el mismo número de consultas al crecer las filas hijas. Los conteos de referencia en la petición completa están en los escenarios.

#### Scenario: Detalle con 2 y 4 ítems (caso C-15)

- **WHEN** se consulta el detalle de una orden con 2 ítems y el de otra con 4 ítems del mismo vehículo, con la misma sesión
- **THEN** ambas respuestas son 200 y el contador de cursor registra el **mismo** número de consultas (5), sin una consulta por ítem

#### Scenario: El historial no agrega consultas por línea

- **WHEN** se compara el detalle de una orden con una línea de historial y el de la misma orden tras `iniciar`, con dos líneas
- **THEN** el conteo es idéntico y la sentencia del historial aparece una sola vez

#### Scenario: Ficha del cliente con 1 y 3 vehículos

- **WHEN** se consulta `GET /clientes/{id}` para un cliente con 1 vehículo y para uno con 3
- **THEN** las dos respuestas son 200 y el conteo es el mismo (4), con una sola sentencia sobre `vehiculo`

#### Scenario: Mis vehículos con 2 y 3 vehículos

- **WHEN** el cliente de la sesión consulta `/mis-vehiculos` con 2 vehículos y luego con 3
- **THEN** ambas respuestas son 200 y el conteo es el mismo (3)

#### Scenario: Mis órdenes con 1 y 2 órdenes

- **WHEN** el cliente de la sesión consulta `/mis-ordenes` con 1 orden visible y luego con 2
- **THEN** ambas respuestas son 200, `total` refleja la cantidad real y el conteo es el mismo (5: `count` + página con el vehículo precargado)

### Requirement: Ninguna lectura depende de la carga perezosa

Toda relación que una lectura devuelve SHALL precargarse en el repositorio que la necesita con `joinedload` o `selectinload`. Las relaciones del modelo MUST declarar `lazy="raise_on_sql"`: un acceso no precargado lanza en vez de emitir una consulta silenciosa o devolver `None`. La precarga MUST declararse en el repositorio, no en el router ni en el servicio.

#### Scenario: Lectura completa sin accesos perezosos

- **WHEN** se pide el detalle de una orden o la ficha de un cliente con sus vehículos
- **THEN** la respuesta es 200 y todas las relaciones que el contrato usa vienen de las consultas de precarga

#### Scenario: Precarga olvidada

- **WHEN** un repositorio devuelve una entidad sin precargar una relación que el mapeo toca
- **THEN** el acceso lanza (`raise_on_sql`) en vez de emitir una consulta por fila o devolver un valor vacío, y el defecto se ve en la suite

### Requirement: La medición se hace contra el motor real sin dependencias extra

La suite SHALL medir el conteo con un listener `before_cursor_execute` sobre `engine.sync_engine`, registrado antes de la petición medida y retirado después. La medición MUST NOT usar mocks de base ni dependencias adicionales, y MUST excluir del conteo el seed y el login.

#### Scenario: Medición acotada a la petición

- **WHEN** un test registra el contador y ejecuta una única petición
- **THEN** sólo se cuentan las sentencias de esa petición, y el listener se retira aunque la aserción falle

#### Scenario: Un contador que no dispara no aprueba la prueba

- **WHEN** el listener no registra sentencias
- **THEN** la verificación falla por el piso mínimo de consultas, no por una igualdad vacía (`0 == 0`)

### Requirement: Los handlers son asincrónicos y no ejecutan IO bloqueante

Todos los endpoints SHALL declararse con `async def`. El trabajo bloqueante —en particular bcrypt— MUST ejecutarse fuera del bucle de eventos con `asyncio.to_thread`. La aplicación MUST NOT usar `time.sleep`, `open()`, `subprocess`, clientes HTTP síncronos ni otra llamada bloqueante en handlers o servicios.

#### Scenario: Introspección de rutas

- **WHEN** se recorren las rutas de la aplicación
- **THEN** todo endpoint es una corrutina y no hay ningún handler declarado con `def`

#### Scenario: Hash de contraseñas

- **WHEN** se hashea o verifica una contraseña
- **THEN** bcrypt corre en un hilo aparte mediante `asyncio.to_thread` y el bucle de eventos queda libre

### Requirement: `SQL_ECHO` es habilitable por entorno y su default es `false`

La configuración SHALL exponer `SQL_ECHO` como booleano leído del entorno o del `.env`, con default `false`. El motor del ciclo de vida MUST crearse con `echo=settings.SQL_ECHO`. La suite MUST mantenerlo en `false`.

#### Scenario: Default silencioso

- **WHEN** no se define `SQL_ECHO`
- **THEN** el valor es `false` y el motor no imprime sentencias

#### Scenario: Activación por entorno

- **WHEN** se define `SQL_ECHO=true`
- **THEN** `Settings` lo expone como `True` y el motor creado en el lifespan imprime las sentencias en consola

#### Scenario: La suite no lo activa

- **WHEN** corre la suite automatizada
- **THEN** `settings.SQL_ECHO` y `engine.echo` son `false`
