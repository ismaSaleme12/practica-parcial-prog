# Arquitectura Propuesta

## Patrones aplicados

| Patrón | Dónde se usa | Por qué |
|---|---|---|
| **Arquitectura en capas** (Router → Service → UoW → Repository → Model) | Todos los módulos | Cada capa sabe lo suyo y nada más (objetivo 1 del TP) |
| **Unit of Work** | `app/core/unit_of_work.py` + `app/modules/<módulo>/unit_of_work.py` | Agrupa las escrituras de una operación de negocio en una transacción: confirma o revierte al salir del bloque (RN-02, RN-13, RN-20) |
| **Repository** (con jerarquía) | `app/core/repository.py` | `BaseRepository[T]` + `SoftDeleteRepository[T]`; los repositorios hacen `flush()`, nunca `commit()` — **ningún repositorio confirma** |
| **Soft delete** (borrado lógico) | `vehiculo`, `repuesto` | La fila dada de baja se conserva; la unicidad es sólo entre los vigentes (índice único parcial con `WHERE borrado_en IS NULL`) |
| **Catálogo / tabla de referencia** | `estado_orden` | Lista fija de estados apuntada con clave foránea; cada estado lleva datos propios (`es_final`, `posicion`) que la API muestra y las consultas cruzan |
| **Append-only / audit log** | `historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto` | Protegidas por disparador instalado por migración escrita a mano (RN-15) |
| **DTO / contratos separados** | `app/modules/<módulo>/schemas.py` | Los contratos de entrada rechazan campos no declarados (`extra="forbid"`); ninguna respuesta incluye `password_hash`; el precio y el total nunca viajan en el cuerpo |
| **Envoltorio de paginación** | `app/core/paginacion.py` | `{items, total, page, size, pages}` uniforme en todos los listados |
| **Dependencias de FastAPI** | `app/core/dependencies.py` | `get_usuario_actual`, roles vigentes, control del cambio obligatorio y `requiere_rol`; el UoW se construye con una dependencia y se pasa al servicio sin abrirlo |
| **BackgroundTasks** (fire-and-forget en proceso) | Aviso al terminar orden | Simulado; fuera de alcance las colas con Redis (capítulo 8) |

## Estructura de directorios (obligatoria)

```
proyecto/
├── main.py                     # Aplicación, lifespan y los dos grupos de rutas
├── seed.py                     # Deja la base en el estado inicial conocido
├── alembic.ini
├── env.example                 # Todas las variables, ningún secreto
├── requirements.txt
├── .env                        # NO se versiona
├── app/
│   ├── core/
│   │   ├── config.py           # Settings con pydantic-settings
│   │   ├── database.py         # Motor y fábrica de sesiones (las llama el lifespan), get_session
│   │   ├── security.py         # Hash con bcrypt fuera del bucle; emisión y verificación del token
│   │   ├── dependencies.py     # Usuario actual, roles vigentes, cambio obligatorio, requiere_rol
│   │   ├── repository.py       # BaseRepository[T] y SoftDeleteRepository[T]
│   │   ├── paginacion.py       # Envoltorio de listados y cálculo de páginas
│   │   └── unit_of_work.py     # UnitOfWork base: confirma o revierte al salir del bloque
│   └── modules/
│       ├── health/
│       │   └── router.py       # Sólo router: /health/live y /health/ready
│       ├── usuarios/
│       │   ├── models.py       # usuario, asignacion_rol, intento_acceso, evento_seguridad
│       │   ├── schemas.py
│       │   ├── repository.py
│       │   ├── unit_of_work.py
│       │   ├── service.py
│       │   └── router.py
│       ├── clientes/
│       │   ├── models.py       # cliente, vehiculo
│       │   ├── schemas.py
│       │   ├── repository.py
│       │   ├── unit_of_work.py
│       │   ├── service.py
│       │   └── router.py
│       ├── repuestos/
│       │   ├── models.py       # repuesto, movimiento_stock, historial_precio_repuesto
│       │   ├── schemas.py
│       │   ├── repository.py
│       │   ├── unit_of_work.py
│       │   ├── service.py
│       │   └── router.py
│       └── ordenes/
│           ├── models.py       # orden_trabajo, item_orden, estado_orden, historial_estado_orden
│           ├── schemas.py
│           ├── repository.py
│           ├── unit_of_work.py
│           ├── service.py
│           └── router.py
├── migrations/                 # Configuración de Alembic y sus versiones
│   └── versions/
│       ├── <autogenerate>_init.py      # Todas las tablas (generada)
│       └── <manual>_append_only.py     # Disparador de sólo agregado (escrita a mano)
└── test/
    ├── *.http                  # Casos C-01 a C-19 con la respuesta esperada en comentarios
    └── solo_agregado.sql       # Caso C-14 (psql)
```

