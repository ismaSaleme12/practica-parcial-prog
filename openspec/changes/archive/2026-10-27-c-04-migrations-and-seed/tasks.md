# Tasks

## 1. Configuración de Alembic

- [x] 1.1 Crear `alembic.ini` en la raíz con `script_location = migrations`, `prepend_sys_path = .` y `path_separator = os`; **sin** `sqlalchemy.url` ni credenciales. Verificación: `grep -i "password\|postgres" alembic.ini` no devuelve nada.
- [x] 1.2 Escribir `migrations/env.py` con la plantilla asincrónica (`async_engine_from_config`, `poolclass=NullPool`, `connection.run_sync`), URL desde `settings.ASYNC_DATABASE_URL` (escapando `%`), `target_metadata = SQLModel.metadata`, `compare_type` y `compare_server_default`; importar `app/models.py`. Verificación: `alembic current` conecta contra la base de `.env` sin error y `alembic check` no reporta diferencias después de migrar.
- [x] 1.3 Dejar `migrations/script.py.mako` y `migrations/README` con el ciclo de trabajo (`upgrade head → downgrade base → upgrade head`) y la advertencia de que el seed usa `TRUNCATE`. Verificación: ambos archivos existen y el README menciona el ciclo.

## 2. Migración 1 — esquema generado

- [x] 2.1 Generar la revisión con `alembic revision --autogenerate -m "crea las tablas del dominio"` y revisar el archivo: trece `op.create_table`, CHECK y FK nombradas, UNIQUE e índices únicos parciales con `postgresql_where`; `estado_orden` sin filas. Verificación: el archivo contiene los 13 `create_table`, los 3 `postgresql_where` y ningún `INSERT`.
- [x] 2.2 Aplicar sobre una base vacía (`POSTGRES_DB=taller_mecanico_test`) y comprobar el esquema resultante. Verificación: `alembic upgrade head` termina OK; `information_schema` reporta 13 tablas de dominio; `pg_indexes` reporta los 3 índices parciales con su `WHERE`; `pg_constraint` reporta los 7 CHECK y las 17 FK.

## 3. Migración 2 — sólo agregado escrito a mano

- [x] 3.1 Crear la revisión manual con la función `solo_agregado_rechazar_modificacion()` y un `BEFORE UPDATE OR DELETE ... FOR EACH ROW` por tabla, con el comentario **LEER ANTES DE APLICAR** (DD-14) y `ERRCODE` de integridad. Verificación: el archivo se lee completo y no usa `--autogenerate`.
- [x] 3.2 Verificar el rechazo. Verificación: tras aplicar, un `UPDATE` y un `DELETE` sobre cada una de las tres tablas fallan con SQLSTATE `23000` y las filas quedan intactas; un `INSERT` nuevo en cada tabla se acepta.
- [x] 3.3 Verificar el `downgrade` de la revisión manual. Verificación: `alembic downgrade -1` elimina los tres disparadores y la función, y un `UPDATE` sobre `movimiento_stock` vuelve a aceptarse; `alembic upgrade head` los reinstala.

## 4. Seed

- [x] 4.1 Estructura de `seed.py`: motor y sesión desde `settings`, un solo `UnitOfWork`, `TRUNCATE` de las trece tablas con `RESTART IDENTITY CASCADE` y contraseñas con `hash_password`. Verificación: el script corre de punta a punta y el encabezado explica la contraseña de prueba y por qué no usa `DELETE`.
- [x] 4.2 Catálogo de estados primero, y después los 7 usuarios con sus asignaciones abiertas (`otorgada_por = 'SISTEMA'`) y `nuevo@example.com` con `debe_cambiar_password`. Verificación: 4 estados con posiciones 1–4 y `es_final` correcto; 7 usuarios y 7 asignaciones vigentes; sólo `nuevo@` tiene el flag.
- [x] 4.3 Clientes y vehículos: Laura con usuario y dos vehículos, Jorge sin usuario y uno. Verificación: 2 clientes, 3 vehículos, uno de ellos con `usuario_id` nulo.
- [x] 4.4 Repuestos con «Stock inicial»: 4 repuestos (stock 10, 4, 2 y 20) y un movimiento por cada uno con la misma cantidad. Verificación: 4 repuestos, 4 movimientos con motivo `Stock inicial` y cantidad igual al stock.
- [x] 4.5 Órdenes: la 1 `PENDIENTE` sobre el primer vehículo de Laura; la 2 `EN_REPARACION` sobre el de Jorge, asignada a `mecanico@example.com`, con 4 bujías a `1500.00` y total `6000.00`; historial de transiciones de ambas. Verificación: 2 órdenes, el ítem de la 2 con cantidad 4 sobre stock 2, y el historial de la 2 con ∅→`PENDIENTE` y `PENDIENTE`→`EN_REPARACION`.
- [x] 4.6 Historial de precio del filtro (`8000.00`→`8500.00`) y evento de seguridad `SISTEMA`. Verificación: una línea de historial por repuesto y una línea de evento con la acción esperada.

## 5. Verificación integral

- [x] 5.1 Ciclo completo en base de test: `upgrade head` → `downgrade base` → `upgrade head`. Verificación: después del `downgrade base` no quedan tablas de dominio; el segundo `upgrade` recrea las 13 y los disparadores.
- [x] 5.2 Seed idempotente. Verificación: dos ejecuciones seguidas dejan los mismos conteos en las 13 tablas y ningún error de unicidad.
- [x] 5.3 Seed sin esquema. Verificación: con las tablas borradas, `python seed.py` termina con código ≠ 0 y un mensaje que indica `alembic upgrade head` (no crea tablas).

## 6. Documentación y cierre

- [x] 6.1 Actualizar `CHANGES.md` con `C-04` completado y anotar en `knowledge-base/04_modelo_de_datos.md` (si hace falta) que el catálogo lo carga el seed. Verificación: la línea dice `[x] completado`.
- [x] 6.2 Confirmar que la app sigue levantando contra la base migrada. Verificación: `GET /health/ready` → 200 con la base migrada y sembrada.

## Workflow follow-up

- Revisar los artefactos y archivar con `/opsx:archive c-04-migrations-and-seed` cuando el usuario lo pida.
- Después del archivo, `C-05 test-infrastructure` queda habilitado (necesita el esquema y el seed para la suite).
