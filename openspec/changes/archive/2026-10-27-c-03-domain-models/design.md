# Design

## Context

`C-03` define las trece tablas del dominio como modelos SQLModel. Todavía no hay migraciones (`C-04`), ni seed, ni suite de tests (`C-05`): este change entrega el **metadata** y lo verifica por introspección y por DDL ejecutado contra PostgreSQL real dentro de una transacción que se revierte.

La consigna fija los nombres de tablas y columnas y las restricciones; el diseño elige cómo representarlos de forma que la base —y no el código— haga cumplir las reglas.

## Goals / Non-Goals

**Goals**

- Las 13 tablas con los nombres y columnas obligatorios.
- Restricciones ejecutadas por PostgreSQL: CHECK, UNIQUE, tres índices únicos parciales y FK al catálogo de estados.
- Dinero `Decimal` + `NUMERIC(p,2)`; todas las fechas `timestamptz`.
- Un índice por cada FK.
- Navegación declarada en los dos extremos, con `Usuario.cliente` como objeto único.

**Non-Goals**

- Migraciones Alembic, disparadores de sólo agregado y seed → `C-04`.
- Repositorios por módulo, servicios, DTOs y endpoints → `C-06` a `C-12`.
- Suite pytest formal → `C-05`/`C-13`. La verificación de este change es un script de humo ejecutable (119 comprobaciones, incluida la creación real del esquema y su rollback).

## Decisions

### D1 — Un módulo de modelos por dominio y un registro central

`app/modules/<dominio>/models.py` es dueño de sus tablas; `app/models.py` importa los trece modelos en un único punto. Las relaciones cruzan módulos (`Usuario.cliente`, `Repuesto.items_orden`, `OrdenTrabajo.estado_actual`), y SQLAlchemy resuelve los nombres de clase contra su registro **en el momento de configurar los mappers**. Si se importa un solo módulo, las relaciones cuyo destino no fue importado fallan con `expression 'Cliente' failed to locate a name`. Por eso:

- las anotaciones de relación son cadenas (`Optional["Cliente"]`, `list["Vehiculo"]`) y el destino sólo se importa bajo `TYPE_CHECKING`, evitando ciclos;
- `app/models.py` es el punto de entrada obligatorio para cualquier consumidor del metadata (Alembic en `C-04`, scripts, tests).

No se usa `from __future__ import annotations`: en SQLModel convierte **todas** las anotaciones en cadenas y rompe la detección de tipos de las columnas.

### D2 — `sa_column` explícito para los tipos que importan

`NUMERIC(10,2)`, `NUMERIC(12,2)`, `TIMESTAMP WITH TIME ZONE` y la PK textual del catálogo se declaran con `sa_column=Column(...)`. La anotación de Python sola no alcanza: `Decimal` no fija precisión y `datetime` no fija zona horaria. Para las columnas con valor por defecto se combinan:

- `Field(default_factory=...)` (valor disponible en el objeto antes del `flush`), y
- `server_default=func.now()` / `text("0")` / `text("true")` (valor correcto también para `INSERT` en SQL crudo, como hará el seed).

`activo` y `debe_cambiar_password` llevan `server_default` además del default de Python, para que una fila insertada desde psql quede en el estado que el dominio espera.

### D3 — Índices únicos parciales con `postgresql_where`

Los tres índices de DD-03 se declaran en `__table_args__`:

```python
Index("uq_vehiculo_patente_vigente", "patente", unique=True,
      postgresql_where=text("borrado_en IS NULL"))
```

La condición es SQL de PostgreSQL, no un filtro de aplicación: la unicidad la garantiza la base (RN-01). Lo mismo para `repuesto.codigo` y para `(usuario_id, rol) WHERE revocada_en IS NULL`.

**Sin índices duplicados**: cuando un UNIQUE ya indexa una FK como primera columna se reutiliza ese índice. `item_orden` no lleva índice propio de `orden_id` (lo cubre `uq_item_orden_orden_repuesto`) y `cliente` no lleva índice de `usuario_id` (lo cubre su UNIQUE). Sí se agrega `ix_asignacion_rol_usuario_id` porque el índice parcial no sirve para consultar todas las asignaciones.

### D4 — CHECK con nombres explícitos

