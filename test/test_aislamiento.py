"""El estado base se restaura entre tests: cada uno arranca del seed.

Es la garantía de la que dependen todos los changes siguientes: un test puede
escribir, romper o borrar lo que quiera porque el siguiente vuelve a encontrar
los conteos y valores de ``seed.py``. Se comprueba en dos pasos porque la
restauración ocurre **entre** tests, no dentro de uno.
"""

from sqlalchemy import text


async def test_1_un_test_puede_ensuciar_el_estado(motor) -> None:
    async with motor.begin() as conexion:
        await conexion.execute(
            text("UPDATE repuesto SET stock = 999 WHERE codigo = 'FA-001'")
        )
        stock = (
            await conexion.execute(
                text("SELECT stock FROM repuesto WHERE codigo = 'FA-001'")
            )
        ).scalar_one()

    assert stock == 999


async def test_2_el_siguiente_test_ve_el_estado_del_seed(motor) -> None:
    async with motor.connect() as conexion:
        stock = (
            await conexion.execute(
                text("SELECT stock FROM repuesto WHERE codigo = 'FA-001'")
            )
        ).scalar_one()

    assert stock == 10
