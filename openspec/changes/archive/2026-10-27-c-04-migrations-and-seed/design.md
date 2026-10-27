# Design

## Context

`C-03` entrega el metadata; este change lo convierte en esquema real y en datos iniciales. La consigna pide **dos** migraciones (una generada, una escrita a mano), plantilla **asincrónica** y un `seed.py` que deje la base en un estado conocido. El ciclo `upgrade head → downgrade base → upgrade head` es requisito de corrección.

## Goals / Non-Goals

**Goals**

- `alembic upgrade head` sobre base vacía crea las trece tablas con todos sus índices y restricciones.
- `downgrade base` no deja tablas de dominio; volver a subir recrea lo mismo.
- Disparadores que rechazan `UPDATE`/`DELETE` en las tres tablas de auditoría, creados por la migración manual.
- `seed.py` idempotente, con el catálogo primero y el caso de stock insuficiente de la orden 2.

**Non-Goals**

- Suite pytest (`C-05`) y evidencia `.http`/`solo_agregado.sql` (`C-14`).
- Endpoints, servicios y repositorios por módulo (`C-06` en adelante).
- Datos de prueba adicionales a los que fija la KB.

## Decisions

### D1 — `alembic.ini` sin credenciales y `env.py` que lee `Settings`

`alembic.ini` sólo declara `script_location = migrations`, `prepend_sys_path = .` y `path_separator = os`. No tiene `sqlalchemy.url`: `migrations/env.py` la setea desde `settings.ASYNC_DATABASE_URL` (el mismo `.env` que usa la app) y escapa `%` antes de pasarla a la config, porque `configparser` lo interpreta como interpolación.

La plantilla es la **asincrónica**: `async_engine_from_config` con `poolclass=NullPool` y `connection.run_sync(do_run_migrations)`. Se soporta también el modo offline (`--sql`) para revisar el SQL sin conectarse.

### D2 — `env.py` importa `app/models.py`, no los módulos sueltos

Es la razón por la que existe el registro central (D1 de `C-03`): sin él, el metadata no conoce las relaciones entre módulos y la configuración de mappers falla. `target_metadata = SQLModel.metadata` con `compare_type=True` y `compare_server_default=True` para que futuras migraciones detecten cambios de tipo y de default.

### D3 — Migración 1 generada y revisada, no copiada a mano

Se genera con `alembic revision --autogenerate -m "crea las tablas del dominio"` contra una base vacía y se **revisa** antes de commitear. Puntos que se verifican en el archivo:

- las trece `op.create_table(...)` con CHECK y FK nombradas;
- los tres `op.create_index(..., unique=True, postgresql_where=sa.text(...))`;
- los UNIQUE de `usuario.email`, `cliente.usuario_id`, `cliente.documento`, `estado_orden.posicion` e `item_orden(orden_id, repuesto_id)`;
- que `estado_orden` se cree **vacía** (el catálogo es dato, no esquema).

Si autogenerate omite un CHECK o un índice parcial (limitación conocida de la herramienta), se corrige el archivo generado y se deja anotado; el resultado es lo que se versiona.

### D4 — Migración 2 escrita a mano con una sola función y tres disparadores

```sql
CREATE OR REPLACE FUNCTION solo_agregado_rechazar_modificacion()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'La tabla % es de sólo agregado: % no está permitido',
                  TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$;
```

Un `BEFORE UPDATE OR DELETE ... FOR EACH ROW` por tabla (`historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto`). El `ERRCODE` 23000 hace que el error se comporte como una violación de integridad, no como un fallo inesperado. El archivo arranca con el comentario **«LEER ANTES DE APLICAR»** que exige DD-14 y su `downgrade` hace `DROP TRIGGER` y `DROP FUNCTION`, de modo que bajar sólo esta revisión deja las tablas usables.

Se usa **una** función para las tres tablas: el mensaje incluye `TG_TABLE_NAME`, así que no se pierde información y no hay tres copias del mismo cuerpo.

### D5 — El seed vacía con `TRUNCATE`, no con `DELETE`

Los disparadores de D4 rechazan el borrado fila por fila, y el seed tiene que poder reiniciarse. `TRUNCATE historial_estado_orden, movimiento_stock, ... RESTART IDENTITY CASCADE` es la operación de reset: no dispara los `BEFORE UPDATE OR DELETE`, reinicia las secuencias y deja las trece tablas vacías en una sola sentencia. **La API nunca trunca**; el permiso vive en el script de puesta en marcha.

`CASCADE` es necesario porque el truncado incluye tablas referenciadas por FK; se listan las trece explícitamente para que el orden no dependa de la cascada.