Cada CHECK lleva nombre (`ck_<tabla>_<regla>`) porque la migración de `C-04` los necesita para crear y revertir, y porque los tests pueden buscarlos por nombre. Las dos reglas ambiguas de la consigna quedan como se resolvió en IN-01/IN-02:

- `movimiento_stock.cantidad <> 0` (la reposición entra positiva; la salida, negativa),
- `historial_precio_repuesto.precio_nuevo <> precio_anterior` (el precio puede subir o bajar).

### D5 — `estado` es columna y la relación tiene otro nombre

`orden_trabajo.estado` es el nombre obligatorio de la columna; un atributo de Python no puede llamarse igual que la relación. Se declara:

- `estado: str` → columna con FK a `estado_orden.codigo` (lo que se lee en psql y lo que usan los filtros de los servicios),
- `estado_actual: "EstadoOrden"` → relación navegable, con `foreign_keys="OrdenTrabajo.estado"`.

En `historial_estado_orden` pasa lo mismo con dos FKs al mismo catálogo: columnas `desde_estado`/`hasta_estado` y relaciones `estado_desde`/`estado_hasta`. Las **dos** relaciones llevan `foreign_keys` explícito; sin eso SQLAlchemy no puede desambiguar el join.

### D6 — `lazy="raise_on_sql"` en todas las relaciones

La regla dura del proyecto prohíbe el lazy loading en lecturas: cada endpoint debe traer lo que usa con carga anticipada y un número fijo de consultas (caso C-15). En vez de confiar en la revisión, el modelo hace **fallar** cualquier acceso que necesite emitir SQL:

```python
sa_relationship_kwargs={"lazy": "raise_on_sql"}
```

Así un servicio que olvide `selectinload`/`joinedload` recibe un error explícito en vez de un N+1 silencioso. Costo aceptado: los consumidores deben pedir lo que van a usar; el seed y los repositorios de `C-04` en adelante lo hacen explícito.

### D7 — Composición en el ORM, sin cascada en la base

`OrdenTrabajo.items` declara `cascade="all, delete-orphan"`: un `item_orden` no existe sin su orden (rombo lleno de la Figura 1). **No** se pone `ON DELETE CASCADE` en la FK: las órdenes no se borran (se cancelan), y las tablas de sólo agregado no deben perder historia por una cascada. Si alguna vez se borra una orden por ORM, los ítems se borran primero y la FK `RESTRICT` no estorba.

### D8 — `asignacion_rol.otorgada_por` es texto, no FK

La carga inicial otorga roles como `SISTEMA`, que no es un usuario. Una FK obligaría a inventar una cuenta de sistema. Se guarda como texto (`String(120)`, nulo permitido), con el mismo criterio que `evento_seguridad.actor`.

### D9 — `intento_acceso.ip` es `VARCHAR(45)`, no `INET`

`INET` exigiría un tipo propio de PostgreSQL y un conversor en SQLModel. `VARCHAR(45)` cubre IPv4 e IPv6 con formato completo y no agrega dependencias ni tipos fuera del stack.

## Risks / Trade-offs

- **Importar un módulo suelto no alcanza**: `from app.modules.usuarios.models import Usuario` seguido de una consulta falla si no se importó `app.models` (D1). Queda documentado en el docstring del registro y es el primer punto que debe respetar `C-04`.
- **`raise_on_sql` es ruidoso**: un acceso perezoso que antes devolvía datos ahora lanza `InvalidRequestError`. Es intencional; los services de `C-07` en adelante deben usar carga anticipada desde el primer día.
- **Divergencia columna/relación** (`estado` vs `estado_actual`): un agente que asuma `orden.estado` como objeto recibirá un `str`. Está documentado en el modelo y en este design.
- **Sin suite formal todavía**: la verificación es un script de humo. La red definitiva es `C-05`/`C-13`, que repetirán estas reglas como tests.
- **`NUMERIC(12,2)` en `total`** admite hasta diez dígitos enteros; el catálogo de repuestos usa `NUMERIC(10,2)`. Son los tamaños de la consigna.

## Migration Plan

Este change no crea ni modifica el esquema de ninguna base: el metadata se verifica creando las tablas dentro de una transacción que se revierte (0 tablas al terminar). `C-04 migrations-and-seed` genera la primera migración desde `app/models.py`, crea los disparadores de sólo agregado y carga el catálogo antes que cualquier orden.
