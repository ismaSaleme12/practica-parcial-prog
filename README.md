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

**Estado actual:** los changes `C-01` a `C-11` están implementados y archivados. La API está **completa en endpoints**: autenticación, RBAC, clientes/vehículos, repuestos/stock y órdenes de trabajo con su máquina de estados y la transacción de descuento de stock. Quedan la auditoría de lectura sin N+1 y el aviso en segundo plano (`C-12`) y la consolidación de la evidencia de entrega (`C-13`).

---

## Estado del proyecto

<!-- ACTUALIZAR AL ARCHIVAR UN CHANGE: marcar la fila como completada, ajustar el contador de pruebas y mover el change de pending a openspec/changes/archive/. -->

**Changes completados: 11 de 13.** **Suite: 189 pruebas en verde** (`python -m pytest test/ -q` contra PostgreSQL real).

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
| C-09 | `clientes-vehiculos` | ✓ completado | 5 — Dominio del taller |
| C-10 | `repuestos-stock` | ✓ completado | 5 — Dominio del taller |
| C-11 | `ordenes-trabajo` | ✓ completado | 5 — Dominio del taller |
| C-12 | `detalle-sin-n1` | ☐ pendiente | 6 — Calidad de lectura |
| C-13 | `casos-de-prueba` | ☐ pendiente | 6 — Entrega |

Los once changes completados están archivados en `openspec/changes/archive/`; las capacidades especificadas viven en `openspec/specs/` (33 capacidades).

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
│       │   ├── schemas.py      # ClienteCrear, ClienteFicha, VehiculoCrear, VehiculoLeer
│       │   ├── repository.py   # ClienteRepository, VehiculoRepository (selectinload, órdenes abiertas)
│       │   ├── unit_of_work.py # ClientesUnitOfWork
│       │   ├── service.py      # Ficha con vehículos, alta de vehículo, baja con 409, /mis-vehiculos
│       │   └── router.py       # /clientes, /vehiculos y /mis-vehiculos (grupo protegido)
│       ├── repuestos/
│       │   ├── models.py       # repuesto, movimiento_stock, historial_precio_repuesto
│       │   ├── schemas.py      # RepuestoCrear (stock_inicial), RepuestoPatch, ReponerStock, historiales
│       │   ├── repository.py   # SoftDeleteRepository + búsqueda q + repositorios de sólo agregado
│       │   ├── unit_of_work.py # RepuestosUnitOfWork (catálogo + movimientos + historial de precios)
│       │   ├── service.py      # Alta con stock_inicial, PATCH con historial, baja, reposición
│       │   └── router.py       # /repuestos completo (grupo protegido)
│       └── ordenes/
│           ├── models.py       # estado_orden, orden_trabajo, item_orden, historial_estado_orden
│           ├── schemas.py      # OrdenCrear, OrdenDetalle, OrdenResumen, enum de estados
│           ├── repository.py   # Precargas fijas + EstadoOrdenRepository de sólo lectura
│           ├── unit_of_work.py # OrdenesUnitOfWork (reusa repos de clientes y repuestos)
│           ├── service.py      # Alta, transiciones, rollback de stock y aviso simulado
│           └── router.py       # /ordenes, /estados-orden y /mis-ordenes (grupo protegido)
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
│   ├── test_clientes.py        # Clientes, vehículos, baja lógica, /mis-vehiculos
│   ├── test_repuestos.py       # Catálogo, stock, historial de precios, reposición
│   ├── contracts.http          # Evidencia C-06 (abre con login de ADMIN)
│   ├── auth.http               # Evidencia C-07
│   ├── rbac.http               # Evidencia C-08
│   ├── clientes.http           # Evidencia C-09
│   └── repuestos.http          # Evidencia C-10
├── knowledge-base/             # 10 documentos de dominio + README
├── openspec/
│   ├── config.yaml
│   ├── specs/                  # Capacidades especificadas (30)
│   └── changes/
│       └── archive/            # C-01 a C-10 archivados
└── docs/
    └── TP_Cap1a6_Consigna.pdf  # Consigna original (22 páginas)
