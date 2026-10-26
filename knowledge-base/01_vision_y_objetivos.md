# Visión y Objetivos

## Propósito del sistema

Una **API REST asincrónica** para el trabajo diario de un taller mecánico: gestionar clientes, vehículos, órdenes de trabajo y stock de repuestos, con autenticación por cookie HttpOnly y autorización por roles decidida en la base de datos.

El taller necesita un sistema donde la recepción dé de alta a clientes y vehículos y abra una orden por cada ingreso (con la falla y los repuestos a usar); el mecánico tome la orden, la repare y la dé por terminada —descontando el stock de cada repuesto usado—; el administrador mantenga el catálogo de repuestos, repone el stock y administre personal y roles; y el cliente se registre solo y consulte el estado de sus vehículos.

El proyecto es el **trabajo práctico integrador de las unidades 1 a 6 de Programación III** ("del objeto a la transacción"). El dominio del taller fue elegido para que cada capítulo tenga un lugar concreto donde aparecer:

| Lo que pide el dominio | Por qué | Capítulo |
|---|---|---|
| La orden nace con sus ítems; un ítem no existe sin su orden | Composición: los datos de cada ítem viajan dentro del alta de la orden | 4 |
| Un cliente puede tener o no un usuario, y a lo sumo uno | Uno a uno opcional: `cliente.usuario_id` UNIQUE y nulo permitido | 4 |
| Un vehículo que se vendió se da de baja, pero sus órdenes viejas siguen, y el comprador lo puede registrar con la misma patente | Borrado lógico e índice único parcial | 4 y 6 |
| Cuatro roles, que el administrador asigna y revoca con vigencia | La autorización se decide en la base, no en el token | 5 |
| El registro crea el usuario, su rol y su ficha de cliente | Tres escrituras que no tienen sentido por separado | 6 |
| Terminar una orden descuenta el stock de cada repuesto | Cuatro clases de escritura en una sola transacción | 6 |
| El límite de intentos de login se calcula contando una tabla | El intento tiene que sobrevivir al rollback del login fallido | 5 y 6 |
| Los estados de una orden son una lista fija que el sistema necesita para funcionar | Catálogo: tabla de referencia apuntada con clave foránea y cargada por `seed.py` | 4 |
| El historial de estados, los movimientos de stock y los cambios de precio no se corrigen | Sólo agregado, impuesto por la base | 6 |

## Objetivos por actor

| Actor | Objetivo principal | Objetivos secundarios |
|---|---|---|
| **Recepción** | Dar de alta clientes, vehículos y órdenes de trabajo | Cancelar órdenes; ver fichas de clientes con sus vehículos |
| **Mecánico** | Tomar (iniciar) y terminar órdenes asignadas | Ver el catálogo de repuestos y buscar por descripción; ver el detalle de sus órdenes |
| **Administrador** | Administrar el personal y sus roles; mantener el catálogo de repuestos | Reponer stock, editar precios (con historial), dar de baja repuestos/vehículos; ver eventos de seguridad; cancelar y terminar cualquier orden |
| **Cliente** | Registrarse en la web y consultar el estado de sus vehículos | Ver sus órdenes (`/mis-*`); cancelar órdenes de sus vehículos pendientes |
| **Sistema** | Registrar eventos de seguridad con el actor `SISTEMA` (texto, no usuario) | Cargar los datos iniciales vía `seed.py` |

## Alcance v1.0 (del objeto a la transacción)

