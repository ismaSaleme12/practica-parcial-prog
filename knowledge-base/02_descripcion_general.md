# Descripción General

## Stack tecnológico

| Capa | Tecnologías | Versión mínima |
|---|---|---|
| Lenguaje | Python | 3.12 |
| Framework web | FastAPI (todos los handlers con `async def`) | 0.111 |
| Modelos de tabla | SQLModel | 0.0.24 |
| Motor / sesión / carga anticipada | SQLAlchemy 2.0, **asincrónico** | 2.0 |
| Controlador de BD | asyncpg (asincrónico). Se acepta psycopg 3 asincrónico (el del capítulo 4) | 0.30 |
| Base de datos | PostgreSQL | 16 |
| Migraciones | Alembic, **plantilla asincrónica** | 1.13 |
| Configuración | pydantic-settings (clase `Settings` desde el entorno o `.env`) | 2.0 |
| Hash de contraseñas | bcrypt | 4.0 |
| Token firmado | PyJWT | 2.8 |
| Servidor ASGI | uvicorn (lo instala `fastapi[standard]`) | el que instala |

## Arquitectura general

API REST **en capas**, con un flujo de una sola dirección por petición:

```
HTTP → router.py → service.py → unit_of_work.py → repository.py → model (tabla)
         ↑              ↑              ↑                 ↑
      traduce       reglas de     abre/confirma/     precarga
      errores       negocio       revierte           y flush
```

- **Router** (`app/modules/<módulo>/router.py`): construye el Unit of Work con una dependencia, lo pasa al servicio **sin abrirlo** y traduce errores a códigos HTTP.
- **Service** (`app/modules/<módulo>/service.py`): contiene las reglas de negocio. Abre el Unit of Work con `async with` y **nunca lo construye**.
- **Unit of Work** (`app/modules/<módulo>/unit_of_work.py` + base en `app/core/unit_of_work.py`): gestor de contexto asincrónico que confirma al salir del bloque, revierte si se sale con una excepción y **no cierra la sesión** (no la creó). Compone los repositorios que las operaciones del módulo necesitan, todos con la misma sesión.
- **Repository** (`app/core/repository.py` + `app/modules/<módulo>/repository.py`): `BaseRepository[T]` (recibe sesión y clase del modelo en el constructor) y `SoftDeleteRepository[T]` (hereda, filtra dados de baja, agrega `get_by_id_including_deleted` y `soft_delete`). `add` y `update` hacen `flush()`, **nunca** `commit()`: ningún repositorio confirma.
- **Model** (`app/modules/<módulo>/models.py`): modelos de tabla con restricciones y relaciones (navegación declarada en los dos extremos de cada relación que se lea).

Ciclo de vida: el motor asincrónico (con tamaño de pool declarado en la configuración) y la fábrica de sesiones se crean **en el lifespan** y se guardan en `app.state` —no al importar un módulo (EA-08, sección 1.9)—. `get_session` toma la fábrica de `app.state`, entrega una sesión por petición con `expire_on_commit=False` y la cierra al terminar. El lifespan calcula además, una vez, el hash ficticio del login; al apagar cierra el motor con `dispose()`.

## Integraciones externas

| Servicio | Propósito | Tipo |
|---|---|---|
| PostgreSQL 16 | Base de datos relacional (único sistema externo) | driver asincrónico (`postgresql+asyncpg` o `postgresql+psycopg`) |
| SMTP / proveedor de SMS / colas | — | **No hay**: el aviso al cliente es simulado con `await asyncio.sleep(0.5)` + log, vía `BackgroundTasks` |

No hay integraciones con APIs de terceros, pasarelas de pago ni servicios cloud. La única dependencia externa es la base de datos.

## API REST

La API se organiza en **dos grupos de rutas** definidos en `main.py` (porque FastAPI suma dependencias y no las resta — sección 5.10):

- **Grupo abierto**: no exige cookie de sesión. Incluye salud, registro, login, logout, `/auth/yo` y cambio de contraseña.
- **Grupo protegido**: exige sesión válida. Toda ruta de este grupo responde además **401 sin sesión** y **403 con el cambio de contraseña pendiente**.

### Endpoints de referencia