```

> `app/modules/ordenes/` todavía **no** tiene `schemas.py`, `service.py`, `router.py` ni `unit_of_work.py`: los crea `C-11`. Hoy existen las tablas y los modelos, pero no sus endpoints.

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
| **Protegido** | `/usuarios`, `/eventos`, `/clientes`, `/vehiculos`, `/mis-vehiculos`, `/repuestos`, `/ordenes`, `/estados-orden`, `/mis-ordenes` | Sesión válida (401) y `debe_cambiar_password = false` (403) |

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

### Módulo `clientes` (grupo protegido)

| Método | Ruta | Rol requerido | Descripción | Códigos |
|---|---|---|---|---|
| POST | `/clientes` | ADMIN, RECEPCION | Alta de ficha de cliente (`documento` UNIQUE) | `201`, `409`, `422` |
| GET | `/clientes/{cliente_id}` | ADMIN, RECEPCION | Ficha con sus vehículos **vigentes** precargados (`selectinload`, 2 consultas fijas) | `200`, `404` |
| POST | `/clientes/{cliente_id}/vehiculos` | ADMIN, RECEPCION | Alta de vehículo del cliente; patente única entre vigentes | `201`, `404`, `409`, `422` |
| DELETE | `/vehiculos/{vehiculo_id}` | ADMIN, RECEPCION | Baja **lógica** (`borrado_en`); 409 si tiene órdenes abiertas | `204`, `404`, `409` |
| GET | `/mis-vehiculos` | Cualquier sesión | Vehículos del cliente dueño de la sesión (RN-17); `[]` si la cuenta no tiene ficha | `200` |

### Módulo `repuestos` (grupo protegido)

| Método | Ruta | Rol requerido | Descripción | Códigos |
|---|---|---|---|---|
| GET | `/repuestos` | ADMIN, RECEPCION, MECANICO | Listado paginado de vigentes, búsqueda `q` en descripción (parámetro ligado) | `200`, `422` |
| GET | `/repuestos/{repuesto_id}` | ADMIN, RECEPCION, MECANICO | Detalle de un repuesto vigente | `200`, `404` |
| POST | `/repuestos` | ADMIN | Alta con `stock_inicial` (default 0); deja el movimiento «Stock inicial» en el mismo UoW | `201`, `409`, `422` |
| PATCH | `/repuestos/{repuesto_id}` | ADMIN | **Sólo** `descripcion` y `precio` (`exclude_unset`); un precio distinto deja línea en el historial | `200`, `404`, `422` |
| DELETE | `/repuestos/{repuesto_id}` | ADMIN | Baja **lógica** (`borrado_en`); el código vuelve a quedar libre | `204`, `404` |
| POST | `/repuestos/{repuesto_id}/reponer` | ADMIN | Reposición: suma stock y deja el movimiento de entrada (RN-14) | `200`, `404`, `422` |
| GET | `/repuestos/{repuesto_id}/movimientos` | ADMIN | Historial de movimientos de stock, paginado | `200`, `404`, `422` |
| GET | `/repuestos/{repuesto_id}/precios` | ADMIN | Historial de cambios de precio, paginado | `200`, `404`, `422` |

Notas de contrato verificadas en el código:

- El alta de repuesto declara `stock_inicial` (`ge=0`) y **no** declara `stock`: enviar `stock` sigue siendo 422 (`extra="forbid"`). El stock sólo se escribe por el alta con `stock_inicial` y por `reponer`, y en ambos casos con su `movimiento_stock` en el mismo UoW (RN-14).
- `PATCH /repuestos/{id}` con el mismo precio (o sin `precio`) responde `200` y **no** deja línea de historial (RN-20).
- `DELETE` de repuesto y de vehículo son **bajas lógicas**: la fila se conserva con `borrado_en`; después de la baja, `GET` por id responde 404.
- El dinero viaja como **string Decimal** (`"8500.00"`), nunca como número.
- Los listados usan el envoltorio uniforme `{items, total, page, size, pages}`; `page` empieza en 1, `size` va de 1 a 100 (default 20) y una página fuera de rango es 422 con mensaje propio.
- Un `q` con comillas (`' OR '1'='1`) viaja como **parámetro ligado**: devuelve `total: 0`, no filas de más (caso C-16).

### Módulo `ordenes` (grupo protegido)

| Método | Ruta | Rol requerido | Descripción | Códigos |
|---|---|---|---|---|
| GET | `/ordenes` | ADMIN, RECEPCION, MECANICO | Listado paginado (`creada_en` desc, `id` desc); filtro `estado` validado por enum del contrato | `200`, `401`, `403`, `422` |
| GET | `/ordenes/{orden_id}` | Cualquier sesión; **CLIENTE sólo las de sus vehículos** | Detalle con vehículo, cliente, ítems con su repuesto e historial, **precargado** (3 consultas fijas) | `200`, `401`, `403`, `404` |
| POST | `/ordenes` | ADMIN, RECEPCION | Alta `PENDIENTE` con ≥ 1 ítem y sin repuestos repetidos; precio copiado y `total` calculado en el servidor; primera línea de historial en el mismo UoW | `201`, `401`, `403`, `409`, `422` |
| POST | `/ordenes/{orden_id}/iniciar` | MECANICO | `PENDIENTE → EN_REPARACION`; asigna el mecánico de la sesión + historial | `200`, `401`, `403`, `404`, `409` |
| POST | `/ordenes/{orden_id}/terminar` | ADMIN o mecánico **asignado** | `EN_REPARACION → TERMINADA`: descuenta stock, un movimiento negativo por ítem e historial; **403 antes que 409**; agenda el aviso simulado | `200`, `401`, `403`, `404`, `409` |
| POST | `/ordenes/{orden_id}/cancelar` | ADMIN, RECEPCION o **dueño** (sin `requiere_rol`, DD-06) | `PENDIENTE → CANCELADA`; el servicio evalúa identidad **antes** que estado | `200`, `401`, `403`, `404`, `409` |
| GET | `/estados-orden` | Cualquier sesión | Catálogo de sólo lectura, ordenado por `posicion`, con `es_final` visible (DD-07) | `200`, `401`, `403` |
| GET | `/mis-ordenes` | Cualquier sesión | Órdenes de los vehículos del cliente de la sesión (RN-17); `[]` si la cuenta no tiene ficha de cliente | `200`, `401`, `403`, `422` |

Notas de contrato verificadas en el código:

- El alta **sólo** acepta `vehiculo_id`, `falla` e `items[{repuesto_id, cantidad}]`. Enviar `precio_unitario`, `total`, `estado`, fecha o `mecanico_id` es **422** por `extra="forbid"` (RN-10). `items: []` y los repuestos repetidos son 422 con el campo `items` nombrado.
- Un vehículo o un repuesto inexistente o dado de baja en el alta es **409** y la orden **no queda creada**: orden, ítems e historial comparten un único UoW (RN-13, RN-16).
- `terminar` valida **todos** los ítems antes de escribir el primero: si falta stock es 409 con rollback total (stock intacto, cero movimientos, cero historial, la orden sigue `EN_REPARACION`). La carrera concurrente se apoya en el `CHECK stock >= 0` y el rollback (hoy no hay `SELECT … FOR UPDATE`).
- El orden de validación de `terminar` y `cancelar` es **404 → 403 → 409**: la identidad se evalúa antes que la máquina de estados (RN-12, SU-04).
- Un `estado` no declarado en `GET /ordenes` es **422**, no una lista vacía ni 409 (caso C-17).
- `historial_estado_orden` y `movimiento_stock` son de **sólo agregado**; el catálogo `estado_orden` no se escribe desde la API (RN-15, RN-19).
- El aviso al cliente se agenda con `BackgroundTasks` **después** de que el servicio retorna (es decir, después del commit): un 403/404/409 nunca lo agenda (DD-13 / US-026).

### Pendientes (`C-12` y `C-13`)

Ninguna de las dos agrega rutas nuevas:

| Change | Alcance |
|---|---|
| C-12 | Auditoría de lectura: conteo fijo de consultas en `GET /ordenes/{id}`, `GET /clientes/{id}` y `/mis-*` (caso C-15), aviso `BackgroundTasks` verificado post-confirmación (caso C-12) y `SQL_ECHO` habilitable |
| C-13 | Consolidación de la evidencia `.http`, `test/solo_agregado.sql` (caso C-14), matriz C-01..C-19 y verificación integral |

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

- Fija las variables de test **antes** de importar la app: `POSTGRES_DB=taller_mecanico_test` (o el que indique `TEST_POSTGRES_DB`), `SECRET_KEY` de prueba, `COOKIE_SECURE=false`, `SQL_ECHO=false`, `BCRYPT_ROUNDS=4`.
- Crea la base de test si no existe y aplica `alembic upgrade head` una sola vez por sesión.
- Re-ejecuta `seed.py` antes de cada test (sin transacciones «trucadas»).
- Expone un `httpx.AsyncClient` con `ASGITransport` y el lifespan real de la app, más el helper `login(email, password)` y fixtures de sesión por rol.

`TEST_POSTGRES_DB` permite apuntar la suite a otra base (por ejemplo `taller_mecanico_c10`). Sirve para correr dos suites en paralelo sin que los `TRUNCATE` de una pisen los datos de la otra:

```powershell
$env:TEST_POSTGRES_DB="taller_mecanico_c10"; python -m pytest test/ -q
```

Corre contra **PostgreSQL real**: sin SQLite, sin repositorios falsos, sin mocks de red y sin testcontainers. El único doble es el de `/health/ready` cuando se simula una caída de infraestructura.

**Resultado actual: 189 pruebas en verde.**

### Qué cubre cada archivo

| Archivo | Tests | Cobertura |
|---|---|---|
| `test/test_health.py` | 3 | `/health/live` (sin tocar la base), `/health/ready` 200 y 503 (caso C-01) |
| `test/test_entorno.py` | 3 | `import main`/`import app` desde la raíz, `Settings` apuntando a la base de test, esquema migrado con 13 tablas |
| `test/test_aislamiento.py` | 2 | El seed se restaura entre tests (un test ensucia y el siguiente ve el estado base) |
| `test/test_contracts.py` | 19 | `extra="forbid"`, límite de 72 bytes, contraseña multibyte, paginación y 422, envoltorio uniforme, dinero como string, `q` con comillas sin inyección (parte SQL del caso C-16), `IntegrityError` → 409, 404 propios, convención PATCH |
| `test/test_auth.py` | 19 | Registro OK/repetido (caso C-02), login sin token en el cuerpo, cookie vs Bearer (C-03), 429 con `Retry-After` sin hash (C-05), hash ficticio (RN-09), cambio de clave y RN-07 (C-04), logout, ninguna respuesta con `password_hash` |
| `test/test_rbac.py` | 18 | 401 vs 403, matriz de repuestos, claim `roles` que no autoriza, revocación inmediata (C-07), `vence_en` sin zona/pasado → 422, autoprotección (C-08), 403 por contraseña provisoria, eventos de seguridad, `/eventos` paginado |
| `test/test_clientes.py` | 14 | Alta de cliente y vehículo, documento y patente repetidos → 409, `GET /clientes/{id}` con vehículos precargados, baja con órdenes abiertas → 409, patente reutilizable tras la baja (C-19), aislamiento de `/mis-vehiculos` (RN-17), 401/403 |
| `test/test_repuestos.py` | 46 | `stock_inicial` + movimiento «Stock inicial», `stock` por PATCH → 422 (C-16), historial de precio sólo si cambió (C-18), `reponer` con movimiento, baja lógica y reutilización del código, `q` con inyección → `total: 0`, paginación de movimientos y precios, 401/403 |
| `test/test_ordenes.py` | 65 | Alta con precio copiado y `total` del servidor, repuestos repetidos y campos no declarados → 422 (RN-10), catálogo vacío → 409 (C-09), repuesto/vehículo inexistente o de baja no deja orden (C-10), stock insuficiente con rollback total (C-11), 403 antes que 409 (SU-04), iniciar/terminar/cancelar, aviso agendado sólo al confirmar (C-12), cancelar una TERMINADA → 409 (C-13), estado no declarado → 422 (C-17), detalle ajeno → 403 (C-06), `/mis-ordenes`, 401/403 |

### Evidencia `.http`

Los archivos `test/*.http` son la **evidencia pedida por la consigna**; la suite `.py` es su réplica automatizada. Se ejecutan con un cliente HTTP de IDE (REST Client de VS Code, cliente HTTP de JetBrains) contra la app levantada y con el seed cargado.

| Archivo | Contenido |
|---|---|
| `test/contracts.http` | Contratos, paginación, 409/404 y validaciones (C-06). Abre con un login de ADMIN para que las peticiones caigan en el grupo protegido |
| `test/auth.http` | Registro, login, cookie vs Bearer, 429, `/auth/yo`, cambio de clave y logout (C-07) |
| `test/rbac.http` | 401/403, matriz de roles, revocación inmediata, `vence_en`, autoprotección, contraseña provisoria y eventos (C-08) |
| `test/clientes.http` | Alta de cliente y vehículo, patente repetida tras la baja, baja con orden abierta y aislamiento de `/mis-vehiculos` (C-09) |
| `test/repuestos.http` | Casos B-01 a B-04: stock no editable, precio historiado, PATCH sin cambio sin línea, RECEPCION → 403 en ADMIN; más reposición, historiales y baja lógica (C-10) |
| `test/ordenes.http` | 29 bloques: catálogo, listado y filtro, detalle completo, alta con total del servidor, 422 del contrato, vehículo/repuesto inexistente, stock insuficiente con rollback (C-11), 403 antes que 409 (SU-04), cancelar con dueño/ajeno/repetida (C-06, C-13), iniciar+terminar y aviso post-confirmación (A-01 a A-04, C-12), `/mis-ordenes` |

### Mapeo de los casos C-01 a C-19

| Caso | Qué verifica | Estado |
|---|---|---|
| C-01 | `/health/live` y `/health/ready` | ✓ `test_health.py` |
| C-02 | Registro con documento repetido → 409 sin apropiarse de la ficha | ✓ `test_auth.py` |
| C-03 | Cookie vs `Authorization: Bearer` → 401 | ✓ `test_auth.py` |
| C-04 | El cambio de contraseña invalida el token anterior | ✓ `test_auth.py` |
| C-05 | 5 fallos → 429 con `Retry-After` | ✓ `test_auth.py` |
| C-06 | Orden ajena → 403 | ✓ `test_ordenes.py` (detalle y cancelar) |
| C-07 | Revocación de rol con efecto inmediato | ✓ `test_rbac.py` |
| C-08 | Autoprotección del último ADMIN → 409 | ✓ `test_rbac.py` |
| C-09 | Catálogo de estados vacío → 409 | ✓ `test_ordenes.py` |
| C-10 | Repuesto inexistente no deja la orden | ✓ `test_ordenes.py` (también vehículo inexistente o de baja) |
| C-11 | Stock insuficiente → rollback total | ✓ `test_ordenes.py` |
| C-12 | Aviso post-respuesta sólo si se confirmó | ◐ `test_ordenes.py` (agendado al confirmar, no agendado en 409); la verificación de temporalidad estricta queda en `C-12` |
| C-13 | Cancelar una orden TERMINADA → 409 | ✓ `test_ordenes.py` |
| C-14 | `UPDATE`/`DELETE` rechazados en las tablas de sólo agregado | ☐ pendiente: `test/solo_agregado.sql` **no existe todavía** (`C-13`); se ejercita con `psql` |
| C-15 | Detalle con 2 y 4 ítems usa el mismo número de consultas | ☐ pendiente (`C-12`): las precargas ya están, falta el conteo automatizado |
| C-16 | `stock` por PATCH → 422 e inyección SQL en `q` | ✓ `test_repuestos.py` |
| C-17 | Estado no declarado → 422 | ✓ `test_ordenes.py` |
| C-18 | PATCH sin cambio de precio no deja línea | ✓ `test_repuestos.py` |
| C-19 | Patente reutilizable después de la baja | ✓ `test_clientes.py` |

Quedan **17 casos cubiertos** (C-01 a C-11, C-13 y C-16 a C-19), **C-12 parcial** (el aviso ya se agenda sólo al confirmar; falta auditarlo con la respuesta en curso) y **2 pendientes** (C-14 y C-15), ambos entregables de `C-12` y `C-13`. La matriz definitiva —`.http` + prueba automatizada por caso— es entregable de `C-13`.

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
- **Changes cerrados:** `openspec/changes/archive/<fecha>-<change>/` (C-01 a C-11 ya archivados).
- **Capacidades vigentes:** `openspec/specs/<capacidad>/spec.md` (33 capacidades).
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

- **No hay auditoría de N+1 ni de `BackgroundTasks`** (`C-12`): `/ordenes/{id}`, `/clientes/{id}`, `/mis-vehiculos` y `/mis-ordenes` ya precargan con un número fijo de consultas, pero falta el conteo automatizado que pruebe que 2 y 4 ítems usan las mismas consultas (caso C-15). El aviso al cliente ya se agenda con `BackgroundTasks` sólo después del commit y hay tests de que un 409 no lo agenda; falta verificar que corra con la respuesta ya emitida (caso C-12).
- **Falta la evidencia de entrega** (`C-13`): `test/solo_agregado.sql` (caso C-14) no existe; la matriz definitiva C-01..C-19 (`.http` + prueba automatizada) y la consolidación de los `.http` quedan para ese change.

**Deuda técnica observada en el código**

- **`session.execute()` genera `DeprecationWarning` de SQLModel** en `app/core/repository.py:84` (el `count`) y en `app/modules/usuarios/repository.py:133,155,184` (conteos y `scalar_one`/`one`), además de `app/modules/health/router.py:17`. Son usos legítimos de `Row`/escalar, pero con 189 pruebas la suite emite 434 warnings. Si se migran a `exec()`, hay que revisar que no cambien los tipos de retorno.
- **`/health/ready` devuelve `str(e)` en el `detail` del 503.** Eso puede exponer texto interno del motor (host, usuario, mensaje de conexión) y va contra el espíritu de RN-18, que prohíbe filtrar detalles de la infraestructura. Lo correcto sería un mensaje fijo y el detalle sólo en el log.
- **Sin bloqueo de fila en el stock.** `POST /repuestos/{id}/reponer` y el descuento de `terminar` leen y escriben `stock` sin `SELECT ... FOR UPDATE`: la concurrencia está fuera de alcance (capítulo 7), pero dos reposiciones o dos terminaciones simultáneas pueden perder una actualización. La transacción de `terminar` se apoya en el `CHECK stock >= 0` y en el rollback total (design D8 de C-11).
- **La documentación describe el objetivo completo, no sólo lo implementado.** `knowledge-base/02_descripcion_general.md` lista todos los endpoints (incluidos los de `C-09` a `C-13`) y `knowledge-base/08_arquitectura_propuesta.md` muestra la estructura de módulos completa. La estructura real de hoy está en [Estructura de directorios](#estructura-de-directorios) y la lista real de rutas en [Endpoints](#endpoints).
- **`app/modules/ordenes/models.py` documenta el módulo como `ordenes`, pero la KB lo llama `ordeneses`** en una tabla (`04_modelo_de_datos.md`, §Dominios). Es una errata de la KB; manda el nombre del código.
- **`practica-parcial-prog-main/`** es un directorio **vacío** residual en la raíz; no forma parte del proyecto.
- **Sin entorno reproducible más allá de `requirements.txt`.** No hay `pyproject.toml`, `Dockerfile` ni lockfile: las versiones son mínimas (`>=`) y se instalan desde `requirements.txt`. Está alineado con el stack cerrado de la consigna (sin Docker), pero implica que dos instalaciones en fechas distintas pueden resolver versiones distintas.
- **Sin verificación de concurrencia.** Está explícitamente fuera de alcance (capítulo 7): dos terminaciones simultáneas de órdenes pueden leer el mismo stock (actualización perdida permitida por el nivel de aislamiento por defecto).
