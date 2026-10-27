# Proposal

## Why

`C-01` y `C-02` dejaron la aplicación en pie (configuración, sesión, repositorios, UoW y primitivas de seguridad) pero **no existe ninguna tabla de dominio**: los 13 modelos del Ejercicio 2 (US-005) son el contrato que consumen todos los changes siguientes. Sin ellos no hay migraciones (`C-04`), ni autenticación (`C-07`), ni órdenes (`C-11`).

Los nombres de tablas y columnas están **impuestos por la consigna** y los usan los casos de prueba, así que un modelo mal nombrado se propaga a migraciones, contratos, servicios y suite. Este change fija ese contrato de una vez, con las restricciones que la base debe hacer cumplir (no la aplicación): índices únicos parciales para la unicidad entre vigentes, CHECKs de dinero/stock/estado y claves foráneas a catálogo.

## What Changes

- **`app/modules/usuarios/models.py`**: `usuario`, `asignacion_rol`, `intento_acceso`, `evento_seguridad`.
- **`app/modules/clientes/models.py`**: `cliente`, `vehiculo`.
- **`app/modules/repuestos/models.py`**: `repuesto`, `movimiento_stock`, `historial_precio_repuesto`.
- **`app/modules/ordenes/models.py`**: `estado_orden`, `orden_trabajo`, `item_orden`, `historial_estado_orden`.
- **`app/models.py`**: registro central que importa los 13 modelos en un solo punto (lo usará `env.py` de Alembic en `C-04`).
- **Restricciones en la base**: CHECK de rol, `anio BETWEEN 1950 AND 2100`, `precio > 0`, `stock >= 0`, `cantidad <> 0` (IN-01), `precio_nuevo > 0` y `precio_nuevo <> precio_anterior` (IN-02), `cantidad > 0`, `precio_unitario > 0`, `total >= 0`; tres índices únicos **parciales** (`asignacion_rol`, `vehiculo`, `repuesto`) y UNIQUE comunes (`usuario.email`, `cliente.usuario_id`, `cliente.documento`, `estado_orden.posicion`, `item_orden(orden_id, repuesto_id)`).
- **Tipos**: dinero en `Decimal` + `NUMERIC(10,2)` / `NUMERIC(12,2)`; **todas** las fechas `timestamptz`.
- **Índices**: cada clave foránea lleva su índice explícito; `intento_acceso` lleva `(email, ip, cuando)`.
- **Navegación**: relación declarada en los **dos extremos** de cada vínculo leído; `Usuario.cliente` devuelve **un objeto** (no una lista).
- No se agregan dependencias ni endpoints: los modelos se verifican por introspección del metadata y por DDL ejecutado contra PostgreSQL real dentro de una transacción revertida (la suite formal llega con `C-05`).

## Capabilities

### New Capabilities
- `identity-models`: contrato de las tablas de identidad y accesos (`usuario`, `asignacion_rol`, `intento_acceso`, `evento_seguridad`): unicidad del correo, roles con vigencia y una sola asignación abierta por rol.
- `customer-models`: contrato de la cartera de clientes (`cliente`, `vehiculo`): 1:1 opcional con usuario, documento único, patente única entre vigentes y rango de año.
- `inventory-models`: contrato de repuestos y stock (`repuesto`, `movimiento_stock`, `historial_precio_repuesto`): dinero `NUMERIC`, precio/stock no negativos, movimiento con cantidad distinta de cero y unicidad del código entre vigentes.
- `work-order-models`: contrato de las órdenes (`estado_orden`, `orden_trabajo`, `item_orden`, `historial_estado_orden`): catálogo por código, total no negativo, composición de ítems sin repuestos repetidos e historial de transiciones.
- `domain-schema-conventions`: reglas transversales que valen para las 13 tablas: nombres obligatorios, dinero `NUMERIC`/`Decimal`, fechas `timestamptz`, un índice por cada clave foránea y navegación declarada en ambos extremos de cada relación.

### Modified Capabilities
- Ninguna. `core-persistence` no cambia: los modelos se apoyan en `BaseRepository`/`SoftDeleteRepository` tal como están.

## Impact

- **Código**: `app/modules/{usuarios,clientes,repuestos,ordenes}/models.py` (nuevos) y `app/models.py` (nuevo). `app/core/*` no se toca.
- **Base de datos**: define las 13 tablas; `C-04 migrations-and-seed` genera la migración desde este metadata y agrega los disparadores de sólo agregado.
- **Dependencias**: ninguna nueva (SQLModel/SQLAlchemy ya están en `requirements.txt`).
- **Habilitado**: `C-04` (migraciones y seed) y, en cascada, los changes de auth, clientes, repuestos y órdenes.
