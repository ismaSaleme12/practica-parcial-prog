# Migraciones

El esquema de la base se crea **sólo** con Alembic. `create_all` está prohibido
y `seed.py` **no** crea tablas: si la base no está migrada, el seed falla y pide
correr `alembic upgrade head`.

## Ciclo de trabajo

```powershell
# 1. Esquema
.\.venv\Scripts\alembic upgrade head

# 2. Datos iniciales
.\.venv\Scripts\python.exe seed.py

# 3. Reversibilidad (siempre sobre una base de prueba, no sobre la de desarrollo)
$env:POSTGRES_DB = "taller_mecanico_test"
.\.venv\Scripts\alembic downgrade base
.\.venv\Scripts\alembic upgrade head
```

La URL sale de `app.core.config.settings` (variables de entorno o `.env`).
`alembic.ini` no guarda credenciales.

## Las dos revisiones

| Revisión | Cómo se escribió | Qué hace |
|---|---|---|
| `0001_crea_las_tablas` | `--autogenerate` y revisión manual | Las trece tablas, índices, UNIQUE, CHECK e índices únicos parciales. `estado_orden` nace **vacía**: sus filas son datos y las carga el seed. |
| `0002_solo_agregado` | **a mano** | Función y disparadores que rechazan `UPDATE` y `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` (RN-15). |

La comparación automática de Alembic no ve funciones ni disparadores: por eso la
segunda revisión es manual. **Se lee antes de aplicarla** (DD-14).

## Sólo agregado y seed

Los disparadores rechazan el borrado fila por fila, así que `seed.py` reinicia
con `TRUNCATE … RESTART IDENTITY CASCADE`, que no dispara `BEFORE UPDATE OR
DELETE`. La API nunca trunca: el permiso vive en el script de puesta en marcha.

Si hay que modificar una fila de auditoría (no debería pasar), el camino no es
desactivar el disparador: se agrega una tabla nueva con la corrección y se deja
la historia como está.