### D6 — El seed usa el UoW y las primitivas de seguridad del proyecto

Un solo `async with UnitOfWork(sesion)` alrededor de todo el seed: el truncado y las altas se confirman juntos o no se confirman. Las contraseñas se hashean con `hash_password` (bcrypt fuera del bucle, mismo costo que la app) y son **de mentira**, definidas en una constante del propio archivo: `secreto123`. No se agrega un endpoint ni un flag de «modo seed»: es un script de puesta en marcha.

Las órdenes, ítems e historiales se insertan con `session.add_all` y un `flush` para obtener los ids; no se usan repositorios porque el seed no es una operación de negocio.

### D7 — Datos iniciales concretos

| Tabla | Filas |
|---|---|
| `estado_orden` | `PENDIENTE` (1), `EN_REPARACION` (2), `TERMINADA` (3, final), `CANCELADA` (4, final) |
| `usuario` | 7: `admin@`, `admin2@` (ADMIN), `recepcion@` (RECEPCION), `mecanico@`, `mecanico2@` (MECANICO), `cliente@` (CLIENTE), `nuevo@` (MECANICO, `debe_cambiar_password=true`) — todos con contraseña `secreto123` |
| `asignacion_rol` | una abierta por usuario, `otorgada_por = 'SISTEMA'` |
| `cliente` | Laura (`cliente@example.com`, documento `30111222`), Jorge (sin usuario, documento `27888999`) |
| `vehiculo` | Laura: `AAA111` Fiat Uno 2015 y `AAB222` Renault Clio 2018; Jorge: `BBB333` Ford Fiesta 2020 |
| `repuesto` | `FA-001` Filtro de aceite `8500.00` stock 10; `PF-002` Pastillas de freno `12000.00` stock 4; `BU-003` Bujía `1500.00` stock 2; `AC-004` Aceite por litro `2500.00` stock 20 |
| `movimiento_stock` | uno por repuesto, motivo `Stock inicial`, cantidad = stock, usuario `admin@` |
| `orden_trabajo` | 1: `PENDIENTE`, `AAA111`, total `0.00`; 2: `EN_REPARACION`, `BBB333`, mecánico `mecanico@`, total `6000.00` |
| `item_orden` | orden 2: `BU-003` × 4 a `1500.00` (stock 2: insumo del caso C-11) |
| `historial_estado_orden` | orden 1: ∅→`PENDIENTE`; orden 2: ∅→`PENDIENTE` y `PENDIENTE`→`EN_REPARACION` (por `mecanico@`) |
| `historial_precio_repuesto` | `FA-001`: `8000.00` → `8500.00`, usuario `admin@` |
| `evento_seguridad` | actor `SISTEMA`, acción «Carga de los datos iniciales» |

Los totales se calculan en el seed a partir de los ítems (`cantidad × precio_unitario`), igual que lo hará el servicio de órdenes (RN-10).

### D8 — `seed.py` es ejecutable de punta a punta y falla fuerte

`python seed.py` arma el motor desde `settings`, abre una sesión, ejecuta el seed y **no** crea el esquema. Si la base no está migrada, PostgreSQL responde «relation does not exist» y el script termina con código distinto de cero y un mensaje que dice que hay que correr `alembic upgrade head` primero. Al final imprime un resumen de filas por tabla.

## Risks / Trade-offs

- **Autogenerate no ve todo**: CHECK e índices parciales pueden requerir ajuste manual del archivo generado (D3). Se verifica con el ciclo real y con introspección de `pg_constraint`/`pg_indexes`.
- **El disparador también frena al seed si se usa `DELETE`**: por eso D5. Queda documentado en `migrations/README` y en el encabezado de `seed.py`; un agente que escriba un reset con `DELETE` va a chocar con el trigger (es lo buscado).
- **`TRUNCATE` esquiva el sólo agregado**: es el precio de poder reiniciar los datos. Sólo lo usa el seed, que no corre en producción.
- **`TRUNCATE ... CASCADE` con las trece tablas**: si mañana se agrega una tabla y no se lista, el reset la deja con filas viejas. El script lista las trece explícitamente y el resumen final permite detectarlo.
- **Contraseña de seed conocida**: es intencional (los casos de prueba tienen que poder loguearse) y el encabezado del archivo lo dice.

## Migration Plan

1. `alembic upgrade head` sobre base vacía.
2. `python seed.py`.
3. `alembic downgrade base` y `alembic upgrade head` para verificar reversibilidad (en la base de test, no en la de desarrollo).
4. Revertir: `downgrade base` deja la base sin tablas de dominio; los datos del seed se pierden con el esquema, que es el comportamiento esperado.
