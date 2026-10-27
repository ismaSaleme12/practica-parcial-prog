# Design

## Context

La app es asincrónica de punta a punta: el motor y la fábrica de sesiones nacen en el `lifespan` (`app.state`), los handlers son `async def` y bcrypt corre con `asyncio.to_thread` bajo un semáforo global. La consigna exige PostgreSQL real (índices únicos parciales, CHECK, disparadores de sólo agregado), así que el andén tiene que probar **la base de verdad**, no un sustituto.

Restricciones que mandan sobre el diseño:

- La estructura de la raíz es obligatoria (consigna): el andén vive dentro de `test/`, no se agregan archivos de configuración en la raíz.
- El stack está cerrado: sólo se suma el bloque de testing del change. Nada de `asgi-lifespan`, `factory-boy`, `respx`, sqlite ni testcontainers.
- Las reglas duras del proyecto (nunca `create_all`, ninguna credencial en el repo, `Decimal`/`timestamptz`, etc.) valen también para los tests.

## Goals / Non-Goals

**Goals**

- `python -m pytest test/ -v` desde la raíz, en verde, contra `taller_mecanico_test`.
- La base de test se crea si falta y se migra **una sola vez** por corrida, con la misma ruta que producción (`alembic upgrade head`).
- Cada test arranca del estado determinista de `seed.py`.
- La app se ejercita con su lifespan real y un cliente HTTP asincrónico.
- `login()` y las fixtures por rol quedan listas para que `C-07` las use sin tocar el andén.

**Non-Goals**

- Cobertura de los casos C-02 a C-19 (cada change agrega su `test/test_<change>.py`; `C-13` consolida la matriz).
- Los `.http` y `solo_agregado.sql` (evidencia de la consigna, `C-13`).
- Paralelismo de tests (`pytest-xdist`) o base efímera por contenedor: quedan fuera del stack y no aportan a la consigna.
- Cualquier cambio en `app/`, `main.py`, `seed.py`, `migrations/` o `alembic.ini`.

## Decisions

### D1 — El andén vive en `test/` y `pythonpath` apunta a la raíz (`..`)

Con `pytest.ini` dentro de `test/`, pytest toma **`test/` como rootdir** (es donde encontró la configuración). `pythonpath` y `testpaths` se resuelven **relativos al rootdir**, así que:

- `pythonpath = ..` → la raíz del repo, donde viven `app/`, `main.py` y `seed.py`.
- `testpaths = .` → `test/`.

Esto no es teórico, se verificó empíricamente:

```
$ pytest test/ -q -o pythonpath=.
ImportError while loading conftest '...\test\conftest.py'
E   ModuleNotFoundError: No module named 'seed'
```

`pythonpath = .` **rompe** los imports porque agrega `test/` al `sys.path`. Con `pythonpath = ..` funcionan tanto `import app` / `import main` como `import seed`, incluso con el script de consola `pytest` (que no agrega el cwd a `sys.path` como sí hace `python -m pytest`). Se eligió `..` justamente para **no depender** de que el usuario invoque `python -m`; la corrida documentada sigue siendo `python -m pytest test/ -v` desde la raíz, pero `pytest test/` también funciona.

Trade-off: si alguien agrega mañana un `pytest.ini`/`pyproject.toml` en la raíz, el rootdir pasa a ser la raíz y `pythonpath = ..` apuntaría al padre del repo. El fallo es ruidoso (`ModuleNotFoundError` en el primer import) y `test/test_entorno.py` lo detecta; se documenta acá para no perder el porqué. No se puso el ini en la raíz porque la estructura obligatoria de la consigna no lo admite.

### D2 — Un solo bucle de eventos para toda la corrida

`asyncio_mode = auto` + `asyncio_default_test_loop_scope = session` + `asyncio_default_fixture_loop_scope = session`.

Motivo concreto: `app/core/security.py` crea el semáforo de bcrypt **a nivel de módulo**, y `asyncio.Semaphore` se liga al bucle en el que se usa por primera vez. Con un bucle nuevo por test, el día que dos pruebas compitan por el semáforo (p. ej. los tests de login concurrente de `C-07`) la segunda revienta con «bound to a different event loop». Un único bucle elimina esa clase entera de error intermitente; el motor se sigue creando y destruyendo por test dentro del `lifespan`, así que no se comparte estado de conexión entre pruebas.

