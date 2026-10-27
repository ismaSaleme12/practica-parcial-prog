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
