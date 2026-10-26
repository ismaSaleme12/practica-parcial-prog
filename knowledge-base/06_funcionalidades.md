# Funcionalidades

Organizadas por **épica** y luego por **historia de usuario** (formato US-NNN). Las épicas siguen el orden de los 8 ejercicios del TP, que es el orden en que se construye el sistema.

## Épica 1: Proyecto, configuración y ciclo de vida (Ejercicio 1 — 8 %)

### US-001 — Estructura de proyecto obligatoria
**Como** desarrollador
**Quiero** la estructura por módulo funcional con las seis capas en todos los módulos
**Para** que cada capa sepa lo suyo y nada más

**Criterios de aceptación**:
- [ ] CA-1: `main.py` (aplicación, lifespan y los dos grupos de rutas) y `seed.py` en la raíz
- [ ] CA-2: `app/core/` con `config.py`, `database.py`, `security.py`, `dependencies.py`, `repository.py`, `paginacion.py`, `unit_of_work.py`
- [ ] CA-3: `app/modules/<módulo>/` con `models.py`, `schemas.py`, `repository.py`, `unit_of_work.py`, `service.py`, `router.py`
- [ ] CA-4: `migrations/` (Alembic) y `test/` (archivos `.http` y `solo_agregado.sql`)
- [ ] CA-5: Módulos mínimos: `health`, `usuarios`, `clientes`, `repuestos`, `ordenes`. `AsignacionRol`, `IntentoAcceso` y `EventoSeguridad` viven en `usuarios`; `Vehiculo` en `clientes`; `MovimientoStock` y `HistorialPrecio` en `repuestos`; `EstadoOrden`, `ItemOrden` e `HistorialEstadoOrden` en `ordenes`. El módulo `health` sólo tiene `router.py`

**Reglas relacionadas**: — (EA-08, sección 1.9)

### US-002 — Configuración desde el entorno sin secretos por defecto
**Como** desarrollador
**Quiero** una clase `Settings` (pydantic-settings) que lea el entorno o un `.env` no versionado
**Para** que ninguna credencial viva en el código

**Criterios de aceptación**:
- [ ] CA-1: La dirección de la base se arma con `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT` y un driver asincrónico, usando un `@computed_field`
- [ ] CA-2: La clave de firma de los tokens sale del entorno
- [ ] CA-3: Ni la clave de firma ni la contraseña de la base tienen valor por defecto en el código: si faltan, la aplicación **no arranca**
- [ ] CA-4: El repositorio incluye `env.example` con todas las variables y ningún secreto

**Reglas relacionadas**: — (sección 5.12: quien tiene la clave de firma fabrica tokens válidos para cualquier usuario; una clave inventada cambia en cada reinicio y con dos procesos cada uno rechaza los tokens del otro)

### US-003 — Ciclo de vida asincrónico
**Como** desarrollador
**Quiero** el motor y la fábrica de sesiones creados en el lifespan y guardados en `app.state`
**Para** que no se construyan al importar un módulo, antes de que exista el bucle de eventos

**Criterios de aceptación**:
- [ ] CA-1: El motor se crea en el lifespan con el tamaño del pool declarado en la configuración (sección 4.5)
- [ ] CA-2: `get_session` toma la fábrica de `app.state`, entrega una sesión por petición con `expire_on_commit=False` y la cierra al terminar
- [ ] CA-3: El lifespan calcula una vez el hash ficticio del login
- [ ] CA-4: Al apagar, el lifespan cierra el motor con `dispose()`

**Reglas relacionadas**: RN-09 (hash ficticio)

### US-004 — Salud del proceso
**Como** operador
**Quiero** distinguir «vivo» de «listo»
**Para** no reiniciar un proceso sano cuando la base es la que está caída

**Criterios de aceptación**:
- [ ] CA-1: `GET /health/live` no toca la base y responde 200
- [ ] CA-2: `GET /health/ready` ejecuta `SELECT 1` y responde 503 si la base no contesta

**Reglas relacionadas**: —

## Épica 2: Modelos, relaciones y migraciones (Ejercicio 2 — 14 %)

### US-005 — Modelo de dominio completo con restricciones
**Como** desarrollador
**Quiero** los 13 modelos con todas sus restricciones
**Para** que la base garantice la integridad

