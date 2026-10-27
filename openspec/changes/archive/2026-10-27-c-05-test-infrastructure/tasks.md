# Tasks

## 1. Dependencias y configuración del andén

- [x] 1.1 Agregar a `requirements.txt` el bloque `# --- testing (adicional a la consigna) ---` con `pytest>=8`, `pytest-asyncio>=0.24` y `httpx>=0.27`, con el comentario de que es la única adición al stack cerrado. Verificación: el archivo conserva las ocho dependencias de la consigna y no agrega ninguna otra (`asgi-lifespan`, `factory-boy`, `respx`, `pytest-xdist` y `testcontainers` no aparecen).
- [x] 1.2 Crear `test/pytest.ini` con `asyncio_mode = auto`, `asyncio_default_test_loop_scope = session`, `asyncio_default_fixture_loop_scope = session`, `pythonpath = ..` y `testpaths = .`. Verificación: `python -m pytest test/ -v` desde la raíz reporta `rootdir: ...\test`, `configfile: pytest.ini` y `asyncio_default_*_loop_scope=session`.
- [x] 1.3 Verificar empíricamente el rootdir y corregir el `pythonpath`. Verificación: con `pytest test/ -q -o pythonpath=.` el arranque falla con `ModuleNotFoundError: No module named 'seed'`; con `pythonpath = ..` pasan `pytest test/` y `python -m pytest test/` (decisión y evidencia en `design.md` D1).

## 2. `conftest.py` — entorno y base de datos

- [x] 2.1 Fijar las variables de test **antes** de importar la app: `POSTGRES_DB=taller_mecanico_test`, `SECRET_KEY` de prueba, `COOKIE_SECURE=false`, `SQL_ECHO=false`, `BCRYPT_ROUNDS=4`. Verificación: `test_entorno.py::test_las_variables_de_test_ganan_sobre_el_entorno_local` pasa y `settings.POSTGRES_DB` es la base de test aun con `POSTGRES_DB=taller_mecanico` en `.env`.
- [x] 2.2 Fixture session-scoped `base_migrada`: crear la base de test con asyncpg contra la base `postgres` si no existe y aplicar `alembic upgrade head` una sola vez, con `script_location` absoluto. Verificación: se dropeó `taller_mecanico_test` y la corrida siguiente la recreó y migró sola (8 passed); la segunda corrida no vuelve a migrar.
- [x] 2.3 Fixture function-scoped autouse `base_limpia`: `await seed.main()` antes de cada test (TRUNCATE + recarga, sin transacciones revertidas ni segundas sesiones). Verificación: `test_aislamiento.py` ensucia `repuesto.stock` en un test y el siguiente vuelve a leer `10` del seed.
- [x] 2.4 Fixture `motor` que expone `app.state.engine` para inspecciones con SQL crudo. Verificación: `test_entorno.py::test_el_esquema_de_test_esta_migrado` cuenta 13 tablas de dominio en `information_schema` usando ese motor.

## 3. `conftest.py` — cliente ASGI y autenticación

- [x] 3.1 Fixture `app_viva`: abrir `app.router.lifespan_context(app)` para que motor, fábrica de sesiones y hash ficticio existan durante el test y se liberen al terminar. Verificación: `/health/ready` responde 200 contra PostgreSQL real (necesita el motor del lifespan).
- [x] 3.2 Fixture `client`: `httpx.AsyncClient` + `ASGITransport(app)`, sin `TestClient` ni `asgi-lifespan`. Verificación: los tres tests de `test_health.py` usan `client` y la suite no importa `asgi_lifespan` ni `starlette.testclient`.
- [x] 3.3 Helper `login(email, password="secreto123")`: `POST /auth/login`, exige 200 y devuelve la cookie `access_token`, que queda también en el tarro del cliente. Verificación: el helper está documentado y su contrato coincide con `02_descripcion_general.md` (cookie HttpOnly, sin token en el cuerpo).
- [x] 3.4 Fixtures `token_admin`, `token_recepcion`, `token_mecanico` y `token_cliente` con los usuarios del seed. Verificación: existen y se resuelven sólo cuando se piden (se ejercitan desde `C-07`); `pytest --fixtures test/` las lista.

## 4. Smoke tests

- [x] 4.1 `test/test_health.py`: `GET /health/live` → 200 `{"status": "alive"}` sin tocar la base. Verificación: el test pasa.
- [x] 4.2 `test/test_health.py`: `GET /health/ready` → 200 `{"status": "ready", "database": "connected"}` contra PostgreSQL real. Verificación: el test pasa.
- [x] 4.3 `test/test_health.py`: `GET /health/ready` → 503 cuando la base no contesta, con `dependency_overrides` de `get_session` y limpieza en `finally`. Verificación: el test pasa y es el único doble del andén.
- [x] 4.4 `test/test_entorno.py`: guardas de `import app`/`import main` desde la raíz, de la base de test y del esquema migrado. Verificación: los tres tests pasan.

## 5. Verificación

- [x] 5.1 TDD: escribir primero `pytest.ini` y los tests (rojo: `fixture 'client' not found`, `assert 'taller_mecanico' == 'taller_mecanico_test'`) y después el `conftest.py` mínimo para ponerlos en verde. Verificación: la corrida previa al `conftest.py` falla y la posterior pasa.
- [x] 5.2 Corrida completa desde la raíz: `python -m pytest test/ -v`. Verificación: **8 passed** del andén en ~2,2 s; compartiendo `test/` con los tests de `C-06` en paralelo, la corrida completa da **26 passed**.
- [x] 5.3 La suite no toca la base de desarrollo. Verificación: después de las corridas, `taller_mecanico` conserva sus 13 tablas y los conteos del seed (7 usuarios, 4 repuestos, 2 órdenes, 4 estados).

## 6. Documentación y cierre

- [x] 6.1 Registrar en `design.md` las decisiones y sus trade-offs, en especial la de `pythonpath`/rootdir (D1) con la evidencia del fallo, el bucle único (D2) y el seed por test (D5). Verificación: `design.md` incluye D1 a D8 y la sección de riesgos.
- [x] 6.2 Dejar escrita la convención `test/test_<change>.py` como réplica de los `.http` (los `.http` siguen siendo la evidencia de la consigna). Verificación: `proposal.md` y `test/conftest.py` la mencionan.

## Workflow follow-up

- Revisar los artefactos y archivar con `/opsx:archive 2026-10-27-c-05-test-infrastructure` cuando el usuario lo pida (el orquestador marca `C-05` en `CHANGES.md` y commitea).
- Después del archivo, `C-06` puede escribir sus tests pytest y `C-07` usar `client`/`login` y las fixtures de rol.