- API REST asincrónica con FastAPI; todos los handlers con `async def`.
- Persistencia relacional en PostgreSQL 16 con SQLModel + SQLAlchemy 2.0 asincrónico y migraciones versionadas con Alembic (plantilla asincrónica). **Sólo** Alembic crea el esquema; `create_all` está prohibido.
- Autenticación con bcrypt (hash de contraseñas) y JWT firmado emitido en cookie `HttpOnly` (`SameSite=Lax`), sin revelar qué cuentas existen y sin frenar el servidor.
- Autorización con cuatro roles (ADMIN, RECEPCION, MECANICO, CLIENTE) asignados con vigencia (`desde`/`vence_en`) y revocación (`revocada_en`); los roles se consultan **en la base, en cada petición**.
- Transacciones: el Unit of Work agrupa las escrituras de cada operación de negocio (registro, terminar orden, cambio de precio con historial).
- 13 tablas con restricciones delegadas a la base: UNIQUE, claves foráneas, CHECK, índices únicos parciales (borrado lógico) y disparador de sólo agregado sobre tres tablas de auditoría.
- Catálogo `estado_orden` cargado por `seed.py`; estados de orden fijos (PENDIENTE, EN_REPARACION, TERMINADA, CANCELADA).
- Borrado lógico de vehículos y repuestos (la fila se conserva; la unicidad es sólo entre los vigentes).
- Paginación de listados con el envoltorio `{items, total, page, size, pages}`.
- Salud del proceso: `GET /health/live` (no toca la base) y `GET /health/ready` (ejecuta `SELECT 1`, 503 si la base no contesta).
- Casos de prueba mínimos C-01 a C-19 en archivos `.http` dentro de `test/`, más `test/solo_agregado.sql` para el caso C-14.
- Aviso al cliente simulado con `BackgroundTasks` (mismo proceso) al terminar una orden.

## Fuera de alcance

- **Concurrencia (capítulo 7)**: no se evalúa. Dos órdenes que se terminan al mismo tiempo pueden leer ambas el mismo stock, darlo las dos por suficiente y descontar cada una sobre el valor que leyó (actualización perdida permitida por el nivel de aislamiento por defecto). El bloqueo que la evita es tema de la próxima clase.
- **Colas de tareas con Redis (capítulo 8)**: no hay colas. El aviso al cliente se resuelve con `BackgroundTasks` en el mismo proceso; si el proceso se reinicia el aviso se pierde y no hay reintento. Se acepta porque el aviso es simulado y perderlo no rompe nada (el capítulo 8 lo resuelve).
- **Segundo mecanismo de sólo agregado por permisos de rol de base**: la sección 6.9 lo describe, pero el TP usa un solo rol de base y no se pide (cualquiera de los dos mecanismos alcanza; tener los dos es defensa en profundidad).
- Interfaz gráfica: el alcance es la API; la web del taller es el cliente que consume la API.
- Multi-taller / multi-tenant: es un taller, un despliegue.

## Métricas de éxito

Los **criterios de evaluación** del TP son la medida de éxito del proyecto:

| Criterio | Peso | Qué se mira |
|---|---|---|
| Proyecto, configuración y ciclo de vida | 8 % | Estructura, `Settings` sin secretos por defecto, motor y fábrica creados en el lifespan, `get_session`, salud |
| Modelos, relaciones y migraciones | 14 % | Restricciones, índices únicos parciales, catálogo con clave foránea, navegación, dos migraciones (una a mano), upgrade y downgrade |
| Contratos y CRUD | 10 % | Contratos separados, `extra="forbid"`, códigos, ninguna entrada inválida en 500, PATCH parcial, envoltorio y paginación |
| Autenticación | 16 % | bcrypt fuera del bucle y con semáforo, orden del login, límite, hash ficticio, cookie HttpOnly |
| Autorización | 14 % | 401 vs 403, roles vigentes en la base, autoprotección, dos grupos de rutas, `iat`, lo propio |
| Repositorios y Unit of Work | 20 % | Dos jerarquías, clase del modelo, `flush` y no `commit`, precarga en el repositorio, quién crea/abre/confirma/cierra, operaciones de varias escrituras |
| Integridad | 10 % | Disparador de sólo agregado en las tres tablas; historial de precios en la misma transacción; intento de acceso en su propia sesión |
| Lecturas sin N+1 y asincronía | 8 % | Consultas fijas en el detalle; ninguna llamada bloqueante; aviso en segundo plano |

Condición dura: *un proyecto que no levanta, que no crea su esquema con `alembic upgrade head` sobre una base vacía o que contiene credenciales reales en el repositorio no se corrige hasta que se subsane.*