**Criterios de aceptación**:
- [ ] CA-1: Los tres índices únicos parciales (`postgresql_where`): `asignacion_rol`, patente y código
- [ ] CA-2: El estado de una orden y los del historial son claves foráneas al catálogo `estado_orden`, no un CHECK con la lista adentro (RN-19)
- [ ] CA-3: Navegación declarada en los dos extremos de cada relación que se lea; `Usuario.cliente` devuelve un objeto y no una lista

**Reglas relacionadas**: RN-01, RN-03, RN-19

### US-006 — Esquema creado sólo con Alembic
**Como** desarrollador
**Quiero** dos migraciones con la plantilla asincrónica
**Para** que el esquema esté versionado y sea reproducible

**Criterios de aceptación**:
- [ ] CA-1: No se usa `create_all`
- [ ] CA-2: Migración 1, generada con `--autogenerate`, con todas las tablas
- [ ] CA-3: Migración 2, **escrita a mano**, con el disparador de sólo agregado sobre las tres tablas (RN-15)
- [ ] CA-4: Cada migración se **lee antes de aplicarla** y lleva un comentario que lo diga
- [ ] CA-5: `alembic upgrade head` sobre base vacía, `alembic downgrade base` y otra vez `upgrade head` funcionan
- [ ] CA-6: Las migraciones crean el catálogo **vacío**; sus cuatro filas las carga `seed.py`

**Reglas relacionadas**: RN-15, RN-19

## Épica 3: Contratos y CRUD (Ejercicio 3 — 10 %)

### US-007 — Contratos separados de los modelos de tabla
**Como** cliente de la API
**Quiero** contratos de entrada y salida distintos de los modelos
**Para** que nadie pueda registrarse con un rol ni editar el stock por PATCH

**Criterios de aceptación**:
- [ ] CA-1: Los contratos de entrada rechazan los campos que no declaran (`extra="forbid"`)
- [ ] CA-2: Ninguna respuesta incluye `password_hash`
- [ ] CA-3: Los PATCH aplican sólo los campos enviados (`exclude_unset`, sección 2.6)

**Reglas relacionadas**: RN-18

### US-008 — Códigos de estado y listados paginados
**Como** cliente de la API
**Quiero** códigos consistentes y un envoltorio uniforme en los listados
**Para** poder manejar errores y paginar sin sorpresas

**Criterios de aceptación**:
- [ ] CA-1: 201 al crear, 204 al dar de baja, 404 si el recurso de la ruta no existe, 409 si choca con lo guardado, 422 si el cuerpo o los parámetros no cumplen el contrato
- [ ] CA-2: Los listados devuelven `{items, total, page, size, pages}`
- [ ] CA-3: `page` empieza en 1; `size` va de 1 a 100 (por defecto 20); pedir una página más allá de la última da 422; `total` cuenta con los **mismos filtros** que la página
- [ ] CA-4: Con cero resultados hay una página, vacía
- [ ] CA-5: La búsqueda de repuestos por descripción (`q`) usa **parámetros ligados** (nunca concatenación)

**Reglas relacionadas**: RN-18

## Épica 4: Autenticación (Ejercicio 4 — 16 %)

### US-009 — Hash de contraseñas con bcrypt sin frenar el servidor
**Como** administrador del sistema
**Quiero** que las contraseñas se guarden hasheadas y que el costo sea configurable
**Para** que el hash no frene el bucle de eventos ni quede fijo en el código

**Criterios de aceptación**:
- [ ] CA-1: Costo declarado en la configuración, no fijo en el código (se sube con los años — secciones 5.4 y 5.12)
- [ ] CA-2: Toda llamada a bcrypt corre **fuera del bucle de eventos** (`to_thread`) y bajo un **semáforo** que limita cuántas corren a la vez (sección 5.6)
- [ ] CA-3: El hash se calcula **antes** de abrir la transacción (dentro, la conexión quedaría tomada los ~300 ms de bcrypt sin usar la base)
- [ ] CA-4: Todo campo que termina en bcrypt (la del registro, la del login, la actual y la nueva del cambio) acepta **máximo 72 bytes**; es bytes y no caracteres (una «ñ» ocupa dos). Sin el límite en el contrato, una contraseña larga daría 500 en lugar de 422 (bcrypt ≥ 5 rechaza con excepción)