Alternativa descartada: `loop_scope` por test y re-crear el semáforo. Obligaría a tocar `app/` desde el andén (prohibido: los tests no adaptan la app) y sería frágil.

### D3 — Variables de test fijadas antes de importar la app

`conftest.py` se importa antes que cualquier test, así que ahí se escribe el entorno **antes** del `import main`:

| Variable | Valor en test | Por qué |
|---|---|---|
| `POSTGRES_DB` | `taller_mecanico_test` | el seed trunca: nunca debe poder tocar la base de desarrollo |
| `SECRET_KEY` | clave de prueba (≥ 32 bytes) | la app no arranca sin ella; no se usa ningún secreto real |
| `COOKIE_SECURE` | `false` | el cliente ASGI habla `http://test`, no TLS |
| `SQL_ECHO` | `false` | el ruido de las consultas taparía los fallos |
| `BCRYPT_ROUNDS` | `4` | el seed hashea en cada test; con 12 rondas cada test pagaría ~300 ms |

Como pydantic-settings da prioridad a las variables de entorno sobre `.env`, el override gana. `test/test_entorno.py` verifica que `settings.POSTGRES_DB == "taller_mecanico_test"`: es la guarda que impide que un cambio futuro vuelva a apuntar la suite a la base de desarrollo.

Trade-off de `BCRYPT_ROUNDS=4`: no se prueba el costo de producción. El costo no es lo que se valida (se valida comportamiento: 401/429/token), pero si algún día se mide la duración del hash, hay que subirlo.

### D4 — La base de test se crea y se migra una sola vez, con Alembic

Fixture `base_migrada`, **session-scoped y síncrona**:

1. `asyncpg.connect(database="postgres")` → `SELECT 1 FROM pg_database WHERE datname = $1` y, si falta, `CREATE DATABASE "taller_mecanico_test"`. Se usa asyncpg porque ya es dependencia del stack (cero agregados) y `CREATE DATABASE` no puede correr dentro de una transacción: asyncpg en autocommit lo permite.
2. `alembic.command.upgrade(Config(<raíz>/alembic.ini), "head")` con `script_location` absoluto a `migrations/`.

Es síncrona a propósito: `migrations/env.py` ya ejecuta Alembic con su propio `asyncio.run`, y llamarla desde una fixture async obligaría a mezclar bucles. Si la base ya está migrada, `upgrade head` es un no-op.

**Nunca** se usa `create_all` (regla dura): el esquema de test nace por la misma ruta que el de producción, así la suite también prueba las migraciones y los disparadores.

### D5 — El estado base se restaura re-corriendo `seed.py`, no con una transacción que se revierte

Fixture `base_limpia`, **function-scoped y autouse**: `await seed.main()` antes de cada test.

Por qué no el patrón «una transacción por test + rollback»:

- La app abre **sus propias** sesiones desde `app.state.session_maker`; cada petición HTTP vive en su propia conexión y confirma. Una transacción externa en otra conexión no puede envolverlas (no hay transacciones anidadas entre conexiones), así que habría que hackear el motor o compartir la conexión: exactamente el «truco» que el scope del change prohíbe.
- El seed usa `TRUNCATE ... RESTART IDENTITY CASCADE` justamente porque los disparadores de sólo agregado rechazan `DELETE`. Re-correrlo ejercita ese camino real.
- `RESTART IDENTITY` deja las secuencias reiniciadas: los ids del seed son estables dentro de cada test, lo que simplifica las aserciones de los changes siguientes.

Costo medido: 8 tests en ~2,2 s (con `BCRYPT_ROUNDS=4`). Se acepta: la corrección de que cada test vea el estado **confirmado** (triggers, índices parciales y commits reales incluidos) vale más que unos segundos.

Trade-off: la suite **no es segura** para dos procesos en simultáneo sobre la misma base de test (sin `pytest-xdist`, un proceso trunca lo que el otro está leyendo). Con dos agentes en paralelo hay que correr la suite de a uno, o usar una base de test por agente.

