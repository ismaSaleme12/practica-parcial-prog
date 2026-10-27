# Proposal

## Why

`C-04` dejó la base migrada y sembrada, pero **nada la ejercita**: `test/` sólo tiene un `.gitkeep` y cada change futuro tendría que inventar su propio arnés. La consigna pide PostgreSQL real y handlers `async`, así que un `TestClient` síncrono con sqlite no sirve: hace falta un andén que levante la app tal como corre en producción, contra una base de test propia, y que deje el estado conocido del seed antes de cada prueba.

Sin este change, `C-06` no puede entregar sus tests pytest y `C-07` en adelante no tienen dónde apoyarse. Es el andén de toda la FASE 2 a 6.

## What Changes

- **`requirements.txt`**: bloque `# --- testing (adicional a la consigna) ---` con `pytest>=8`, `pytest-asyncio>=0.24` y `httpx>=0.27`. Es la **única** adición al stack cerrado del PDF: sin Redis, sin Docker, sin ORM alternativo, sin mocks de red ni repos falsos.
- **`test/pytest.ini`**: `asyncio_mode = auto`, un solo bucle de eventos para la corrida, y `pythonpath = ..` + `testpaths = .` porque el rootdir queda en `test/`. La estructura obligatoria de la raíz no cambia: todo el andén vive dentro de `test/`.
- **`test/conftest.py`**:
  - fija las variables de test (`POSTGRES_DB=taller_mecanico_test`, `SECRET_KEY` de prueba, `COOKIE_SECURE=false`, `SQL_ECHO=false`, `BCRYPT_ROUNDS=4`) **antes** de importar la app;
  - fixture session-scoped que crea la base de test si no existe y aplica `alembic upgrade head` una sola vez;
  - fixture function-scoped autouse que restaura el estado base re-corriendo `seed.py` (vacía y recarga) por test;
  - fixture `client` con `httpx.AsyncClient` + `ASGITransport(app)` y el lifespan real (`app.router.lifespan_context`), sin `asgi-lifespan`;
  - helper `login(email, password)` y fixtures `token_admin` / `token_recepcion` / `token_mecanico` / `token_cliente`, listas para `C-07`.
- **Smoke tests**: `GET /health/live` → 200, `GET /health/ready` → 200 contra PostgreSQL real y 503 cuando la base no contesta (caso C-01), más guardas de entorno (imports desde la raíz, base de test, esquema migrado) y una prueba de que el estado se restaura entre tests.
- **Convención**: de acá en más cada change agrega su `test/test_<change>.py` como réplica de sus `.http`. Los `.http` siguen siendo la evidencia que pide la consigna; la suite los automatiza.

## Capabilities

### New Capabilities

- `test-infrastructure`: el arnés de pruebas — cómo se fija el entorno, cómo se crea y migra la base de test, cómo se restaura el estado del seed, cómo se ejercita la app asincrónica con un cliente ASGI y cómo se autentican los roles.

### Modified Capabilities

- Ninguna. La aplicación, el esquema y el seed no cambian; `C-05` sólo agrega el andén que los prueba.

## Impact

- **Código**: `requirements.txt`, `test/pytest.ini`, `test/conftest.py`, `test/test_health.py`, `test/test_entorno.py`, `test/test_aislamiento.py`.
- **Base de datos**: crea y migra `taller_mecanico_test` (desechable). **No toca** `taller_mecanico`: una prueba de entorno verifica que `Settings` apunte a la base de test.
- **Dependencias**: única adición permitida al stack cerrado (`pytest`, `pytest-asyncio`, `httpx`). Nada de `asgi-lifespan`, `factory-boy`, `respx`, `pytest-xdist`, `testcontainers`.
- **Habilitado**: `C-06` (sus tests pytest) y `C-07` en adelante (fixtures `client`/`login`).
- **Operación**: corrida estándar `python -m pytest test/ -v` **desde la raíz del repo**; la suite no es segura para dos procesos simultáneos sobre la misma base de test.