**Reglas relacionadas**: RN-09

### US-010 — Login con límite de intentos y respuesta uniforme
**Como** atacante frustrado / usuario legítimo
**Quiero** que el login frene la fuerza bruta y no revele cuentas
**Para** que el sistema no filtre ni el listado de correos ni su tiempo de respuesta

**Criterios de aceptación**:
- [ ] CA-1: Orden del login (sección 5.5): primero el límite de intentos (RN-08); después la verificación, contra el hash del usuario o contra un hash ficticio si el correo no existe (RN-09)
- [ ] CA-2: 5 fallos fallidos con el mismo correo desde la misma IP en 60 s → 429 con `Retry-After`, sin calcular ningún hash
- [ ] CA-3: Un login correcto reinicia la cuenta
- [ ] CA-4: Mismo cuerpo y duración parecida exista o no el correo

**Reglas relacionadas**: RN-08, RN-09

### US-011 — Token en cookie HttpOnly
**Como** cliente web
**Quiero** que el token viaje sólo en una cookie protegida
**Para** que un script de terceros no pueda leerlo

**Criterios de aceptación**:
- [ ] CA-1: JWT firmado con `sub`, `iat`, `exp` y los roles vigentes al emitirlo (sección 5.3)
- [ ] CA-2: Cookie `access_token` con `HttpOnly`, `SameSite=Lax`, `Max-Age` igual a la duración del token y `Secure` configurable
- [ ] CA-3: El cuerpo del login **no** trae el token; la dependencia lo lee de `request.cookies`
- [ ] CA-4: `Authorization: Bearer` no sirve (caso C-03: sin cookie o con Bearer, 401)

**Reglas relacionadas**: RN-07

### US-012 — Registro, logout y /auth/yo
**Como** cliente
**Quiero** registrarme, cerrar sesión y ver quién soy
**Para** operar en el taller

**Criterios de aceptación**:
- [ ] CA-1: El registro crea usuario + rol CLIENTE + ficha de cliente en un solo UoW (RN-02); documento repetido → 409 sin apropiarse de la ficha
- [ ] CA-2: El logout borra la cookie (200)
- [ ] CA-3: `GET /auth/yo` devuelve el usuario, sus **roles vigentes** y los que dice el token

**Reglas relacionadas**: RN-02, RN-07

## Épica 5: Autorización (Ejercicio 5 — 14 %)

### US-013 — Sesión válida (401) vs permiso (403)
**Como** cliente de la API
**Quiero** que el sistema distinga siempre entre «no estás identificado» y «no podés»
**Para** depurar accesos sin ambigüedad

**Criterios de aceptación**:
- [ ] CA-1: `get_usuario_actual` responde 401 si: no hay cookie, el token es inválido o venció, el usuario no existe o está inactivo, o el token es **anterior** al último cambio de contraseña (RN-07)
- [ ] CA-2: `requiere_rol` responde 403 y consulta los roles vigentes **en la base en cada petición** (RN-04)

**Reglas relacionadas**: RN-04, RN-07

### US-014 — Gestión de roles con vigencia
**Como** administrador
**Quiero** asignar roles con vencimiento opcional y revocarlos sin borrar la fila
**Para** que el historial de quién tuvo qué rol y hasta cuándo quede registrado

**Criterios de aceptación**:
- [ ] CA-1: Asignar con `desde`/`vence_en` opcional; revocar escribe `revocada_en`; la fila no se borra
- [ ] CA-2: Reasignar un rol **vencido** cierra la fila anterior y abre una nueva
- [ ] CA-3: El vencimiento llega con **zona horaria** y en el **futuro**: sin zona o en el pasado → 422 (no 409)
- [ ] CA-4: Se cumple la autoprotección (RN-05): 409 al revocarse el propio ADMIN

**Reglas relacionadas**: RN-03, RN-05

### US-015 — Cambio obligatorio de contraseña
**Como** administrador
**Quiero** que un usuario con contraseña provisoria no pueda operar hasta cambiarla
**Para** que nadie quede trabado con la clave que le dio el admin

