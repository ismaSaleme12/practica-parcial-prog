# Design

Ver `proposal.md` (Why) y las specs `core-persistence`, `list-pagination` y `security-primitives` (requisitos). Este documento explica **cómo** se cumple ese contrato.

## Context

`C-01` dejó `app/core/` como cascarones: `main.py` arma la fábrica de sesiones con la `AsyncSession` de SQLAlchemy, `BaseRepository` llama a `session.exec()` (método que existe en la sesión de SQLModel, no en la de SQLAlchemy) y `UnitOfWork`, `Page` y `security.py` no tienen todavía la semántica que fijan las reglas duras. `C-02` cierra esa capa **antes** de que exista un solo modelo, para que ningún módulo de dominio herede el defecto.

Restricciones que condicionan el diseño:

- Stack cerrado: SQLModel + SQLAlchemy 2.0 async + asyncpg, sin dependencias nuevas.
- `AGENTS.md`: ningún repositorio confirma; ningún servicio construye su UoW; el UoW no cierra la sesión; `expire_on_commit=False`; dinero con `Decimal`; sin lazy loading.
- Todavía no hay modelos de dominio (llegan en `C-03`), así que la capa base debe tipar genéricamente y no importar nada de `app/modules/`.

## Goals / Non-Goals

**Goals:**
- Un contrato único de repositorio y de UoW que todos los módulos de dominio hereden sin reescribirlo.
- Confirmación en un solo punto (`UnitOfWork`) y sesión compartida entre repositorios.
- Paginación reutilizable con `total` coherente con los filtros.
- Primitivas criptográficas listas para `C-07 auth`, sin endpoints.
- Que `import app.core.*` y `py_compile` funcionen sin base de datos levantada.

**Non-Goals:**
- Endpoints de autenticación, cookie `access_token`, `requiere_rol` y hash ficticio del login → `C-07`/`C-08`.
- Traducción de `IntegrityError` a 409 y contratos de error → `C-06`.
- Modelos, migraciones y `seed.py` → `C-03`/`C-04`.
- Suite de tests automatizada → `C-05` (aquí solo se verifica compilación e import).

## Decisions

### D1 — La sesión es la de SQLModel, no la de SQLAlchemy

**Decisión**: `main.py` construye `async_sessionmaker(..., class_=SQLModelAsyncSession)` y `database.py`/repositorios tipan con `sqlmodel.ext.asyncio.session.AsyncSession`.

**Por qué**: es una subclase de la sesión de SQLAlchemy (no cambia nada del motor ni del pool) y agrega `exec()`, que devuelve instancias del modelo directamente al hacer `select(Model)`. Con la sesión de SQLAlchemy habría que escribir `(await session.execute(stmt)).scalars().all()` en cada repositorio.

**Alternativas**: (a) sesión de SQLAlchemy + `.scalars().all()` en todos lados — más verboso y repetitivo; (b) mezclar ambas — dos tipos de sesión en el proyecto, peor. Se descartan.

**Nota**: `health/ready` usa `session.execute(text("SELECT 1"))`, que funciona en ambas y no depende de `exec()`.

### D2 — `add`/`update` hacen `flush()` y nada más

**Decisión**: `add`, `update`, `delete` y `soft_delete` hacen `flush()` y devuelven la entidad; **no** hacen `commit()` ni `refresh()` automático. El refresco queda como método explícito (`refresh`) para quien necesite valores generados por la base.

**Por qué**: el `commit` es del UoW (regla dura) y el `refresh` es un `SELECT` extra: hacerlo implícito en cada escritura infla el número de consultas y puede arrastrar relaciones, justo lo que la regla de "carga anticipada con número fijo de consultas" quiere evitar. Con `flush()` los identificadores ya están poblados; si un valor lo genera la base (`created_at`, defaults), el servicio pide `refresh` a propósito y ese coste queda visible.

**Alternativas**: refrescar siempre (más cómodo, más consultas, menos predecible) — descartado.

### D3 — `count` con los mismos filtros, en el repositorio

**Decisión**: `BaseRepository.count(*filtros)` arma `select(func.count()).select_from(model).where(*filtros)` y `list_page(params, *filtros)` usa **la misma tupla de filtros** para la página y para el total, devolviendo un `Page[T]`.

**Por qué**: el requisito de la consigna es explícito ("`total` cuenta con los mismos filtros que la página"). Tener una sola función que recibe los filtros una vez evita el bug clásico de contar la tabla entera. Todas las condiciones viajan como expresiones SQLModel ligadas (nunca SQL concatenado).

**Consultas por listado**: 2 fijas (count + página), independientes del tamaño de la página.

### D4 — `PageParams` valida con mensaje propio y `Page` calcula `pages`

**Decisión**: `PageParams` es un `BaseModel` con `page: int = 1` y `size: int = 20`, validado en `model_validator(mode="after")`; las violaciones lanzan `HTTPException(422)` con mensaje propio. `Page.create(items, total, params)` calcula `pages = ceil(total / size)` y lanza 422 con «La página N no existe: hay M» cuando `page > pages` (con `pages > 0`; un listado vacío devuelve `pages: 0` y `items: []`).

**Por qué**: la consigna pide 422 con mensaje propio y este es el punto único donde se decide; si se dejara a los `Field(ge=1, le=100)` de Pydantic, el mensaje sería el genérico de FastAPI. `Page.create` centraliza el cálculo para que ningún router repita la fórmula.

