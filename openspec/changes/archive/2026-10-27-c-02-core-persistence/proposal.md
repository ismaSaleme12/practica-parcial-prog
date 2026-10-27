# Proposal

## Why

`C-01` dejó `app/core/` como cascarones compilables: `BaseRepository` todavía delega en `session.exec()` sobre una sesión de SQLAlchemy (que no expone ese método) y el `UnitOfWork`, la paginación y las primitivas de seguridad no tienen la semántica que exigen las reglas duras del proyecto. Sin esta capa cerrada, cualquier módulo de dominio (`C-03` en adelante) heredaría el defecto y lo replicaría en cada repositorio, servicio y endpoint.

Este change implementa el **Ejercicio 6** de la consigna (repositorios, Unit of Work y utilidades transversales) y fija los invariantes que el resto del sistema da por sentados: ningún repositorio confirma, ningún servicio construye su UoW, la sesión se comparte entre los repositorios del UoW, y la paginación siempre devuelve `{items, total, page, size, pages}` con `total` calculado con los mismos filtros que la página.

## What Changes

- **`app/core/database.py`**: la fábrica de sesiones pasa a instanciar la sesión de **SQLModel** (`sqlmodel.ext.asyncio.session.AsyncSession`, subclase de la de SQLAlchemy) para que `session.exec(select(Model))` devuelva instancias del modelo; se mantiene `expire_on_commit=False` y la entrega por `app.state`.
- **`app/core/repository.py`**: `BaseRepository[T]` con contrato explícito (`get_by_id`, `get_all`, `list_page`, `count`, `add`, `update`, `delete`, `refresh`) donde `add`/`update`/`delete`/`soft_delete` hacen **solo `flush()`**, nunca `commit()`; `SoftDeleteRepository[T]` filtra `borrado_en IS NULL`, agrega `get_by_id_including_deleted` y `soft_delete`.
- **`app/core/unit_of_work.py`**: `UnitOfWork` como gestor de contexto asincrónico que **confirma al salir sin excepción**, **revierte con excepción** y **nunca cierra la sesión** (no la creó); expone `session` y un helper `repositorio()` para componer repositorios sobre esa misma sesión.
- **`app/core/paginacion.py`**: `PageParams` (`page` ≥ 1, `size` 1–100, default 20) y `Page[T]` (`{items, total, page, size, pages}`) con `total` calculado por el repositorio con los mismos filtros; página fuera de rango → **422 con mensaje propio** («La página N no existe: hay M»).
- **`app/core/security.py`**: primitivas bcrypt (`hash_password`/`verify_password`) ejecutadas **fuera del bucle** (`asyncio.to_thread`) bajo un semáforo **configurable**, costo desde `Settings`; y JWT (`crear_token`/`verificar_token`) con `sub`, `iat`, `exp` y roles vigentes, `iat` **sin truncar** (RN-07).
- **`app/core/config.py`**: nueva variable `BCRYPT_MAX_CONCURRENT_HASHES` (default 4) y `env.example` actualizado. No se agregan dependencias: todo cae dentro del stack cerrado.
- **Documentación de la regla**: comentario explícito en `repository.py`/`unit_of_work.py` de que ningún repositorio confirma y ningún servicio construye su UoW.

## Capabilities

### New Capabilities
- `core-persistence`: contrato de repositorios (base y borrado lógico), Unit of Work como único punto de confirmación/reversión y garantía de sesión compartida sin cerrarla.
- `list-pagination`: envoltorio uniforme de listados con validación de `page`/`size`, cálculo de páginas y error 422 propio para páginas fuera de rango.
- `security-primitives`: hash/verificación bcrypt fuera del bucle y emisión/verificación de JWT con `sub`, `iat` sin truncar y `exp`, sin endpoints todavía.

### Modified Capabilities
- Ninguna. `foundation-setup` no cambia de requisitos: el ajuste del endpoint `/health/ready` (`execute` en lugar de `exec`) y el cambio de clase de sesión alinean la implementación con lo que la spec ya exige.

## Impact

- **Código**: `app/core/database.py`, `app/core/repository.py`, `app/core/unit_of_work.py`, `app/core/paginacion.py`, `app/core/security.py`, `app/core/config.py`, `env.example`; `main.py` y `app/modules/health/router.py` solo en el tipo de sesión usado.
- **Dependencias**: ninguna nueva (bcrypt, PyJWT, SQLModel y SQLAlchemy ya están en `requirements.txt`).
- **Habilitado**: `C-03 domain-models` (los repositorios ya pueden tipar modelos), `C-06 contracts-and-errors` (paginación lista para los contratos de listado) y `C-07 auth` (primitivas de hash y token).