### D6 — Cliente ASGI con el lifespan real, sin dependencias extra

```python
transport = ASGITransport(app=app)
async with AsyncClient(transport=transport, base_url="http://test") as client: ...
```

La fixture `app_viva` abre `app.router.lifespan_context(app)`: Starlette expone ahí el lifespan ya envuelto, así que el motor, la fábrica de sesiones y (cuando exista) el hash ficticio de `C-07` quedan en `app.state` durante el test y se liberan (`engine.dispose()`) al terminar.

Descartados: `TestClient` (síncrono, corre el lifespan en un hilo con otro bucle: no ejercita los handlers `async` como se ejecutan en producción) y `asgi-lifespan` (dependencia extra fuera del stack permitido).

### D7 — `login()` y fixtures por rol quedan listas para `C-07`

`login(email, password="secreto123")` hace `POST /auth/login` con `{"email", "password"}`, exige 200 y devuelve la cookie `access_token` (que además queda en el tarro del cliente, así las peticiones siguientes ya van autenticadas). Las fixtures `token_admin`, `token_recepcion`, `token_mecanico` y `token_cliente` usan los usuarios del seed.

Hoy el endpoint **no existe** (llega en `C-07`), por eso ningún test de `C-05` las ejercita: se resuelven recién cuando `C-07` las pida. Es código sin cobertura hasta entonces, deliberado: el contrato (ruta, cuerpo, nombre de la cookie) está fijado en la KB (`02_descripcion_general.md`, Flujo 2) y `C-07` lo implementa. Si `C-07` cambia ese contrato, el ajuste es de una línea en el andén.

### D8 — Un solo doble, y sólo para simular una caída de infraestructura

El escenario 503 de `/health/ready` necesita una base que no contesta. Se reemplaza la dependencia `get_session` por una que levanta al ejecutar, con `app.dependency_overrides`, y se limpia en `finally`. No se reemplaza la persistencia: es el único punto del andén donde no corre PostgreSQL real, y está aislado en un test.

Excluidos por diseño (y por el scope del change): `factory-boy` (los objetos se construyen con el seed o con SQL explícito), `respx`/mocks de red (no hay APIs externas), sqlite y repositorios falsos (no reproducen CHECK, índices parciales ni triggers), `testcontainers`/Docker (fuera del stack y de la consigna).

## Risks / Trade-offs

- **Rootdir frágil ante un ini en la raíz** (D1): se documenta y `test_entorno.py` lo detecta con `import main`.
- **Suite más lenta por seed en cada test** (D5): ~0,2 s por test hoy; si la suite crece, se puede agrupar por módulo con una fixture de alcance módulo sin cambiar el contrato (cada test sigue viendo el estado base).
- **`BCRYPT_ROUNDS=4` no representa producción** (D3): es una decisión de velocidad; el costo real se configura sólo en `.env`.
- **Dos procesos sobre la misma base de test se pisan** (D5): correr una suite por vez o una base por agente.
- **Fixtures de rol sin cobertura hasta `C-07`** (D7): el contrato está en la KB; el riesgo es un cambio de ruta/cuerpo y se resuelve en una línea.
- **Un módulo de test a medio escribir rompe la recolección de todo `test/`**: con dos agentes en paralelo, un archivo que todavía no importa (p. ej. porque su módulo de la app aún no existe) tumba la corrida completa con un `ImportError`. Es transitorio; mientras dure, se verifica con los archivos propios (`python -m pytest test/test_health.py test/test_entorno.py test/test_aislamiento.py`).
- **La base de test sobrevive entre corridas**: no se borra al final. Es intencional (arrancar es más barato y el estado se re-siembra por test); si el esquema cambia, `alembic upgrade head` la pone al día.

## Migration Plan

1. `pip install -r requirements.txt` (agrega el bloque de testing).
2. `python -m pytest test/ -v` desde la raíz: crea `taller_mecanico_test` si falta, migra y corre los smoke tests.
3. Revertir: borrar `test/pytest.ini`, `test/conftest.py` y `test/test_*.py` y quitar el bloque de testing de `requirements.txt`. La base `taller_mecanico_test` se puede dropear; `taller_mecanico` nunca fue tocada.
