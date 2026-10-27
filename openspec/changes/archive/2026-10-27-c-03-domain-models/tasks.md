# Tasks

## 1. Estructura y registro

- [x] 1.1 Crear `app/modules/{usuarios,clientes,repuestos,ordenes}/models.py` y el registro central `app/models.py` que importa los trece modelos. Verificación: `python -c "import app.models; from sqlalchemy.orm import configure_mappers; configure_mappers()"` configura los mappers sin error y el metadata reporta **13** tablas.
- [x] 1.2 Dejar documentado en `app/models.py` que es el punto de entrada obligatorio del metadata (Alembic lo importará en `C-04`) y por qué las relaciones se anotan como cadenas. Verificación: el docstring lo explica y las anotaciones usan `Optional["..."]` / `list["..."]` con imports bajo `TYPE_CHECKING`.

## 2. Identidad y accesos (`usuarios`)

- [x] 2.1 `Usuario`: `id`, `email` (UNIQUE `uq_usuario_email`), `nombre`, `password_hash`, `activo`, `debe_cambiar_password`, `password_cambiada_en` (timestamptz nulo). Verificación: el DDL creado en PostgreSQL acepta el alta y rechaza un email duplicado; `password_cambiada_en` queda `NULL` cuando no se informa.
- [x] 2.2 `AsignacionRol`: FK a `usuario`, CHECK `rol IN ('ADMIN','RECEPCION','MECANICO','CLIENTE')`, índice único parcial `(usuario_id, rol) WHERE revocada_en IS NULL`, `otorgada_por` como texto. Verificación: PostgreSQL rechaza la segunda asignación abierta del mismo rol y un rol fuera del catálogo, y acepta una nueva asignación después de revocar la anterior; `otorgada_por = 'SISTEMA'` se guarda sin usuario.
- [x] 2.3 `IntentoAcceso` con índice `(email, ip, cuando)` y `EventoSeguridad` con `actor` texto. Verificación: el índice existe en `pg_indexes`; se guardan un intento fallido y uno exitoso (`exito` distinto) y un evento con `actor = 'SISTEMA'`.

## 3. Cartera de clientes (`clientes`)

- [x] 3.1 `Cliente`: `usuario_id` nulo con UNIQUE (1:1), `documento` UNIQUE, `nombre` y `telefono`. Verificación: PostgreSQL acepta un cliente con usuario y otro sin usuario, y rechaza el segundo cliente para el mismo usuario y el documento duplicado; el UNIQUE de `usuario_id` cubre el índice de la FK.
- [x] 3.2 `Vehiculo`: FK a `cliente` con índice, CHECK `anio BETWEEN 1950 AND 2100`, índice único parcial `(patente) WHERE borrado_en IS NULL`. Verificación: rechaza patente duplicada entre vigentes, año 1949 y cliente inexistente; después de escribir `borrado_en` acepta registrar la misma patente.

## 4. Repuestos y stock (`repuestos`)

- [x] 4.1 `Repuesto`: `precio NUMERIC(10,2)` con CHECK `> 0`, `stock` con CHECK `>= 0`, índice único parcial `(codigo) WHERE borrado_en IS NULL`. Verificación: `8000.10` vuelve como `Decimal('8000.10')`; rechaza precio 0, stock -1 y código duplicado entre vigentes; acepta reutilizar el código de un repuesto dado de baja.
- [x] 4.2 `MovimientoStock`: FKs a repuesto/orden/usuario con sus índices, CHECK `cantidad <> 0` (IN-01). Verificación: acepta una entrada positiva sin orden y una salida negativa con orden; rechaza `cantidad = 0`.
- [x] 4.3 `HistorialPrecioRepuesto`: precios `NUMERIC(10,2)`, CHECK `precio_nuevo > 0` y `precio_nuevo <> precio_anterior` (IN-02). Verificación: acepta suba y baja; rechaza precio nuevo 0 y precio sin cambio.

## 5. Órdenes de trabajo (`ordenes`)

- [x] 5.1 `EstadoOrden`: PK `codigo` textual, `posicion` UNIQUE, `es_final`. Verificación: el DDL acepta el catálogo y rechaza una posición repetida; la PK es `codigo` (no hay columna `id`).
- [x] 5.2 `OrdenTrabajo`: FK `estado` → `estado_orden.codigo`, `mecanico_id` nulo, `creada_en` timestamptz, `total NUMERIC(12,2)` con CHECK `>= 0`, índices de las tres FKs. Verificación: rechaza un estado inexistente (RN-19) y un total negativo; acepta una orden sin mecánico.
- [x] 5.3 `ItemOrden`: UNIQUE `(orden_id, repuesto_id)`, CHECK de `cantidad > 0` y `precio_unitario > 0`, índice de `repuesto_id`. Verificación: rechaza el repuesto repetido, cantidad 0 y orden inexistente.
- [x] 5.4 `HistorialEstadoOrden`: FKs a orden, catálogo por ambos extremos y usuario, con sus cuatro índices. Verificación: la primera transición guarda `desde_estado` nulo y rechaza un `hasta_estado` inexistente.

## 6. Navegación

- [x] 6.1 Declarar las relaciones en ambos extremos y `lazy="raise_on_sql"` en todas. Verificación: `configure_mappers()` resuelve 34 relaciones (17 pares) sin error; `Usuario.cliente` tiene `uselist = False`; las seis relaciones de `Usuario` y las seis de `OrdenTrabajo` existen; ninguna relación conserva `lazy="select"`.
- [x] 6.2 Declarar `OrdenTrabajo.items` como composición (`cascade="all, delete-orphan"`) y desambiguar las dos FKs de `HistorialEstadoOrden` con `foreign_keys`. Verificación: el mapper reporta la cascada y `EstadoOrden` navega `historiales_desde` e `historiales_hasta`.

## 7. Verificación integral

- [x] 7.1 Introspección del metadata: nombres de tabla exactos, columnas obligatorias, `NUMERIC(p,s)`, `timestamptz`, CHECK/UNIQUE/índices parciales y cobertura de índices de FK. Verificación: script `verify_c03_models.py`, sección de metadata → 0 fallas.
- [x] 7.2 PostgreSQL real: crear las 13 tablas y sus índices dentro de una transacción, ejecutar las reglas (altas válidas, violaciones esperadas y borrado lógico) y revertir. Verificación: 119 comprobaciones OK, `rollback` deja **0** tablas creadas (`POSTGRES_DB=taller_mecanico_test` desde `.env`).
- [x] 7.3 Actualizar `CHANGES.md` con el estado de `C-03`. Verificación: la línea dice `[x] completado`.

## Workflow follow-up

- Revisar los artefactos y archivar con `/opsx:archive c-03-domain-models` cuando el usuario lo pida.
- Después del archivo, `C-04 migrations-and-seed` queda habilitado: debe importar `app/models.py` en `env.py`, crear los disparadores de sólo agregado y cargar primero el catálogo de estados.
