# API Taller Mecánico

API REST asincrónica para la gestión diaria de un taller mecánico: **clientes, vehículos, órdenes de trabajo y stock de repuestos**, con autenticación por cookie `HttpOnly` y autorización por roles decidida en la base de datos en cada petición.

Es el trabajo práctico integrador de las unidades 1 a 6 de **Programación III** («del objeto a la transacción»). El alcance es el backend: no hay frontend propio en el repositorio; la web del taller sería un cliente externo que consume esta API.

> Documento **vivo**: la sección [Estado del proyecto](#estado-del-proyecto) y el contador de pruebas se actualizan al cerrar cada change (ver la nota al pie de esa sección).

---

## Índice

1. [Descripción](#descripción)
2. [Estado del proyecto](#estado-del-proyecto)
3. [Stack tecnológico](#stack-tecnológico)
4. [Arquitectura](#arquitectura)
5. [Estructura de directorios](#estructura-de-directorios)
6. [Puesta en marcha](#puesta-en-marcha)
7. [Variables de entorno](#variables-de-entorno)
8. [Autenticación y autorización](#autenticación-y-autorización)
9. [Endpoints](#endpoints)
10. [Modelo de datos](#modelo-de-datos)
11. [Migraciones](#migraciones)
12. [Datos iniciales (seed)](#datos-iniciales-seed)
13. [Pruebas](#pruebas)
14. [Flujo de trabajo del proyecto](#flujo-de-trabajo-del-proyecto)
15. [Documentación](#documentación)
16. [Limitaciones y deuda conocida](#limitaciones-y-deuda-conocida)

---

## Descripción

El sistema modela el circuito completo del taller:

- **Recepción** da de alta clientes y vehículos y abre una orden por cada ingreso, con la falla y los repuestos a usar.
- **Mecánico** toma (inicia) la orden, la repara y la da por terminada; al terminarla se descuenta el stock de cada repuesto usado.
- **Administrador** mantiene el catálogo de repuestos, repone stock, cambia precios con historial y administra personal y roles.
- **Cliente** se auto-registra y consulta el estado de sus vehículos y sus órdenes.
- **Sistema** registra eventos de seguridad con el actor `'SISTEMA'`.

La integridad se delega a PostgreSQL: claves foráneas, `CHECK`, índices únicos parciales para el borrado lógico y los roles vigentes, un catálogo de estados y un disparador de **sólo agregado** sobre tres tablas de auditoría.

**Estado actual:** los changes `C-01` a `C-08` están implementados y archivados (proyecto, persistencia, modelos, migraciones, tests, contratos, autenticación y RBAC). El dominio del taller (`C-09` a `C-13`: clientes/vehículos, repuestos/stock, órdenes y lectura sin N+1) está pendiente.

---

## Estado del proyecto

<!-- ACTUALIZAR AL ARCHIVAR UN CHANGE: marcar la fila como completada, ajustar el contador de pruebas y mover el change de pending a openspec/changes/archive/. -->

**Changes completados: 8 de 13.** **Suite: 64 pruebas en verde** (`python -m pytest test/ -q` contra PostgreSQL real).

| ID | Change | Estado | Fase |
|---|---|---|---|
| C-01 | `foundation-setup` | ✓ completado | 0 — Cimientos |
| C-02 | `core-persistence` | ✓ completado | 0 — Cimientos |
| C-03 | `domain-models` | ✓ completado | 1 — Modelo y esquema |
| C-04 | `migrations-and-seed` | ✓ completado | 1 — Modelo y esquema |
| C-05 | `test-infrastructure` | ✓ completado | 2 — Andén de pruebas |
| C-06 | `contracts-and-errors` | ✓ completado | 3 — Contratos |
| C-07 | `auth` | ✓ completado | 3 — Autenticación |
| C-08 | `authorization-rbac` | ✓ completado | 4 — Autorización |
| C-09 | `clientes-vehiculos` | ☐ pendiente | 5 — Dominio del taller |
| C-10 | `repuestos-stock` | ☐ pendiente | 5 — Dominio del taller |
| C-11 | `ordenes-trabajo` | ☐ pendiente | 5 — Dominio del taller |
| C-12 | `detalle-sin-n1` | ☐ pendiente | 6 — Calidad de lectura |
| C-13 | `casos-de-prueba` | ☐ pendiente | 6 — Entrega |

Los ocho changes completados están archivados en `openspec/changes/archive/`; las capacidades especificadas viven en `openspec/specs/`.

> **Cómo actualizar esta sección** (obligatorio al archivar un change): (1) marcar la fila con ✓, (2) actualizar el contador de changes y el de pruebas con el resultado real de `python -m pytest test/ -q`, (3) mover el directorio del change de `openspec/changes/` a `openspec/changes/archive/`, (4) marcar el `[x]` en `CHANGES.md`. No se actualiza «a ojo»: el contador sale de la corrida de la suite.

---

## Stack tecnológico

Tomado de `requirements.txt`, `knowledge-base/02_descripcion_general.md` y `app/core/config.py`.

| Capa | Tecnología | Versión mínima |
|---|---|---|
| Lenguaje | Python | 3.12 |
| Framework web | FastAPI (todos los handlers `async def`) | `fastapi[standard]>=0.111.0` |
| Modelos de tabla | SQLModel | `>=0.0.24` |
| ORM / motor | SQLAlchemy 2.0 asincrónico (`sqlalchemy[asyncio]`) | `>=2.0.0` |
| Driver | asyncpg | `>=0.30.0` |
| Base de datos | PostgreSQL | 16 |
| Migraciones | Alembic (plantilla asincrónica) | `>=1.13.0` |
| Configuración | pydantic-settings | `>=2.0.0` |
| Hash de contraseñas | bcrypt | `>=4.0.0` |
| Token firmado | PyJWT (HS256) | `>=2.8.0` |
| Servidor ASGI | uvicorn (lo instala `fastapi[standard]`) | el que instale el extra |
| **Testing** (adicional) | pytest, pytest-asyncio, httpx | `>=8`, `>=0.24`, `>=0.27` |

**El stack está cerrado**: sin Redis, sin Docker, sin ORM alternativo, sin frontend, sin mocks de red, sin SQLite ni testcontainers. La **única** excepción es el bloque `# --- testing (adicional a la consigna) ---` de `requirements.txt`: la consigna pide pruebas contra PostgreSQL real y esos tres paquetes son el estándar del ecosistema FastAPI asincrónico. Cualquier otra dependencia debe proponerse y esperar confirmación.

---

## Arquitectura

Arquitectura **en capas** con flujo de una sola dirección por petición:

```
Petición HTTP
     │
     ▼
┌──────────────────────────────────────────────────────────────┐
│ main.py — app FastAPI + lifespan                             │
│   app.state.engine · app.state.session_maker · hash ficticio │
│   grupo abierto (/health, /auth) · grupo protegido (resto)   │
└──────────────────────────────────────────────────────────────┘
     │
     ▼
router.py  ── arma el UoW con una dependencia y lo pasa CERRADO
     │         traduce errores a códigos HTTP
     ▼
service.py ── reglas de negocio; abre el UoW con `async with`
     │         nunca construye el UoW
     ▼
unit_of_work.py ── commit al salir sin excepción / rollback con excepción
     │             no cierra la sesión (no la creó)
     ▼
repository.py ── add/update/soft_delete → flush() y nada más
     │            lecturas con selectinload/joinedload (sin lazy loading)
     ▼
models.py (SQLModel) ── PostgreSQL 16
```

Puntos que sostienen el diseño:

- **Un solo punto de confirmación.** `UnitOfWork.__aexit__` hace `commit()` si el bloque terminó bien y `rollback()` si salió con excepción (y relanza el fallo del commit). Los repositorios hacen `flush()` para obtener la PK y **nunca** `commit()`.
- **Quién crea, abre, confirma y cierra.** La sesión la crea `get_session` (una por petición, desde `app.state.session_maker`, con `expire_on_commit=False`) y la cierra la propia dependencia. El router arma el UoW con `Depends(get_uow)`; el servicio lo abre con `async with`; el UoW confirma o revierte, pero **no** cierra la sesión.
- **Motor y fábrica en el lifespan.** Se crean en `main.py` (`create_async_engine` + `async_sessionmaker`) y se guardan en `app.state`. Nunca al importar un módulo. Al apagar, `engine.dispose()`.
- **Sin carga perezosa.** Todas las relaciones declaran `lazy="raise_on_sql"`: un acceso perezoso lanza en vez de disparar SQL escondido. Las lecturas que necesitan relaciones deben precargarlas en el repositorio con `selectinload`/`joinedload` y un número fijo de consultas (caso C-15, pendiente en C-12).
- **Registro central de modelos.** `app/models.py` importa las trece tablas. Es obligatorio importarlo (lo hacen `main.py` y `migrations/env.py`) para que SQLAlchemy resuelva las relaciones que cruzan módulos.
- **`select` se importa de SQLModel.** Con `session.exec(...)`, el `select` de SQLAlchemy devuelve `Row` y la entidad pierde sus atributos sin error de tipos.
- **Contratos separados del ORM.** `app/core/schemas.py` define `ContratoEntrada` (`extra="forbid"`), `ContratoSalida` (`from_attributes`) y `Dinero` (Decimal que se serializa como string con dos decimales).
- **Errores centralizados.** `app/core/errors.py` traduce `IntegrityError` → 409, `DataError` → 422, `RequestValidationError` → 422 y uniforma los HTTP. Ninguna respuesta filtra el texto del motor ni una traza.

---

## Estructura de directorios

```
practica-parcial-prog/
├── main.py                     # App FastAPI, lifespan y los dos grupos de rutas
├── seed.py                     # Vacía y recarga el estado inicial conocido
├── alembic.ini                 # Configuración de Alembic (sin credenciales)
├── env.example                 # Todas las variables, ningún secreto
├── requirements.txt            # Stack cerrado + bloque de testing
├── AGENTS.md / CLAUDE.md       # Instrucciones para agentes (mismo contenido)
├── CHANGES.md                  # Roadmap de los 13 changes
├── README.md                   # Este documento
├── .env                        # Local, NO se versiona
├── app/
│   ├── models.py               # Registro central de las 13 tablas
│   ├── core/
│   │   ├── config.py           # Settings (pydantic-settings) + ASYNC_DATABASE_URL
│   │   ├── database.py         # get_session desde app.state
│   │   ├── dependencies.py     # get_usuario_actual, requiere_rol, exigir_password_al_dia
│   │   ├── errors.py           # Handlers centrales (409, 422, 404 uniforme)
│   │   ├── paginacion.py       # Page/PageParams {items, total, page, size, pages}
│   │   ├── repository.py       # BaseRepository[T] + SoftDeleteRepository[T]
│   │   ├── schemas.py          # ContratoEntrada/Salida, Dinero, cambios_enviados
│   │   ├── security.py         # bcrypt fuera del bucle + JWT (crear/verificar)
│   │   └── unit_of_work.py     # UnitOfWork base: commit/rollback, no cierra sesión
│   └── modules/
│       ├── health/
│       │   └── router.py       # /health/live y /health/ready (sólo router)
│       ├── usuarios/
│       │   ├── models.py       # usuario, asignacion_rol, intento_acceso, evento_seguridad
│       │   ├── schemas.py      # Contratos de auth, usuarios, roles, eventos
│       │   ├── repository.py   # Usuario, AsignacionRol, IntentoAcceso, EventoSeguridad
│       │   ├── unit_of_work.py # UsuariosUnitOfWork (incluye clientes)
│       │   ├── service.py      # Registro, login, roles, eventos, cambio de clave
│       │   ├── auth_router.py  # Router /auth (grupo abierto)
│       │   └── router.py       # Routers /usuarios y /eventos (grupo protegido)
│       ├── clientes/
│       │   ├── models.py       # cliente, vehiculo
│       │   └── repository.py   # ClienteRepository (usado por el auto-registro)
│       ├── repuestos/
│       │   ├── models.py       # repuesto, movimiento_stock, historial_precio_repuesto
│       │   ├── schemas.py      # RepuestoCrear (sin stock), RepuestoLeer, RepuestoPatch
│       │   ├── repository.py   # SoftDeleteRepository + búsqueda q parametrizada
│       │   ├── unit_of_work.py # RepuestosUnitOfWork
│       │   ├── service.py      # Listado, detalle y alta con stock 0
│       │   └── router.py       # /repuestos (grupo protegido)
│       └── ordenes/
│           └── models.py       # estado_orden, orden_trabajo, item_orden, historial_estado_orden
├── migrations/
│   ├── env.py                  # Plantilla asincrónica; URL desde Settings
│   ├── script.py.mako
│   ├── README.md
│   └── versions/
│       ├── 0001_crea_las_tablas_del_dominio.py   # Autogenerate: 13 tablas
│       └── 0002_solo_agregado.py                 # Escrita a mano: disparadores
├── test/
│   ├── pytest.ini              # asyncio_mode=auto, pythonpath=.., testpaths=.
│   ├── conftest.py             # Base de test, seed por test, cliente ASGI, fixtures de rol
│   ├── test_health.py          # /health/live y /health/ready
│   ├── test_entorno.py         # Import desde la raíz, DB de test, 13 tablas
│   ├── test_aislamiento.py     # El seed se restaura entre tests
│   ├── test_contracts.py       # Contratos, errores, paginación, búsqueda
│   ├── test_auth.py            # Registro, login, cookie, cambio de clave
│   ├── test_rbac.py            # 401/403, roles, autoprotección, eventos
│   ├── contracts.http          # Evidencia C-06 (⚠ requiere sesión, ver Limitaciones)
│   ├── auth.http               # Evidencia C-07
│   └── rbac.http               # Evidencia C-08
├── knowledge-base/             # 10 documentos de dominio + README
├── openspec/
│   ├── config.yaml
│   ├── specs/                  # Capacidades especificadas (24)
│   └── changes/
│       └── archive/            # C-01 a C-08 archivados
└── docs/
    └── TP_Cap1a6_Consigna.pdf  # Consigna original (22 páginas)
```

> `app/modules/clientes/` y `app/modules/ordenes/` todavía **no** tienen `schemas.py`, `service.py`, `router.py` ni `unit_of_work.py`: los crean `C-09`, `C-10` y `C-11`. Hoy existen las tablas y los modelos, pero no sus endpoints.

---

## Puesta en marcha

### Requisitos

- **Python 3.12** (el proyecto se desarrolló y se prueba con esa versión).
- **PostgreSQL 16** corriendo en local (o accesible por red).
- El cliente `psql`/`createdb` para crear las bases (o cualquier administrador de PostgreSQL).

### Paso a paso

Todos los comandos se ejecutan **desde la raíz del repositorio**.

**1. Crear y activar el entorno virtual**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate         # Linux / macOS
```

**2. Instalar dependencias**

```powershell
pip install -r requirements.txt
```

**3. Crear el archivo de entorno**

```powershell
Copy-Item env.example .env           # Windows PowerShell
# cp env.example .env                # Linux / macOS
```

Editá `.env` y completá, como mínimo, `POSTGRES_PASSWORD` y `SECRET_KEY` (clave de firma del JWT; `env.example` recomienda al menos 32 bytes). Ninguna de las dos tiene valor por defecto: sin ellas la aplicación **no arranca**. `.env` está en `.gitignore` y no se versiona.

**4. Crear las bases de datos**

```powershell
psql -U postgres -c "CREATE DATABASE taller_mecanico;"
```

La base de la suite (`taller_mecanico_test`) la crea `test/conftest.py` automáticamente si no existe, conectándose a la base administrativa `postgres`. Si preferís crearla a mano:

```powershell
psql -U postgres -c "CREATE DATABASE taller_mecanico_test;"
```

Los nombres `taller_mecanico` (desarrollo) y `taller_mecanico_test` (suite) son los que esperan la configuración y `conftest.py`.

**5. Aplicar las migraciones**

```powershell
alembic upgrade head
```

`alembic.ini` fija `script_location = migrations` y `prepend_sys_path = .`; `migrations/env.py` toma la URL de `Settings` (`POSTGRES_*` del `.env`), no de `alembic.ini`. El esquema se crea **sólo** así: la aplicación no usa `create_all`.

**6. Cargar los datos iniciales**

```powershell
python seed.py
```

Vacía las trece tablas con `TRUNCATE ... RESTART IDENTITY CASCADE` y carga catálogo, usuarios, clientes, vehículos, repuestos, órdenes e historiales en un solo Unit of Work. Al final imprime el conteo por tabla y la contraseña de los usuarios de prueba. Si la base no está migrada, aborta con el mensaje `ERROR: la base no está migrada`.

**7. Levantar la API**

```powershell
uvicorn main:app --reload
```

- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- OpenAPI JSON: <http://localhost:8000/openapi.json>

**8. Correr la suite** (opcional, con la base de test disponible)

```powershell
python -m pytest test/ -q
```

La suite usa el mismo `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_HOST`/`POSTGRES_PORT` del `.env`, fuerza `POSTGRES_DB=taller_mecanico_test`, `COOKIE_SECURE=false` y `BCRYPT_ROUNDS=4`, y restaura el seed antes de cada test.

---

## Variables de entorno

Definidas en `app/core/config.py` (`Settings`) y documentadas sin secretos en `env.example`.

| Variable | ¿Obligatoria? | Default | Qué hace |
|---|---|---|---|
| `POSTGRES_USER` | No | `postgres` | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | **Sí** (sin default) | — | Contraseña de PostgreSQL; si falta, la app no arranca |
| `POSTGRES_DB` | No | `taller_mecanico` | Base de datos de desarrollo (`taller_mecanico_test` en la suite) |
| `POSTGRES_HOST` | No | `localhost` | Host de la base |
| `POSTGRES_PORT` | No | `5432` | Puerto de la base |
| `SECRET_KEY` | **Sí** (sin default) | — | Clave de firma del JWT (HS256). Sin ella no arranca; no debe versionarse |
| `BCRYPT_ROUNDS` | No | `12` | Costo de bcrypt |
| `BCRYPT_MAX_CONCURRENT_HASHES` | No | `4` | Cuántos hashes corren a la vez fuera del bucle de eventos (semáforo) |
| `TOKEN_EXPIRE_MINUTES` | No | `30` | Duración del JWT y `Max-Age` de la cookie |
| `COOKIE_SECURE` | No | `false` | Atributo `Secure` de la cookie (`true` en producción) |
| `SQL_ECHO` | No | `false` | Muestra las consultas en consola (diagnóstico y conteo de N+1) |
| `POOL_SIZE` | No | `5` | Tamaño del pool del motor asincrónico |

`ASYNC_DATABASE_URL` **no** es una variable: es un `@computed_field` que arma `postgresql+asyncpg://usuario:clave@host:puerto/base`.

Reglas:

- `.env` **no se versiona** (está en `.gitignore`); `env.example` documenta las variables con valores de ejemplo.
- `SECRET_KEY` y `POSTGRES_PASSWORD` **no tienen default**: el arranque falla si faltan. Es deliberado.
- No hay credenciales reales en el repositorio, ni en `alembic.ini`.

---

## Autenticación y autorización

### Sesión: cookie `access_token`

El JWT viaja **sólo** en la cookie `access_token`, nunca en el cuerpo de la respuesta ni en un header `Authorization: Bearer` (ese header se ignora; caso C-03).

| Atributo | Valor |
|---|---|
| `HttpOnly` | Sí (no se puede leer desde JavaScript) |
| `SameSite` | `Lax` |
| `Secure` | `COOKIE_SECURE` (`false` en desarrollo) |
| `Max-Age` | `TOKEN_EXPIRE_MINUTES * 60` (1800 s con el default) |
| `Path` | `/` |

### Token

JWT firmado con HS256 y la `SECRET_KEY` del entorno. Claims:

- `sub` — id del usuario (como texto).
- `iat` — emisión, como marca numérica **con fracciones de segundo, sin truncar**.
- `exp` — vencimiento.
- `roles` — roles vigentes al emitirlo; son **informativos**, nunca autorizan.

`verificar_token` no levanta: devuelve `None` y el llamador responde 401.

### Los cuatro roles

`ADMIN`, `RECEPCION`, `MECANICO`, `CLIENTE`. Viven en `asignacion_rol` (no en una columna de `usuario`) con `desde`, `vence_en` y `revocada_en`. Un rol está **vigente** si la fila no está revocada (`revocada_en IS NULL`) y no venció (`vence_en` nulo o futuro).

### Autorización en cada petición

`requiere_rol(*roles)` consulta `asignacion_rol` **en la base en cada petición** (RN-04) y responde 403 si ninguno de los roles vigentes está entre los esperados. Revocar un rol le quita el permiso a una sesión ya abierta sin esperar a que venza el token (caso C-07). El claim `roles` del token no otorga nada.

`get_usuario_actual` lee **sólo** `request.cookies["access_token"]` y responde **401 uniforme** («No hay una sesión válida.») si: no hay cookie, el token es inválido o venció, el usuario no existe o está inactivo, o el `iat` es anterior o igual a `password_cambiada_en`.

### Dos grupos de rutas

Definidos en `main.py`. El control de contraseña provisoria se monta **una sola vez**, como dependencia del grupo protegido:

| Grupo | Rutas | Exige |
|---|---|---|
| **Abierto** | `/health/*`, `/auth/*` | Nada. `/auth/yo` y `/auth/cambiar-password` exigen sesión **por dentro**, pero no el cambio obligatorio |
| **Protegido** | `/usuarios`, `/eventos`, `/repuestos` (y los módulos futuros) | Sesión válida (401) y `debe_cambiar_password = false` (403) |

El 403 de contraseña provisoria dice: «Tenés que cambiar la contraseña provisoria antes de usar esta ruta.» `/auth` queda abierto a propósito: si el grupo protegido incluyera el cambio de contraseña, el usuario afectado no podría cambiar la clave nunca.

### Reglas de seguridad clave

- **RN-07 — el cambio de contraseña invalida las sesiones anteriores.** `password_cambiada_en` se anota con hora completa (`timestamptz`) y el `iat` del token se compara **sin truncar**, con `<=`. El token que emite el propio cambio se crea después (con `iat_minimo`) y sí vale; los anteriores dan 401 aunque sean del mismo segundo. En Windows el reloj tiene ~15,6 ms de granularidad: sin esta comparación estricta, el token viejo sobrevivía ~40 % de las veces.
- **RN-08 — límite de intentos.** Con 5 fallos del mismo `(email, ip)` en 60 s, el login responde **429 con `Retry-After`** y **sin calcular ni verificar ningún hash**. Un login correcto reinicia la cuenta; los fallos viejos quedan en `intento_acceso` pero dejan de contar. Cada intento se anota en una **sesión y transacción propias, siempre confirmadas**.
- **RN-09 — no revelar qué cuentas existen.** Correo inexistente y contraseña equivocada devuelven el **mismo 401** («Credenciales inválidas.») y tardan parecido: cuando el correo no existe se verifica contra un **hash ficticio** calculado una sola vez en el lifespan.

### bcrypt

`hash_password`/`verify_password` corren en `asyncio.to_thread` bajo un semáforo (`BCRYPT_MAX_CONCURRENT_HASHES`), con el costo de `BCRYPT_ROUNDS`. El hash se calcula **antes** de abrir la transacción. Todo campo que termina en bcrypt acepta **hasta 72 bytes** UTF-8 (validado en el contrato: 422, nunca 500); la contraseña **nueva** del cambio exige además **más de 8 bytes**.

---

## Endpoints

Lista extraída del código (`main.py` y los routers), no del roadmap. Todas las rutas del grupo protegido responden además **401** sin sesión y **403** con el cambio de contraseña pendiente.

### Grupo abierto

| Método | Ruta | Rol requerido | Descripción | Códigos |
|---|---|---|---|---|
| GET | `/` | — | Mensaje de bienvenida de la API | `200` |
| GET | `/health/live` | — | Liveness; no toca la base | `200` |
| GET | `/health/ready` | — | `SELECT 1` contra PostgreSQL | `200`, `503` |
| POST | `/auth/registro` | Público | Auto-registro: usuario + rol `CLIENTE` + ficha de cliente en un solo UoW | `201`, `409`, `422` |
| POST | `/auth/login` | Público | Inicia sesión; deja el JWT en la cookie y **no** en el cuerpo | `200`, `401`, `422`, `429` |
| POST | `/auth/logout` | Público | Borra la cookie `access_token` | `200` |
| GET | `/auth/yo` | Sesión | Usuario, roles vigentes (base) y roles del token (informativos) | `200`, `401` |
| POST | `/auth/cambiar-password` | Sesión | Verifica la actual, cambia y emite un token nuevo | `200`, `401`, `422` |

> `GET /` se declara directo sobre `app` en `main.py`, fuera de los dos grupos; por eso no lleva ninguna dependencia.

### Módulo `usuarios` (grupo protegido)

| Método | Ruta | Rol requerido | Descripción | Códigos |
|---|---|---|---|---|
| POST | `/usuarios` | ADMIN | Alta de personal con contraseña provisoria (`debe_cambiar_password=true`) + evento | `201`, `409`, `422` |
| GET | `/usuarios/{usuario_id}/roles` | ADMIN | Historial completo de roles (incluye revocados y vencidos) | `200`, `404` |
| POST | `/usuarios/{usuario_id}/roles` | ADMIN | Asigna un rol con `desde`/`vence_en` opcionales (con zona y futuro) + evento | `201`, `404`, `409`, `422` |
| DELETE | `/usuarios/{usuario_id}/roles/{rol}` | ADMIN | Revoca escribiendo `revocada_en` (no borra) + evento; autoprotección RN-05 | `200`, `404`, `409` |
| GET | `/eventos` | ADMIN | Historial de seguridad paginado (`page`, `size`) | `200`, `422` |

### Módulo `repuestos` (grupo protegido)

| Método | Ruta | Rol requerido | Descripción | Códigos |
|---|---|---|---|---|
| GET | `/repuestos` | ADMIN, RECEPCION, MECANICO | Listado paginado de vigentes, búsqueda `q` en descripción (parámetro ligado) | `200`, `422` |
| GET | `/repuestos/{repuesto_id}` | ADMIN, RECEPCION, MECANICO | Detalle de un repuesto vigente | `200`, `404` |
| POST | `/repuestos` | ADMIN | Alta con `codigo`, `descripcion` y `precio`; **nace con stock 0** | `201`, `409`, `422` |

Notas de contrato verificadas en el código:

- El alta de repuesto **no** declara `stock` ni `stock_inicial`: enviarlos es 422 (`extra="forbid"`). El stock inicial llega en `C-10`.
- El dinero viaja como **string Decimal** (`"8500.00"`), nunca como número.
- Los listados usan el envoltorio uniforme `{items, total, page, size, pages}`; `page` empieza en 1, `size` va de 1 a 100 (default 20) y una página fuera de rango es 422 con mensaje propio.

### Pendientes (`C-09` a `C-13`)

Estas rutas **todavía no existen** en el código; hoy responderían 404. Se listan para no confundirlas con lo implementado:

| Change | Rutas planificadas |
|---|---|
| C-09 | `POST /clientes`, `GET /clientes/{id}` (con vehículos), `POST /clientes/{id}/vehiculos`, `DELETE /vehiculos/{id}`, `GET /mis-vehiculos` |
| C-10 | `PATCH /repuestos/{id}` (descripción y precio, con historial), `DELETE /repuestos/{id}`, `POST /repuestos/{id}/reponer`, `GET /repuestos/{id}/movimientos`, `GET /repuestos/{id}/precios`, y `stock_inicial` en el alta |
| C-11 | `POST /ordenes`, `GET /ordenes`, `GET /ordenes/{id}`, `POST /ordenes/{id}/iniciar`, `POST /ordenes/{id}/terminar`, `POST /ordenes/{id}/cancelar`, `GET /estados-orden`, `GET /mis-ordenes` |
| C-12 | Lecturas con número fijo de consultas en `GET /ordenes/{id}`, `GET /clientes/{id}` y `/mis-*` (no agrega rutas nuevas) |
| C-13 | Ninguna ruta: consolida la evidencia `.http`, `test/solo_agregado.sql` y la suite |

---

## Modelo de datos

Trece tablas, agrupadas por el módulo que las declara. Todos los nombres son los obligatorios de la consigna. Todas las fechas son `timestamptz`, el dinero es `NUMERIC`/`Decimal`, y **toda clave foránea lleva índice explícito** (PostgreSQL no lo crea solo). Las FK usan `ON DELETE RESTRICT`.

### Identidad y accesos — `app/modules/usuarios/models.py`

| Tabla | Una línea | Restricciones notables |
|---|---|---|
| `usuario` | Cuenta de acceso; el rol **no** es columna | `email` UNIQUE; `password_cambiada_en` timestamptz nulo; `activo` y `debe_cambiar_password` booleanos |
| `asignacion_rol` | Rol otorgado con vigencia e historial | CHECK `rol IN ('ADMIN','RECEPCION','MECANICO','CLIENTE')`; **único parcial** `(usuario_id, rol) WHERE revocada_en IS NULL`; índice `usuario_id` |
| `intento_acceso` | Cada intento de login, correcto o fallido | Índice `(email, ip, cuando)`; sin relaciones |
| `evento_seguridad` | Auditoría de altas, roles y contraseñas | `actor` es texto (`'SISTEMA'` no es usuario); sin relaciones |

### Cartera de clientes — `app/modules/clientes/models.py`

| Tabla | Una línea | Restricciones notables |
|---|---|---|
| `cliente` | Ficha del cliente, con o sin cuenta | `usuario_id` UNIQUE y **nulo** (1:1 opcional); `documento` UNIQUE |
| `vehiculo` | Vehículo con borrado lógico | **Único parcial** `(patente) WHERE borrado_en IS NULL`; CHECK `anio BETWEEN 1950 AND 2100`; índice `cliente_id` |

### Repuestos y stock — `app/modules/repuestos/models.py`

| Tabla | Una línea | Restricciones notables |
|---|---|---|
| `repuesto` | Catálogo con borrado lógico | **Único parcial** `(codigo) WHERE borrado_en IS NULL`; CHECK `precio > 0`, `stock >= 0`; `NUMERIC(10,2)` |
| `movimiento_stock` | Punto único de escritura del stock | CHECK `cantidad <> 0` (entradas positivas, salidas negativas); **sólo agregado**; índices de sus tres FK |
| `historial_precio_repuesto` | Cada cambio de precio | CHECK `precio_nuevo > 0` y `precio_nuevo <> precio_anterior`; precios `NUMERIC(10,2)`; **sólo agregado** |

### Órdenes de trabajo — `app/modules/ordenes/models.py`

| Tabla | Una línea | Restricciones notables |
|---|---|---|
| `estado_orden` | Catálogo de estados; lo carga `seed.py` | PK `codigo` (no `id`); `posicion` UNIQUE; `es_final`; la migración la crea **vacía** |
| `orden_trabajo` | Orden de un vehículo | `estado` FK a `estado_orden.codigo`; CHECK `total >= 0`; `total NUMERIC(12,2)`; índices `vehiculo_id`, `mecanico_id`, `estado` |
| `item_orden` | Repuesto usado en la orden (composición) | UNIQUE `(orden_id, repuesto_id)`; CHECK `cantidad > 0` y `precio_unitario > 0`; índice `repuesto_id`; `cascade="all, delete-orphan"` |
| `historial_estado_orden` | Transición de estado | FKs `desde_estado`/`hasta_estado` al catálogo; **sólo agregado**; índices de sus cuatro FK |

### ERD

```mermaid
erDiagram
    usuario ||--o| cliente : "1:1 opcional"
    usuario ||--o{ asignacion_rol : "roles"
    cliente ||--o{ vehiculo : "cartera"
    vehiculo ||--o{ orden_trabajo : "ingresos"
    usuario ||--o{ orden_trabajo : "mecánico asignado"
    orden_trabajo ||--|{ item_orden : "composición"
    repuesto ||--o{ item_orden : "usado en"
    estado_orden ||--o{ orden_trabajo : "catálogo"
    orden_trabajo ||--o{ historial_estado_orden : "transiciones"
    estado_orden ||--o{ historial_estado_orden : "desde/hasta"
    usuario ||--o{ historial_estado_orden : "autor"
    repuesto ||--o{ movimiento_stock : "movimientos"
    orden_trabajo ||--o{ movimiento_stock : "salidas"
    usuario ||--o{ movimiento_stock : "autor"
    repuesto ||--o{ historial_precio_repuesto : "precios"
    usuario ||--o{ historial_precio_repuesto : "autor"
```

`intento_acceso` y `evento_seguridad` no se relacionan con ninguna otra tabla.

### Los tres índices únicos parciales

| Tabla | Índice | `WHERE` | Para qué |
|---|---|---|---|
| `asignacion_rol` | `(usuario_id, rol)` | `revocada_en IS NULL` | A lo sumo una asignación **abierta** por rol |
| `vehiculo` | `(patente)` | `borrado_en IS NULL` | Un auto vendido se puede volver a registrar con la misma patente |
| `repuesto` | `(codigo)` | `borrado_en IS NULL` | El código se reutiliza entre los vigentes |

La unicidad la garantiza la **base**, no una consulta previa: el choque se traduce a 409 en `app/core/errors.py`.

### Borrado lógico y sólo agregado

- **Borrado lógico:** `vehiculo` y `repuesto` usan `SoftDeleteRepository`; la baja escribe `borrado_en` y la fila se conserva.
- **Sólo agregado:** `historial_estado_orden`, `movimiento_stock` y `historial_precio_repuesto` rechazan `UPDATE` y `DELETE` con un disparador creado por la migración `0002`. `INSERT` sigue permitido. El disparador corre venga de donde venga (API, seed o psql).

---

## Migraciones

Alembic con **plantilla asincrónica** (`migrations/env.py` usa `async_engine_from_config` y `connection.run_sync`). La URL sale de `Settings`, nunca de `alembic.ini`; se importa `app/models.py` para que el metadata conozca las trece tablas. `create_all` está **prohibido**: el esquema se crea únicamente con `alembic upgrade head`.

| Revisión | Archivo | Qué hace |
|---|---|---|
| `0001` | `0001_crea_las_tablas_del_dominio.py` | Generada con `--autogenerate` y revisada a mano: las 13 tablas, CHECK, FK nombradas, índices y los tres `postgresql_where`. Crea `estado_orden` **vacía** (el catálogo es dato y lo carga `seed.py`) |
| `0002` | `0002_solo_agregado.py` | Escrita a mano: función `solo_agregado_rechazar_modificacion()` y disparadores `trg_<tabla>_solo_agregado` (`BEFORE UPDATE OR DELETE`) sobre las tres tablas de auditoría. El rechazo usa `ERRCODE = integrity_constraint_violation` (SQLSTATE 23000). El `downgrade` borra disparadores y función |

Ciclo de verificación sobre una base vacía:

```powershell
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

Consideraciones:

- `alembic downgrade base` baja las dos revisiones: la `0002` quita disparadores y función, y la `0001` elimina las tablas.
- `seed.py` reinicia con `TRUNCATE`, que **no** dispara el trigger `BEFORE UPDATE OR DELETE`. Un reset con `DELETE` sería rechazado (es lo buscado).
- `alembic upgrade head --sql` genera el SQL sin conectarse (modo offline de `env.py`).

---

## Datos iniciales (seed)

`seed.py` deja la base en un estado conocido y **reproducible**: vacía las trece tablas con `TRUNCATE ... RESTART IDENTITY CASCADE` y recarga todo en un solo Unit of Work. Es parte de la puesta en marcha, no un extra. Los IDs son deterministas (1 a 7 para los usuarios).

### Usuarios de prueba

Todos comparten la contraseña **`secreto123`** (de mentira, definida en `seed.py`).

| ID | Email | Rol | Para qué sirve en las pruebas |
|---|---|---|---|
| 1 | `admin@example.com` | ADMIN | Rutas de administración, matriz RBAC, autoprotección (caso C-08) |
| 2 | `admin2@example.com` | ADMIN | Revocar el ADMIN de otro sin dejar el sistema con 0 administradores (RN-05) |
| 3 | `recepcion@example.com` | RECEPCION | 403 en rutas de ADMIN y revocación con efecto inmediato (caso C-07) |
| 4 | `mecanico@example.com` | MECANICO | 403 en administración; mecánico asignado a la orden 2 |
| 5 | `mecanico2@example.com` | MECANICO | Segundo mecánico; reasignación de un rol vencido |
| 6 | `cliente@example.com` | CLIENTE | Cliente autenticado sin rol de personal (403, no 401); dueña de Laura |
| 7 | `nuevo@example.com` | MECANICO + `debe_cambiar_password` | 403 en el grupo protegido; cambio de contraseña y RN-07 (caso C-04) |

### Resto del estado inicial

| Qué | Datos |
|---|---|
| Catálogo `estado_orden` | `PENDIENTE` (posición 1), `EN_REPARACION` (2), `TERMINADA` (3, final), `CANCELADA` (4, final) |
| Clientes | Laura (`30111222`, con usuario `cliente@example.com`) y Jorge (`27888999`, **sin** usuario) |
| Vehículos | `AAA111` Fiat Uno 2015 y `AAB222` Renault Clio 2018 (Laura); `BBB333` Ford Fiesta 2020 (Jorge) |
| Repuestos | FA-001 Filtro de aceite (10, $8500), PF-002 Pastillas de freno (4, $12000), BU-003 Bujía (2, $1500), AC-004 Aceite por litro (20, $2500) |
| Movimientos | Un `movimiento_stock` «Stock inicial» por cada repuesto |
| Órdenes | Orden 1 `PENDIENTE` del Fiat de Laura; Orden 2 `EN_REPARACION` del Ford de Jorge, asignada al mecánico, con **4 bujías cuando hay 2** (insumo del caso C-11) |
| Historial de estados | Una línea por orden (y la segunda transición de la orden 2) |
| Historial de precios | Una línea del filtro: de `8000.00` a `8500.00` |
| Evento de seguridad | `actor='SISTEMA'`, «Carga de los datos iniciales» |

> El seed también corre antes de **cada** test (`test/conftest.py`), así que cada prueba arranca de este mismo estado.

---

## Pruebas

### Cómo se corre

Desde la raíz del repositorio, con PostgreSQL levantado y `.env` con las credenciales:

```powershell
python -m pytest test/ -q        # resumen
python -m pytest test/ -v        # detalle por test
python -m pytest test/test_auth.py -q   # un archivo
```

La suite está configurada en `test/pytest.ini`: `asyncio_mode = auto`, `pythonpath = ..`, `testpaths = .` y un único bucle de eventos por sesión (evita «bound to a different event loop» con el motor y el semáforo de bcrypt).

Qué hace `test/conftest.py`:

- Fija las variables de test **antes** de importar la app: `POSTGRES_DB=taller_mecanico_test`, `SECRET_KEY` de prueba, `COOKIE_SECURE=false`, `SQL_ECHO=false`, `BCRYPT_ROUNDS=4`.
- Crea la base de test si no existe y aplica `alembic upgrade head` una sola vez por sesión.
- Re-ejecuta `seed.py` antes de cada test (sin transacciones «trucadas»).
- Expone un `httpx.AsyncClient` con `ASGITransport` y el lifespan real de la app, más el helper `login(email, password)` y fixtures de sesión por rol.

Corre contra **PostgreSQL real**: sin SQLite, sin repositorios falsos, sin mocks de red y sin testcontainers. El único doble es el de `/health/ready` cuando se simula una caída de infraestructura.

**Resultado actual: 64 pruebas en verde.**

### Qué cubre cada archivo

| Archivo | Tests | Cobertura |
|---|---|---|
| `test/test_health.py` | 3 | `/health/live` (sin tocar la base), `/health/ready` 200 y 503 (caso C-01) |
| `test/test_entorno.py` | 3 | `import main`/`import app` desde la raíz, `Settings` apuntando a la base de test, esquema migrado con 13 tablas |
| `test/test_aislamiento.py` | 2 | El seed se restaura entre tests (un test ensucia y el siguiente ve el estado base) |
| `test/test_contracts.py` | 19 | `extra="forbid"`, límite de 72 bytes, contraseña multibyte, paginación y 422, envoltorio uniforme, dinero como string, `q` con comillas sin inyección (parte SQL del caso C-16), `IntegrityError` → 409, 404 propios, convención PATCH |
| `test/test_auth.py` | 19 | Registro OK/repetido (caso C-02), login sin token en el cuerpo, cookie vs Bearer (C-03), 429 con `Retry-After` sin hash (C-05), hash ficticio (RN-09), cambio de clave y RN-07 (C-04), logout, ninguna respuesta con `password_hash` |
| `test/test_rbac.py` | 18 | 401 vs 403, matriz de repuestos, claim `roles` que no autoriza, revocación inmediata (C-07), `vence_en` sin zona/pasado → 422, autoprotección (C-08), 403 por contraseña provisoria, eventos de seguridad, `/eventos` paginado |

### Evidencia `.http`

Los archivos `test/*.http` son la **evidencia pedida por la consigna**; la suite `.py` es su réplica automatizada. Se ejecutan con un cliente HTTP de IDE (REST Client de VS Code, cliente HTTP de JetBrains) contra la app levantada y con el seed cargado.

| Archivo | Contenido |
|---|---|
| `test/contracts.http` | Contratos, paginación, 409/404 y validaciones (C-06). **Desactualizado frente al RBAC**: sus peticiones no inician sesión y hoy `/repuestos` y `/usuarios` son del grupo protegido (ver [Limitaciones](#limitaciones-y-deuda-conocida)) |
| `test/auth.http` | Registro, login, cookie vs Bearer, 429, `/auth/yo`, cambio de clave y logout (C-07) |
| `test/rbac.http` | 401/403, matriz de roles, revocación inmediata, `vence_en`, autoprotección, contraseña provisoria y eventos (C-08) |

### Mapeo de los casos C-01 a C-19

| Caso | Qué verifica | Estado |
|---|---|---|
| C-01 | `/health/live` y `/health/ready` | ✓ `test_health.py` |
| C-02 | Registro con documento repetido → 409 sin apropiarse de la ficha | ✓ `test_auth.py` |
| C-03 | Cookie vs `Authorization: Bearer` → 401 | ✓ `test_auth.py` |
| C-04 | El cambio de contraseña invalida el token anterior | ✓ `test_auth.py` |
| C-05 | 5 fallos → 429 con `Retry-After` | ✓ `test_auth.py` |
| C-06 | Orden ajena → 403 | ☐ pendiente (`C-11`) |
| C-07 | Revocación de rol con efecto inmediato | ✓ `test_rbac.py` |
| C-08 | Autoprotección del último ADMIN → 409 | ✓ `test_rbac.py` |
| C-09 | Catálogo de estados vacío → 409 | ☐ pendiente (`C-11`) |
| C-10 | Repuesto inexistente no deja la orden | ☐ pendiente (`C-11`) |
| C-11 | Stock insuficiente → rollback total | ☐ pendiente (`C-11`) |
| C-12 | Aviso post-respuesta sólo si se confirmó | ☐ pendiente (`C-11`/`C-12`) |
| C-13 | Cancelar una orden TERMINADA → 409 | ☐ pendiente (`C-11`) |
| C-14 | `UPDATE`/`DELETE` rechazados en las tablas de sólo agregado | ☐ pendiente: `test/solo_agregado.sql` **no existe todavía** (`C-13`); se ejercita con `psql` |
| C-15 | Detalle con 2 y 4 ítems usa el mismo número de consultas | ☐ pendiente (`C-12`) |
| C-16 | `stock` por PATCH → 422 e inyección SQL en `q` | ◐ parcial: la parte SQL está en `test_contracts.py`; la parte del PATCH llega con `C-10` |
| C-17 | Estado no declarado → 422 | ☐ pendiente (`C-11`) |
| C-18 | PATCH sin cambio de precio no deja línea | ☐ pendiente (`C-10`) |
| C-19 | Patente reutilizable después de la baja | ☐ pendiente (`C-09`) |

Quedan **7 casos completamente cubiertos** (C-01 a C-05, C-07 y C-08), 1 parcial (C-16) y 11 pendientes de los changes de dominio. La matriz definitiva —`.http` + prueba automatizada por caso— es entregable de `C-13`.

---

## Flujo de trabajo del proyecto

El proyecto usa **OPSX/OpenSpec** (spec-driven development). Cada unidad de trabajo es un **change** atómico: un agente puede implementarlo en una sesión.

```
1. Leer la KB relevante (knowledge-base/)
2. Identificar el change en CHANGES.md y verificar dependencias
3. /opsx:propose C-NN-nombre   → proposal + design + specs + tasks
4. Implementar las tasks (cargando las skills del rol)
5. /opsx:archive C-NN-nombre  → archivar + marcar [x] en CHANGES.md + actualizar este README
```

- **Changes en curso:** `openspec/changes/<change>/` con `proposal.md`, `design.md`, `tasks.md` y `specs/`.
- **Changes cerrados:** `openspec/changes/archive/<fecha>-<change>/` (C-01 a C-08 ya archivados).
- **Capacidades vigentes:** `openspec/specs/<capacidad>/spec.md` (24 capacidades).
- **Orden y dependencias:** `CHANGES.md` es el índice canónico (árbol, gates, camino crítico, plan con 3 agentes).

**Commits:** Conventional Commits en español (`feat:`, `fix:`, `test:`, `chore:`), **sin trailers de co-autoría IA**. No se commitea ni se pushea sin pedido explícito del usuario.

**Reglas duras:** viven en `AGENTS.md` (y su copia `CLAUDE.md`). Ante conflicto entre la KB y `AGENTS.md`, prevalecen las reglas duras. Resumen de las que más se rompen: `Decimal`/`NUMERIC` para dinero, `timestamptz` para fechas, esquema sólo por Alembic, `flush()` en repositorios y `commit()` sólo en el UoW, sin lazy loading, sin SQL concatenado, token sólo en cookie, nunca `password_hash` en respuestas, y errores con mensaje propio (409/422, nunca texto del motor).

---

## Documentación

| Documento | Contenido |
|---|---|
| [`knowledge-base/README.md`](knowledge-base/README.md) | Índice y resumen ejecutivo de la KB |
| [`knowledge-base/01_vision_y_objetivos.md`](knowledge-base/01_vision_y_objetivos.md) | Propósito, objetivos por actor, alcance, fuera de alcance y criterios de evaluación |
| [`knowledge-base/02_descripcion_general.md`](knowledge-base/02_descripcion_general.md) | Stack, arquitectura en capas, API de referencia y ejemplos de contrato |
| [`knowledge-base/03_actores_y_roles.md`](knowledge-base/03_actores_y_roles.md) | Actores, matriz RBAC completa, reglas 401/403 y rutas públicas |
| [`knowledge-base/04_modelo_de_datos.md`](knowledge-base/04_modelo_de_datos.md) | Las 13 entidades, ERD textual, índices parciales y seed |
| [`knowledge-base/05_reglas_de_negocio.md`](knowledge-base/05_reglas_de_negocio.md) | RN-01 a RN-20 con su garante |
| [`knowledge-base/06_funcionalidades.md`](knowledge-base/06_funcionalidades.md) | 26 historias de usuario (US-001 a US-026) en 8 épicas |
| [`knowledge-base/07_flujos_principales.md`](knowledge-base/07_flujos_principales.md) | 13 flujos extremo a extremo |
| [`knowledge-base/08_arquitectura_propuesta.md`](knowledge-base/08_arquitectura_propuesta.md) | Patrones, estructura obligatoria, seguridad, variables y requisitos no funcionales |
| [`knowledge-base/09_decisiones_y_supuestos.md`](knowledge-base/09_decisiones_y_supuestos.md) | Decisiones DD-01 a DD-14 y supuestos SU-01 a SU-07 |
| [`knowledge-base/10_preguntas_abiertas.md`](knowledge-base/10_preguntas_abiertas.md) | Inconsistencias IN-01 a IN-04 (las tres de prioridad alta, resueltas) y preguntas abiertas |
| [`CHANGES.md`](CHANGES.md) | Roadmap: 13 changes, dependencias, gates, camino crítico y plan multiagente |
| [`AGENTS.md`](AGENTS.md) · [`CLAUDE.md`](CLAUDE.md) | Instrucciones para agentes: stack, skills, roadmap y reglas duras |
| [`openspec/`](openspec/) | `config.yaml`, specs vigentes y changes archivados |
| [`docs/TP_Cap1a6_Consigna.pdf`](docs/TP_Cap1a6_Consigna.pdf) | Consigna original del TP (22 páginas) |

---

## Limitaciones y deuda conocida

Lo que falta o merece atención, sin dramatizar:

**Alcance pendiente**

- **No existen endpoints de clientes, vehículos ni órdenes** (`C-09`, `C-11`). Las tablas y los modelos están; los routers y servicios no. Hoy `/clientes`, `/vehiculos`, `/ordenes`, `/estados-orden` y `/mis-*` responden 404.
- **El módulo `repuestos` está a medio ABM** (`C-10`): hay listado, detalle y alta, pero no `PATCH`, baja lógica, reposición ni historiales. El alta **no acepta `stock_inicial`** y siempre crea stock 0 (el contrato rechaza el campo con 422).
- **No hay verificación de N+1 ni de `BackgroundTasks`** (`C-12`): todavía no hay lecturas con relaciones ni aviso post-respuesta que auditar.
- **Falta la evidencia de entrega** (`C-13`): `test/solo_agregado.sql` (caso C-14) no existe, y quedan casos C-06, C-09 a C-15, C-17 a C-19 sin prueba automatizada.

**Deuda técnica observada en el código**

- **`session.execute()` genera `DeprecationWarning` de SQLModel** en `app/core/repository.py:84` (el `count`) y en `app/modules/usuarios/repository.py:133,155,184` (conteos y `scalar_one`/`one`), además de `app/modules/health/router.py:17`. Son usos legítimos de `Row`/escalar, pero la suite emite 161 warnings. Si se migran a `exec()`, hay que revisar que no cambien los tipos de retorno.
- **`/health/ready` devuelve `str(e)` en el `detail` del 503.** Eso puede exponer texto interno del motor (host, usuario, mensaje de conexión) y va contra el espíritu de RN-18, que prohíbe filtrar detalles de la infraestructura. Lo correcto sería un mensaje fijo y el detalle sólo en el log.
- **`test/contracts.http` quedó desactualizado después de `C-08`.** El archivo dice que «todavía no hay autenticación» y no inicia sesión; sus `GET /repuestos` y `POST /usuarios` hoy responden 401 porque esas rutas pasaron al grupo protegido. La réplica `test_contracts.py` sí se actualizó (usa la fixture `admin`). Hay que refrescar el `.http` en `C-13`.
- **La documentación describe el objetivo completo, no sólo lo implementado.** `knowledge-base/02_descripcion_general.md` lista todos los endpoints (incluidos los de `C-09` a `C-13`) y `knowledge-base/08_arquitectura_propuesta.md` muestra la estructura de módulos completa. La estructura real de hoy está en [Estructura de directorios](#estructura-de-directorios) y la lista real de rutas en [Endpoints](#endpoints).
- **`app/modules/ordenes/models.py` documenta el módulo como `ordenes`, pero la KB lo llama `ordeneses`** en una tabla (`04_modelo_de_datos.md`, §Dominios). Es una errata de la KB; manda el nombre del código.
- **`practica-parcial-prog-main/`** es un directorio **vacío** residual en la raíz; no forma parte del proyecto.
- **Sin entorno reproducible más allá de `requirements.txt`.** No hay `pyproject.toml`, `Dockerfile` ni lockfile: las versiones son mínimas (`>=`) y se instalan desde `requirements.txt`. Está alineado con el stack cerrado de la consigna (sin Docker), pero implica que dos instalaciones en fechas distintas pueden resolver versiones distintas.
- **Sin verificación de concurrencia.** Está explícitamente fuera de alcance (capítulo 7): dos terminaciones simultáneas de órdenes pueden leer el mismo stock (actualización perdida permitida por el nivel de aislamiento por defecto).
