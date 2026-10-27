# Proposal

## Why

`C-03` dejó el metadata de las trece tablas, pero **nada crea el esquema**: hoy una base vacía no se puede levantar y la aplicación no tiene datos con los que funcionar. La consigna exige que el esquema nazca **sólo** de `alembic upgrade head` (nunca de `create_all`), que haya dos migraciones —una generada y una escrita a mano para el sólo agregado— y que `seed.py` deje la base en un estado inicial conocido que los casos de prueba usan.

Sin este change no se puede arrancar la app contra una base real ni empezar la suite (`C-05`).

## What Changes

- **`alembic.ini`**: configuración sin credenciales; la URL sale de `Settings` en `migrations/env.py`.
- **`migrations/env.py`**: plantilla **asincrónica** (`async_engine_from_config` + `connection.run_sync`), importa `app/models.py` para que el metadata conozca las trece tablas y activa `compare_type`/`compare_server_default`.
- **Migración 1** (`--autogenerate`, revisada): las trece tablas con índices, UNIQUE, CHECK e índices únicos parciales (`postgresql_where`); `estado_orden` queda **vacío**.
- **Migración 2** (escrita a mano): función y disparadores que rechazan `UPDATE` y `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` (RN-15), con el comentario de que debe leerse antes de aplicarse (DD-14).
- **`seed.py`**: vacía las tablas y carga catálogo de estados, 7 usuarios con sus roles, 2 clientes y 3 vehículos, 4 repuestos con su movimiento de «Stock inicial», 2 órdenes (la segunda con 4 bujías sobre un stock de 2), el historial de precio del filtro y el evento de seguridad de `SISTEMA`.
- **`migrations/README`**: explica el ciclo `upgrade head → downgrade base → upgrade head` y por qué el seed usa `TRUNCATE` y no `DELETE`.

## Capabilities

### New Capabilities
- `schema-migrations`: el esquema versionado con Alembic (plantilla asincrónica, migración generada + migración manual) y el contrato de que la base se crea y se revierte sólo con `alembic upgrade`/`downgrade`.
- `append-only-enforcement`: la garantía de que las tres tablas de auditoría no admiten `UPDATE` ni `DELETE`, impuesta por disparadores instalados por la migración manual.
- `initial-seed`: el estado inicial determinista de la base: catálogo primero, usuarios y roles, clientes y vehículos, repuestos con su stock, órdenes de prueba, historial de precio y evento de seguridad, cargable las veces que haga falta.

### Modified Capabilities
- Ninguna. Los modelos de `C-03` no cambian; las migraciones materializan ese contrato.

## Impact

- **Código**: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_*.py`, `migrations/versions/0002_*.py`, `migrations/README`, `seed.py`.
- **Base de datos**: crea las trece tablas, sus índices y restricciones, y los disparadores de sólo agregado. `down` deja el esquema vacío.
- **Dependencias**: ninguna nueva (`alembic` y `asyncpg` ya están en `requirements.txt`).
- **Habilitado**: `C-05 test-infrastructure` (la suite necesita el esquema y los datos) y `C-06` en adelante.
- **Orden de operación**: `alembic upgrade head` y después `python seed.py`; el seed no crea tablas.