Notas de la estructura:
- **Módulos mínimos**: `health`, `usuarios`, `clientes`, `repuestos`, `ordenes`.
- `AsignacionRol`, `IntentoAcceso` y `EventoSeguridad` viven en `usuarios`; `Vehiculo` en `clientes`; `MovimientoStock` y `HistorialPrecio` en `repuestos`; `EstadoOrden`, `ItemOrden` e `HistorialEstadoOrden` en `ordenes`.
- El módulo `health` **sólo** tiene `router.py` (no tiene modelo ni persistencia propia).

## Seguridad

- **Autenticación**: contraseñas con **bcrypt** (costo configurable en `Settings`), hash calculado **fuera del bucle de eventos** (`asyncio.to_thread`) y bajo un **semáforo** que limita cuántas corridas simultáneas; el hash se calcula **antes** de abrir la transacción. Todo campo que termina en bcrypt acepta **máximo 72 bytes** (bytes, no caracteres), validado en el contrato (422, no 500).
- **Token**: JWT firmado (PyJWT) con `sub`, `iat`, `exp` y los roles vigentes al emitirlo. Viaja **sólo** en la cookie `access_token` con `HttpOnly`, `SameSite=Lax`, `Max-Age` = duración del token y `Secure` configurable. **Nunca** en el cuerpo ni leído de la cabecera `Authorization`. La clave de firma sale del entorno, **sin default**: quien la tenga fabrica tokens válidos para cualquier usuario.
- **Autorización**: los roles se deciden consultando `asignacion_rol` **en la base, en cada petición** (`requiere_rol`); el token es informativo. Revocar un rol surte efecto inmediato. 401 = sin sesión inválida; 403 = sin permiso. El cambio obligatorio se resuelve con **dos grupos de rutas** en `main.py` (abierto y protegido) con el control montado una sola vez.
- **Validación de input**: contratos Pydantic con `extra="forbid"`; `exclude_unset` en PATCH; paginación acotada (`size` 1–100); búsquedas con **parámetros ligados** (nunca concatenación de SQL con datos del usuario).
- **Errores**: mensajes propios; **nunca** el texto de la base ni una traza; ninguna entrada inválida termina en un 500 (RN-18: traducción del `IntegrityError` a 409).
- **Secrets management**: ninguna contraseña ni clave de firma en el código —tampoco como valor por defecto—, ni en `alembic.ini`, ni en el repositorio. `env.example` documenta las variables sin valores reales. `.env` no se sube.
- **Diagnóstico**: las consultas se pueden ver en la consola (`SQL_ECHO=true` o equivalente).

## Variables de entorno

| Variable | Descripción | Ejemplo | Sensible |
|---|---|---|---|
| `POSTGRES_USER` | Usuario de la base | `taller` | No |
| `POSTGRES_PASSWORD` | Contraseña de la base — **sin default**; si falta, la app no arranca | — | **Y** |
| `POSTGRES_DB` | Nombre de la base | `taller` | No |
| `POSTGRES_HOST` | Host de la base | `localhost` | No |
| `POSTGRES_PORT` | Puerto de la base | `5432` | No |
| `DATABASE_URL` (o el `@computed_field` que la arma) | URL completa con driver asincrónico | `postgresql+asyncpg://...` | Depende |
| `SECRET_KEY` (o el nombre elegido para la clave de firma) | Clave de firma del JWT — **sin default**; si falta, la app no arranca | — | **Y** |
| `BCRYPT_ROUNDS` (costo) | Costo del hash bcrypt, declarado en configuración | `12` | No |
| Duración del token (p. ej. `ACCESS_TOKEN_EXPIRE_MINUTES`) | Usada para `exp` y para el `Max-Age` de la cookie | `30` | No |
| `COOKIE_SECURE` | Si la cookie es `Secure` | `false` en dev / `true` en prod | No |
| `SQL_ECHO` | Muestra las consultas en consola | `true` en dev | No |

La dirección de la base se arma con las variables sueltas + un `@computed_field`; el driver es asincrónico (`postgresql+asyncpg` o `postgresql+psycopg`). El repositorio incluye **`env.example`** con todas las variables y ningún secreto.

## Requisitos no funcionales (tabla de la consigna)

| Requisito | Detalle |
|---|---|
| Asincronía | Todos los handlers con `async def`; bcrypt siempre fuera del bucle |
| Credenciales | Ninguna contraseña ni clave de firma en el código —tampoco como valor por defecto—, en `alembic.ini` ni en el repositorio |
| Token | Sólo en la cookie HttpOnly; nunca en el cuerpo ni leído de la cabecera Authorization |
| Esquema | Sólo con Alembic; la aplicación no usa `create_all` |
| Transacciones | Ningún repositorio confirma; ningún servicio construye su Unit of Work; el Unit of Work no cierra la sesión |
| Carga perezosa | Prohibida: toda relación que se lee se precarga en el repositorio |
| SQL | Nunca armado por concatenación con datos del usuario |
| Errores | Mensajes propios; nunca el texto de la base ni una traza; ninguna entrada inválida termina en un 500 |
| Unicidad | Garantizada por la base; no se verifica con una consulta previa |
| Diagnóstico | Las consultas se pueden ver en la consola (`SQL_ECHO=true` o equivalente) |