**Criterios de aceptación**:
- [ ] CA-1: Dos grupos de rutas en `main.py` —uno abierto y uno protegido— con el control montado **una sola vez** (FastAPI suma dependencias y no las resta — sección 5.10)
- [ ] CA-2: Bloqueado (403) salvo `/auth` y salud (RN-06)
- [ ] CA-3: Después del cambio, la cookie **nueva** vale y la **anterior** da 401, sin esperar entre el login y el cambio (RN-07, iat sin truncar)

**Reglas relacionadas**: RN-06, RN-07

### US-016 — Historial de seguridad
**Como** administrador
**Quiero** un registro de altas, cambios de rol y de contraseña, y de los datos iniciales
**Para** auditar quién hizo qué

**Criterios de aceptación**:
- [ ] CA-1: `evento_seguridad` con `actor` texto (incluye `'SISTEMA'`, que no es un usuario — sección 5.8)
- [ ] CA-2: `GET /eventos` con paginación, sólo ADMIN

**Reglas relacionadas**: —

## Épica 6: Clientes, vehículos y lo propio (módulo clientes)

### US-017 — Alta de clientes y vehículos
**Como** recepción
**Quiero** dar de alta clientes y sus vehículos
**Para** abrir órdenes sobre vehículos reales

**Criterios de aceptación**:
- [ ] CA-1: `POST /clientes` (RECEPCION, ADMIN): 201/409/422; documento único
- [ ] CA-2: `GET /clientes/{id}` devuelve la ficha **con sus vehículos** (carga anticipada)
- [ ] CA-3: `POST /clientes/{id}/vehiculos`: 201/404/409/422; patente única entre vigentes; `anio` 1950–2100

**Reglas relacionadas**: RN-01

### US-018 — Baja lógica de vehículos
**Como** recepción
**Quiero** dar de baja un vehículo sin borrar sus órdenes viejas
**Para** que el comprador pueda registrar la misma patente

**Criterios de aceptación**:
- [ ] CA-1: `DELETE /vehiculos/{id}` → 204; la fila queda con `borrado_en`
- [ ] CA-2: Un vehículo con órdenes **abiertas** (`es_final = false`) no se da de baja: 409
- [ ] CA-3: Registrarse con la misma patente de un baja → 201 (caso C-19); una segunda patente **vigente** igual → 409

**Reglas relacionadas**: RN-16

### US-019 — Lo propio del cliente
**Como** cliente
**Quiero** ver mis vehículos y mis órdenes, y cancelar las mías
**Para** seguir mi reparación sin ver lo ajeno

**Criterios de aceptación**:
- [ ] CA-1: `GET /mis-vehiculos` y `GET /mis-ordenes` sólo piden estar autenticados (RN-17)
- [ ] CA-2: Un cliente ve su orden (200) y no la ajena (403) — caso C-06
- [ ] CA-3: Puede cancelar **sus** órdenes PENDIENTE (200); una ajena → 403; una terminada → 409 (caso C-13)

**Reglas relacionadas**: RN-12, RN-17

## Épica 7: Repuestos y stock (módulo repuestos)

### US-020 — Catálogo de repuestos
**Como** personal del taller
**Quiero** consultar y buscar repuestos por descripción
**Para** cotizar y abrir órdenes

**Criterios de aceptación**:
- [ ] CA-1: `GET /repuestos` (`q`, `page`, `size`) para ADMIN, RECEPCION y MECANICO
- [ ] CA-2: Búsqueda con parámetros ligados; `' OR '1'='1` devuelve lista vacía con `total: 0` (caso C-16)
- [ ] CA-3: `GET /repuestos/{id}`: 200/404

**Reglas relacionadas**: RN-18

### US-021 — ABM de repuestos (sólo ADMIN)
**Como** administrador
**Quiero** crear, editar y dar de baja repuestos
**Para** mantener el catálogo al día

**Criterios de aceptación**:
- [ ] CA-1: `POST /repuestos` con `stock_inicial`: 201; el stock inicial deja un movimiento «Stock inicial»
- [ ] CA-2: `PATCH /repuestos/{id}` sólo descripción y precio: sólo cambia lo enviado (`exclude_unset`)
- [ ] CA-3: `DELETE /repuestos/{id}` → 204 (borrado lógico); no usable en órdenes nuevas
- [ ] CA-4: El stock **no** es editable por PATCH: 422 (caso C-16)

**Reglas relacionadas**: RN-14, RN-16