| Grupo | Método | Ruta | Quién | Códigos |
|---|---|---|---|---|
| Abierto | GET | `/health/live` | Cualquiera | 200 |
| Abierto | GET | `/health/ready` | Cualquiera | 200, 503 |
| Abierto | POST | `/auth/registro` | Cualquiera | 201, 409, 422 |
| Abierto | POST | `/auth/login` | Cualquiera | 200, 401, 422, 429 |
| Abierto | POST | `/auth/logout` | Cualquiera | 200 |
| Abierto | GET | `/auth/yo` | Autenticado | 200, 401 |
| Abierto | POST | `/auth/cambiar-password` | Autenticado | 200, 401, 422 |
| Protegido | POST | `/usuarios` (alta de personal, con contraseña provisoria) | ADMIN | 201, 409, 422 |
| Protegido | GET | `/usuarios/{id}/roles` | ADMIN | 200, 404 |
| Protegido | POST | `/usuarios/{id}/roles` | ADMIN | 201, 404, 409, 422 |
| Protegido | DELETE | `/usuarios/{id}/roles/{rol}` | ADMIN | 200, 404, 409 |
| Protegido | GET | `/eventos` (`page`, `size`) | ADMIN | 200, 422 |
| Protegido | POST | `/clientes` | RECEPCION, ADMIN | 201, 409, 422 |
| Protegido | GET | `/clientes/{id}` (con sus vehículos) | RECEPCION, ADMIN | 200, 404 |
| Protegido | POST | `/clientes/{id}/vehiculos` | RECEPCION, ADMIN | 201, 404, 409, 422 |
| Protegido | DELETE | `/vehiculos/{id}` | RECEPCION, ADMIN | 204, 404, 409 |
| Protegido | GET | `/mis-vehiculos` | Autenticado | 200 |
| Protegido | GET | `/repuestos` (`q`, `page`, `size`) | ADMIN, RECEPCION, MECANICO | 200, 422 |
| Protegido | GET | `/repuestos/{id}` | ADMIN, RECEPCION, MECANICO | 200, 404 |
| Protegido | POST | `/repuestos` (con `stock_inicial`) | ADMIN | 201, 409, 422 |
| Protegido | PATCH | `/repuestos/{id}` (descripción y precio) | ADMIN | 200, 404, 422 |
| Protegido | DELETE | `/repuestos/{id}` | ADMIN | 204, 404 |
| Protegido | POST | `/repuestos/{id}/reponer` | ADMIN | 200, 404, 422 |
| Protegido | GET | `/repuestos/{id}/movimientos` | ADMIN | 200, 404 |
| Protegido | GET | `/repuestos/{id}/precios` (historial de precios) | ADMIN | 200, 404 |
| Protegido | POST | `/ordenes` | RECEPCION, ADMIN | 201, 409, 422 |
| Protegido | GET | `/ordenes` (`estado`, `page`, `size`) | ADMIN, RECEPCION, MECANICO | 200, 422 |
| Protegido | GET | `/ordenes/{id}` | El personal, o el dueño del vehículo | 200, 403, 404 |
| Protegido | POST | `/ordenes/{id}/iniciar` | MECANICO | 200, 404, 409 |
| Protegido | POST | `/ordenes/{id}/terminar` | El mecánico asignado, o ADMIN | 200, 403, 404, 409 |
| Protegido | POST | `/ordenes/{id}/cancelar` | RECEPCION, ADMIN o el dueño | 200, 403, 404, 409 |
| Protegido | GET | `/estados-orden` (el catálogo, por posición) | Autenticado | 200 |
| Protegido | GET | `/mis-ordenes` (`page`, `size`) | Autenticado | 200, 422 |

La ruta de cancelar **no** lleva `requiere_rol`: el dueño de un vehículo puede cancelar su orden y no tiene rol de personal; la decisión (403 por identidad/relación vs 409 por estado) la toma el servicio.

### Ejemplos de contrato (de la consigna)

**POST /ordenes** — viajan el id del vehículo y los datos de cada ítem; no viajan precio, total, estado ni fecha:

```json
{
  "vehiculo_id": 2,
  "falla": "Ruido al frenar",
  "items": [
    { "repuesto_id": 2, "cantidad": 1 },
    { "repuesto_id": 4, "cantidad": 3 }
  ]
}
```

Respuesta (precio copiado del repuesto, total calculado, primera línea del historial):

```json
{
  "id": 3,
  "estado": "PENDIENTE",
  "patente": "AC456EF",
  "total": "68000.00",
  "creada_en": "2026-10-23T02:18:54.332849Z",
  "mecanico_id": null,
  "falla": "Ruido al frenar",
  "cliente": "Laura Cliente",
  "items": [
    { "repuesto_id": 2, "codigo": "FRE-010", "descripcion": "Pastillas de freno delanteras",
      "cantidad": 1, "precio_unitario": "32000.00", "subtotal": "32000.00" },
    { "repuesto_id": 4, "codigo": "ACE-530", "descripcion": "Aceite 5W30 por litro",
      "cantidad": 3, "precio_unitario": "12000.00", "subtotal": "36000.00" }
  ],
  "historial": [
    { "desde_estado": null, "hasta_estado": "PENDIENTE", "usuario_id": 3,
      "cuando": "2026-10-23T02:18:54.366899Z" }
  ]
}
```

**POST /auth/login** — la respuesta no trae el token: viaja en `Set-Cookie`:

```json
{ "mensaje": "Sesión iniciada", "debe_cambiar_password": false, "expira_en_segundos": 1800 }
```

**Listado paginado** (`GET /repuestos?size=2`):

```json
{
  "items": [
    { "id": 1, "codigo": "FIL-001", "descripcion": "Filtro de aceite", "precio": "8500.00", "stock": 10 },
    { "id": 2, "codigo": "FRE-010", "descripcion": "Pastillas de freno delanteras", "precio": "32000.00", "stock": 4 }
  ],
  "total": 4,
  "page": 1,
  "size": 2,
  "pages": 2
}
```

Con `page=3` respondería 422: «La página 3 no existe: hay 2».
