# Tasks

## 1. Scaffolding & Configuration

- [x] 1.1 Create directory structure (`app/core/`, `app/modules/health/`, `migrations/versions/`, `test/`) and `requirements.txt` with closed stack requirements. Verify structure and requirements file.
- [x] 1.2 Implement `app/core/config.py` with `Settings` class using `pydantic-settings`. Verify settings load correctly from environment / `.env`.
- [x] 1.3 Create `env.example` file with configuration keys. Verify file presence.

## 2. Core Persistence & Base Utilities

- [x] 2.1 Implement `app/core/database.py` with async engine, sessionmaker, `get_session` via `app.state`, and `expire_on_commit=False`. Verify session dependency functions correctly.
- [x] 2.2 Implement core base utilities (`security.py`, `dependencies.py`, `repository.py`, `paginacion.py`, `unit_of_work.py`). Verify modules compile and import successfully.

## 3. Application Entrypoint & Health Checks

- [x] 3.1 Implement `app/modules/health/router.py` with `GET /health/live` and `GET /health/ready`. Verify health endpoints behavior.
- [x] 3.2 Implement `main.py` with FastAPI app and lifespan handler storing engine/sessionmaker in `app.state`. Verify application starts and health checks respond successfully.

---

## Notas de cierre (2026-10-27)

Correcciones aplicadas después de la verificación post-archivo, para que lo declarado en estas tasks coincida con lo que realmente quedó en el repositorio.

### 1.1 — Directorios vacíos versionados

Git no versiona carpetas vacías, así que `migrations/versions/` y `test/` se perdieron al clonar/commitear. Se recrearon y ahora persisten en el repo con un `.gitkeep`:

```text
migrations/
  versions/
    .gitkeep      ← destino de las migraciones (lo consume Alembic en C-04)
test/
  .gitkeep        ← suite pytest (la llena C-05)
```

`migrations/` queda en pie sin `alembic.ini` ni `env.py` a propósito: el scaffolding de Alembic (plantilla asincrónica) es alcance de `C-04 migrations-and-seed`, no de `C-01`.

### 2.2 — Alcance real de las utilidades base

Los módulos de `app/core/` se crearon en `C-01` como **cascarones compilables** (contratos mínimos que `main.py` y `health` necesitan). Su implementación definitiva —firmas exactas de `BaseRepository`/`SoftDeleteRepository`, semántica del `UnitOfWork`, reglas de `paginacion` y primitivas de `security`— es alcance explícito de `C-02 core-persistence`.

Consecuencia documental: la frase "Implement core base utilities" de 2.2 describe la creación de los módulos, no su especificación final. Quien lea este change debe tomar `C-02` como la fuente de verdad de esa capa.

### 3.1 — Corrección en `GET /health/ready`

El handler usaba `session.exec(...)` sobre un `AsyncSession` de SQLAlchemy: ese método pertenece a la sesión de SQLModel, no a la de SQLAlchemy, por lo que el endpoint devolvía **503 siempre** (contra el escenario "readiness con base sana → 200" de la spec). Se corrigió a:

```python
await session.execute(text("SELECT 1"))
```

Comportamiento esperado ahora: 200 con base alcanzable, 503 con `detail` propio cuando la consulta falla.

### 4. `requirements.txt` — `sqlalchemy[asyncio]`

`sqlalchemy>=2.0.0` no alcanzaba para levantar el proyecto: desde SQLAlchemy 2.1 `greenlet` dejó de instalarse por defecto y su módulo asíncrono lo exige, así que `import app.core.database` moría con `ModuleNotFoundError: greenlet`. Se corrigió el requisito a `sqlalchemy[asyncio]>=2.0.0` (extra oficial de SQLAlchemy, no una biblioteca ajena al stack). Verificado en `.venv` limpio: instalación + import de `app.core.database` sin error.

### 5. Entorno de verificación

No había entorno virtual ni dependencias instaladas, así que ninguna comprobación de `C-01` pudo ejecutarse realmente. `C-02` creó `.venv/` (ignorado por git) y verificó con él; los smoke checks quedaron fuera del repositorio, en el temporal del sistema.