**Trade-off aceptado**: `app/core/` importa `HTTPException` de FastAPI. Se acepta en este proyecto (es una API FastAPI pura y el mensaje propio es requisito), y queda aislado en este módulo.

### D5 — El UoW confirma al salir y no cierra la sesión

**Decisión**: `UnitOfWork(session)` es un gestor de contexto asincrónico: en `__aexit__` revierte si hubo excepción, si no confirma, y si el `commit` falla revierte y **relanza**. No crea, no cierra ni reemplaza la sesión; expone `session` y `repositorio(cls, model)` para componer repositorios sobre esa misma sesión.

**Por qué**: RN-02, RN-13 y RN-20 exigen atomicidad multi-repositorio; la sesión la abre y la cierra el dueño de la petición (la dependencia de sesión), no el UoW. El UoW concreto de cada módulo (`app/modules/<módulo>/unit_of_work.py`) heredará y solo declarará sus repositorios.

**Alternativas**: que el UoW abra su propia sesión desde la fábrica — rompe la regla dura ("el router lo arma con una dependencia y se lo pasa abierto") y duplica conexiones por petición. Descartado.

**Explícitamente fuera**: traducir `IntegrityError` a 409. Eso es `C-06`; aquí el error se propaga tal cual para no fijar el contrato de errores antes de tiempo.

### D6 — Semáforo de bcrypt configurable y token con `sub`/`iat`/`exp`

**Decisión**: `hash_password`/`verify_password` corren en `asyncio.to_thread` bajo un `asyncio.Semaphore` cuyo tamaño sale de `Settings.BCRYPT_MAX_CONCURRENT_HASHES` (nueva variable, default 4); `verify_password` atrapa cualquier fallo de bcrypt y devuelve `False`. `crear_token(sub, roles, expires_delta=None)` firma HS256 con `iat`/`exp` como `datetime` con zona (sin truncar) y `verificar_token` valida con `require=["sub", "exp", "iat"]`, devolviendo `None` ante cualquier `PyJWTError`.

**Por qué**: DD-08 pide que bcrypt no bloquee el bucle y que el costo salga de configuración; RN-07 pide `iat` sin truncar para poder comparar contra `password_cambiada_en`. Devolver `None` en vez de excepción deja al llamador (`C-07`) decidir el 401.

**Trade-off aceptado**: el semáforo limita concurrencia pero no la encola con timeout; bajo saturación las peticiones esperan. Se documenta en el código.

## Risks / Trade-offs

- **Cambiar la clase de sesión afecta a `main.py` y al tipo de `get_session`** → se cambia en el mismo commit que el resto de la capa base; `health/ready` queda con `execute()` y no depende del cambio. Verificación: `py_compile` + import de `main` sin base levantada.
- **Quitar el `refresh()` implícito puede sorprender a quien espere defaults de la base tras `add`** → método `refresh` explícito + comentario en el docstring del repositorio; los modelos de `C-03` usarán `default` en Python para los campos que el contrato necesita de inmediato.
- **`count` + página con filtros desincronizados** → una sola función (`list_page`) recibe los filtros y los aplica a ambas consultas; queda cubierto por el caso de test de paginación de `C-13`.
- **`asyncio.Semaphore` creado a nivel de módulo** → en Python 3.10+ no está atado a un loop hasta el primer `await`; correcto para un servidor con un solo loop.
- **Sin tests automatizados todavía** (la infra llega en `C-05`) → la verificación de este change es compilación, import y smoke checks con sesión falsa (repositorios/UoW), TestClient (paginación vía dependencia y health checks) y bcrypt/JWT reales. La comprobación contra PostgreSQL queda para la suite de `C-05`/`C-13`.
- **`greenlet` faltaba en `requirements.txt`** → desde SQLAlchemy 2.1 el módulo asíncrono no se puede importar sin él; se corrigió a `sqlalchemy[asyncio]` en este change (extra oficial, no una dependencia nueva del stack) y se documentó en las notas de `C-01`.
- **El nombre del status 422 cambió en Starlette** (`UNPROCESSABLE_ENTITY` → `UNPROCESSABLE_CONTENT`) → `paginacion.py` usa el literal `422` para no quedar atado a ninguna versión y no emitir `DeprecationWarning` en la más nueva.
- **`SECRET_KEY` corta** → PyJWT advierte por debajo de 32 bytes (RFC 7518); `env.example` lo deja explícito y la clave sigue siendo obligatoria, sin default.
- **`select` de SQLAlchemy con `session.exec` devuelve `Row`, no el modelo** → apareció al verificar contra PostgreSQL real (`AttributeError: nombre`): `exec` decide por el tipo de sentencia, y sólo el `select` de SQLModel produce `SelectOfScalar`. `repository.py` importa `select` de **SQLModel** y la regla quedó como restricción dura en `AGENTS.md`/`CLAUDE.md`.

## Migration Plan

1. Ajustar `config.py` + `env.example` (`BCRYPT_MAX_CONCURRENT_HASHES`).
2. Cambiar la clase de sesión en `main.py` y el tipo en `database.py`.
3. Reescribir `repository.py`, `unit_of_work.py` y `paginacion.py`.
4. Reescribir `security.py` con las firmas definitivas.
5. Verificar `py_compile` e import de `main`; actualizar `CHANGES.md` y archivar el change.

Rollback: no hay migraciones ni datos; revertir los archivos de `app/core/` y `main.py` deja el repositorio en el estado de `C-01`.
