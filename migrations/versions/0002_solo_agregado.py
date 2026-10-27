"""sólo agregado: rechaza UPDATE y DELETE en las tablas de auditoría

LEER ANTES DE APLICAR (DD-14).

Esta revisión se escribe a mano porque la comparación automática de Alembic no
ve funciones ni disparadores. Qué hace y por qué:

- `historial_estado_orden`, `movimiento_stock` y `historial_precio_repuesto` son
  de sólo agregado (RN-15): nadie puede modificar ni borrar sus filas, venga de
  donde venga (API, seed o psql). INSERT sigue permitido.
- Una sola función para las tres tablas: el mensaje usa `TG_TABLE_NAME`, así que
  no se pierden datos y no hay tres copias del mismo cuerpo.
- `ERRCODE = 'integrity_constraint_violation'` (SQLSTATE 23000) hace que el
  rechazo se comporte como una violación de integridad y no como un error
  inesperado del servidor.
- El `downgrade` borra los disparadores y la función: bajar sólo esta revisión
  deja las tablas existentes y usables.
- `seed.py` reinicia con `TRUNCATE`, que no dispara `BEFORE UPDATE OR DELETE`;
  si se intenta un reset con `DELETE`, el disparador lo rechaza (es lo buscado).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FUNCION = "solo_agregado_rechazar_modificacion"
TABLAS = ("historial_estado_orden", "movimiento_stock", "historial_precio_repuesto")


def upgrade() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {FUNCION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'La tabla % es de sólo agregado: % no está permitido',
                TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'integrity_constraint_violation',
                      HINT = 'Agregá una fila nueva en lugar de modificar o borrar la existente.';
        END;
        $$;
        """
    )

    for tabla in TABLAS:
        op.execute(
            f"""
            CREATE TRIGGER trg_{tabla}_solo_agregado
            BEFORE UPDATE OR DELETE ON {tabla}
            FOR EACH ROW
            EXECUTE FUNCTION {FUNCION}();
            """
        )


def downgrade() -> None:
    for tabla in TABLAS:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tabla}_solo_agregado ON {tabla};")

    op.execute(f"DROP FUNCTION IF EXISTS {FUNCION}();")