### US-022 — Reposición e historiales de stock y precios
**Como** administrador
**Quiero** reponer stock y auditar movimientos y cambios de precio
**Para** explicar cada baja y cada alza

**Criterios de aceptación**:
- [ ] CA-1: `POST /repuestos/{id}/reponer`: 200; deja un movimiento
- [ ] CA-2: `GET /repuestos/{id}/movimientos` y `GET /repuestos/{id}/precios`: 200/404
- [ ] CA-3: Cambiar el precio deja **una línea** en el historial con el anterior y el nuevo; un PATCH posterior que no cambia el precio **no** agrega línea (caso C-18); la recepción recibe 403 en esos endpoints
- [ ] CA-4: Las tres tablas de auditoría rechazan UPDATE/DELETE (caso C-14)

**Reglas relacionadas**: RN-14, RN-15, RN-20

## Épica 8: Órdenes de trabajo (módulo ordenes)

### US-023 — Alta de una orden
**Como** recepción
**Quiero** abrir una orden con la falla y los repuestos a usar
**Para** que el mecánico sepa qué reparar

**Criterios de aceptación**:
- [ ] CA-1: `POST /ordenes` (RECEPCION, ADMIN): nace PENDIENTE, con al menos un ítem, sin repuestos repetidos
- [ ] CA-2: El precio de cada ítem se copia del repuesto; el total lo calcula el servidor; no viajan en el cuerpo
- [ ] CA-3: 201 con los precios, el total y la primera línea del historial; con un repuesto inexistente → 409 y la orden **no queda creada** (caso C-10)

**Reglas relacionadas**: RN-10, RN-19

### US-024 — Transiciones de la orden
**Como** mecánico / recepción / administrador / dueño
**Quiero** avanzar la orden por su máquina de estados
**Para** que el estado refleje la realidad del taller

**Criterios de aceptación**:
- [ ] CA-1: `POST /ordenes/{id}/iniciar` (MECANICO): PENDIENTE → EN_REPARACION, el mecánico queda asignado
- [ ] CA-2: `POST /ordenes/{id}/terminar` (mecánico asignado o ADMIN): EN_REPARACION → TERMINADA, descuenta stock, deja movimientos e historial; si no alcanza el stock → 409 sin escrituras (caso C-11)
- [ ] CA-3: `POST /ordenes/{id}/cancelar` (RECEPCION, ADMIN o dueño): PENDIENTE → CANCELADA; el permiso se evalúa antes que el estado (403 antes que 409)
- [ ] CA-4: Filtrar `GET /ordenes` por un estado que el contrato no declara → 422 (caso C-17)

**Reglas relacionadas**: RN-11, RN-12, RN-13

### US-025 — Detalle de la orden sin N+1
**Como** cliente de la API
**Quiero** el detalle completo con un número fijo de consultas
**Para** que el rendimiento no dependa de la cantidad de ítems

**Criterios de aceptación**:
- [ ] CA-1: El detalle —vehículo, cliente, ítems, el repuesto de cada ítem y el historial— se resuelve con un número **fijo** de consultas, que **no crece** con la cantidad de ítems (sección 4.6; caso C-15: 2 y 4 ítems, mismas consultas en la consola)
- [ ] CA-2: Ninguna lectura depende de la carga perezosa (sección 3.8): la precarga se declara en el repositorio que la necesita (sección 6.5)
- [ ] CA-3: `GET /estados-orden` devuelve el catálogo por posición, con TERMINADA y CANCELADA finales (caso C-17)

**Reglas relacionadas**: RN-19

### US-026 — Aviso al cliente en segundo plano
**Como** taller
**Quiero** avisarle al cliente cuando termina su orden
**Para** que retire el vehículo

**Criterios de aceptación**:
- [ ] CA-1: Al terminar, se agenda con `BackgroundTasks` un aviso **simulado** con `await asyncio.sleep(0.5)` y un mensaje en el registro (sección 3.9)
- [ ] CA-2: Corre **después** de enviar la respuesta y **sólo si** la operación se confirmó (caso C-12)
- [ ] CA-3: Todos los handlers son `async def` y ninguno ejecuta una llamada bloqueante (sección 3.6)

**Reglas relacionadas**: — (fuera de alcance: colas con Redis — capítulo 8)
