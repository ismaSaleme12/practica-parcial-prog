"""Réplica automatizada de ``test/rbac.http`` (change C-08, Épica 5).

Cubre la autorización decidida **en la base en cada petición** (RN-04), los dos
grupos de rutas (DD-05 / RN-06), la administración de roles con vigencia
(RN-03, RN-05) y la auditoría en ``evento_seguridad`` (US-016).

Casos de la consigna que se automatizan acá:

- **C-07** — revocar un rol le quita el permiso a una sesión ya abierta, sin
  esperar a que venza el token (ni volver a loguearse).
- **C-08** — autoprotección: un ADMIN no se revoca su propio ADMIN y el sistema
  no queda sin administradores vigentes.

Usa los fixtures de ``C-05`` (``test/conftest.py``): ``client`` es un
``httpx.AsyncClient`` con ``ASGITransport``, el seed se re-ejecuta antes de cada
test (ids deterministas: 1 admin, 2 admin2, 3 recepción, 4 mecánico, 5 mecánico
dos, 6 cliente, 7 nuevo) y ``asyncio_mode = auto`` evita el decorador.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from app.core.security import crear_token

MENSAJE_CONFLICTO = "La operación entra en conflicto con datos ya guardados."


async def _filas(motor, sql: str, **parametros: Any) -> list[tuple]:
    """Ejecuta una consulta contra la base real de test y devuelve sus filas."""
    async with motor.connect() as conexion:
        resultado = await conexion.execute(text(sql), parametros)
        return list(resultado.all())


async def _escalar(motor, sql: str, **parametros: Any):
    async with motor.connect() as conexion:
        resultado = await conexion.execute(text(sql), parametros)
        return resultado.scalar_one()


def _cookie(token: str) -> dict[str, str]:
    """Cabecera con una sesión concreta (el token viaja sólo en la cookie)."""
    return {"Cookie": f"access_token={token}"}


# --- US-013: 401 (sin sesión) vs 403 (sin permiso) -------------------------


async def test_sin_cookie_el_grupo_protegido_responde_401(client):
    assert (await client.get("/repuestos")).status_code == 401
    assert (await client.get("/eventos")).status_code == 401
    assert (await client.get("/usuarios/1/roles")).status_code == 401
    assert (
        await client.post(
            "/usuarios",
            json={
                "email": "staff@example.com",
                "nombre": "Staff",
                "password": "secreto123",
            },
        )
    ).status_code == 401
    assert (
        await client.post(
            "/repuestos",
            json={"codigo": "ZZ-900", "descripcion": "Prueba", "precio": "100.00"},
        )
    ).status_code == 401


async def test_cookie_con_rol_insuficiente_responde_403(client, login):
    await login("cliente@example.com")

    # El cliente está autenticado (no es 401) pero no tiene rol de personal.
    assert (await client.get("/repuestos")).status_code == 403
    assert (await client.get("/eventos")).status_code == 403
    assert (
        await client.post(
            "/usuarios",
            json={
                "email": "staff@example.com",
                "nombre": "Staff",
                "password": "secreto123",
            },
        )
    ).status_code == 403


async def test_matriz_de_repuestos_admin_recepcion_mecanico(client, login):
    await login("recepcion@example.com")
    assert (await client.get("/repuestos")).status_code == 200
    assert (await client.get("/repuestos/1")).status_code == 200
    assert (
        await client.post(
            "/repuestos",
            json={"codigo": "ZZ-901", "descripcion": "Prueba", "precio": "100.00"},
        )
    ).status_code == 403

    await login("mecanico@example.com")
    assert (await client.get("/repuestos")).status_code == 200
    assert (
        await client.post(
            "/repuestos",
            json={"codigo": "ZZ-902", "descripcion": "Prueba", "precio": "100.00"},
        )
    ).status_code == 403

    await login("admin@example.com")
    assert (await client.get("/repuestos")).status_code == 200
    assert (
        await client.post(
            "/repuestos",
            json={"codigo": "ZZ-903", "descripcion": "Prueba", "precio": "100.00"},
        )
    ).status_code == 201


async def test_requiere_rol_no_confia_en_los_roles_del_token(client):
    # Token válido de la recepción con un claim ``roles`` que dice ADMIN: la
    # autorización se decide en la base, así que el claim no otorga nada.
    token_mentiroso = crear_token(sub="3", roles=["ADMIN"])
    client.cookies.clear()

    respuesta = await client.get("/eventos", headers=_cookie(token_mentiroso))

    assert respuesta.status_code == 403


async def test_revocacion_tiene_efecto_inmediato_sobre_la_sesion_abierta(
    client, login, motor
):
    # Caso C-07: la recepción inicia sesión y conserva ese token.
    token_recepcion = await login("recepcion@example.com")
    assert (await client.get("/repuestos")).status_code == 200

    # El ADMIN revoca el rol con su propia sesión.
    await login("admin@example.com")
    revocacion = await client.delete("/usuarios/3/roles/RECEPCION")
    assert revocacion.status_code == 200, revocacion.text

    # La MISMA sesión abierta pierde el permiso en la petición siguiente.
    client.cookies.clear()
    bloqueado = await client.get(
        "/repuestos", headers=_cookie(token_recepcion)
    )
    assert bloqueado.status_code == 403

    fila = await _filas(
        motor,
        """
        SELECT revocada_en
          FROM asignacion_rol
         WHERE usuario_id = 3 AND rol = 'RECEPCION'
        """,
    )
    assert len(fila) == 1
    assert fila[0][0] is not None  # se escribe revocada_en; la fila no se borra

    # Reasignar el rol hace que el MISMO token viejo vuelva a pasar: la
    # autorización se consulta en la base, nunca en el token.
    await login("admin@example.com")
    reasignacion = await client.post("/usuarios/3/roles", json={"rol": "RECEPCION"})
    assert reasignacion.status_code == 201

    client.cookies.clear()
    permitido = await client.get("/repuestos", headers=_cookie(token_recepcion))
    assert permitido.status_code == 200


# --- US-014: gestión de roles con vigencia --------------------------------


async def test_listar_roles_devuelve_historial_y_404_si_el_usuario_no_existe(
    client, login
):
    await login("admin@example.com")

    respuesta = await client.get("/usuarios/4/roles")

    assert respuesta.status_code == 200, respuesta.text
    filas = respuesta.json()
    assert [fila["rol"] for fila in filas] == ["MECANICO"]
    assert filas[0]["vigente"] is True
    assert filas[0]["revocada_en"] is None

    inexistente = await client.get("/usuarios/999999/roles")
    assert inexistente.status_code == 404


async def test_asignacion_abierta_repetida_responde_409_por_el_indice_parcial(
    client, login
):
    await login("admin@example.com")

    # El mecánico 4 ya tiene MECANICO abierto desde el seed: no hay consulta
    # previa que lo rechace, el índice único parcial produce el 409.
    respuesta = await client.post("/usuarios/4/roles", json={"rol": "MECANICO"})

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == MENSAJE_CONFLICTO


async def test_asignar_rol_con_vence_en_con_zona_y_futuro_es_201(client, login):
    await login("mecanico@example.com")  # token con roles informativos viejos
    token_mecanico = client.cookies.get("access_token")
    assert (await client.get("/eventos")).status_code == 403

    await login("admin@example.com")
    vence = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    respuesta = await client.post(
        "/usuarios/4/roles", json={"rol": "ADMIN", "vence_en": vence}
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["rol"] == "ADMIN"
    assert cuerpo["vigente"] is True
    assert cuerpo["vence_en"] is not None and cuerpo["revocada_en"] is None

    # El token emitido antes de la asignación ya sirve para el nuevo rol: los
    # permisos se consultan en la base en cada petición (RN-04).
    client.cookies.clear()
    assert (
        await client.get("/eventos", headers=_cookie(token_mecanico))
    ).status_code == 200


async def test_vence_en_sin_zona_horaria_responde_422(client, login):
    await login("admin@example.com")

    respuesta = await client.post(
        "/usuarios/3/roles",
        json={"rol": "MECANICO", "vence_en": "2026-12-31T23:59:59"},
    )

    assert respuesta.status_code == 422
    assert "zona horaria" in respuesta.text.lower()


async def test_vence_en_en_el_pasado_responde_422(client, login):
    await login("admin@example.com")

    respuesta = await client.post(
        "/usuarios/3/roles",
        json={"rol": "MECANICO", "vence_en": "2020-01-01T00:00:00+00:00"},
    )

    assert respuesta.status_code == 422
    assert "futura" in respuesta.text.lower()


async def test_reasignar_un_rol_vencido_cierra_la_fila_y_abre_una_nueva(
    client, login, motor
):
    # El seed deja MECANICO abierto para el usuario 5; se simula su vencimiento
    # sin revocarlo (asignacion_rol no es de sólo agregado).
    async with motor.begin() as conexion:
        await conexion.execute(
            text(
                """
                UPDATE asignacion_rol
                   SET vence_en = now() - interval '1 day'
                 WHERE usuario_id = 5 AND rol = 'MECANICO'
                   AND revocada_en IS NULL
                """
            )
        )

    await login("admin@example.com")
    respuesta = await client.post("/usuarios/5/roles", json={"rol": "MECANICO"})

    assert respuesta.status_code == 201, respuesta.text

    filas = await _filas(
        motor,
        """
        SELECT revocada_en
          FROM asignacion_rol
         WHERE usuario_id = 5 AND rol = 'MECANICO'
         ORDER BY id
        """,
    )
    assert len(filas) == 2
    assert filas[0][0] is not None  # la fila vencida quedó cerrada
    assert filas[1][0] is None  # la nueva está abierta


# --- US-014 CA-4 / RN-05: autoprotección -----------------------------------


async def test_admin_no_puede_revocarse_su_propio_rol_admin(client, login, motor):
    await login("admin@example.com")

    respuesta = await client.delete("/usuarios/1/roles/ADMIN")

    assert respuesta.status_code == 409
    assert "propio" in respuesta.json()["detail"].lower()

    sigue_abierta = await _escalar(
        motor,
        """
        SELECT count(*)
          FROM asignacion_rol
         WHERE usuario_id = 1 AND rol = 'ADMIN' AND revocada_en IS NULL
        """,
    )
    assert sigue_abierta == 1


async def test_el_sistema_no_queda_sin_administradores_vigentes(client, login):
    token_admin2 = await login("admin2@example.com")

    await login("admin@example.com")
    # Con dos ADMIN vigentes se puede revocar el de otro; queda uno.
    assert (await client.delete("/usuarios/2/roles/ADMIN")).status_code == 200

    # El admin2 conserva una sesión válida, pero ya no tiene el rol ADMIN.
    client.cookies.clear()
    assert (
        await client.get("/eventos", headers=_cookie(token_admin2))
    ).status_code == 403

    # El único ADMIN vigente tampoco puede revocarse a sí mismo: 0 ADMINs es
    # inalcanzable (RN-05).
    await login("admin@example.com")
    assert (await client.delete("/usuarios/1/roles/ADMIN")).status_code == 409


# --- US-015 / RN-06: cambio obligatorio de contraseña ---------------------


async def test_debe_cambiar_password_bloquea_el_grupo_protegido_pero_no_auth(
    client, login
):
    await login("nuevo@example.com")

    # /auth sigue accesible: el afectado puede cambiar la clave.
    assert (await client.get("/auth/yo")).status_code == 200

    # Todo el grupo protegido responde 403 mientras el cambio esté pendiente.
    assert (await client.get("/repuestos")).status_code == 403
    assert (await client.get("/eventos")).status_code == 403

    cambio = await client.post(
        "/auth/cambiar-password",
        json={
            "password_actual": "secreto123",
            "password_nueva": "NuevaClaveSegura2026",
        },
    )
    assert cambio.status_code == 200, cambio.text

    # Con la cookie nueva del cambio, el grupo protegido ya responde 200.
    assert (await client.get("/repuestos")).status_code == 200


# --- US-003/US-014/US-016: evento_seguridad -------------------------------


async def test_alta_de_personal_registra_evento_y_password_provisoria(client, login, motor):
    await login("admin@example.com")

    respuesta = await client.post(
        "/usuarios",
        json={
            "email": "staff@example.com",
            "nombre": "Staff Nuevo",
            "password": "secreto123",
        },
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["debe_cambiar_password"] is True
    assert "password_hash" not in cuerpo

    eventos = await _filas(
        motor,
        """
        SELECT actor, accion
          FROM evento_seguridad
         WHERE accion = :accion
        """,
        accion=f"Alta de usuario id {cuerpo['id']}",
    )
    assert eventos == [("admin@example.com", f"Alta de usuario id {cuerpo['id']}")]


async def test_asignar_y_revocar_rol_registran_eventos(client, login, motor):
    await login("admin@example.com")

    assert (await client.post("/usuarios/3/roles", json={"rol": "MECANICO"})).status_code == 201
    assert (await client.delete("/usuarios/3/roles/MECANICO")).status_code == 200

    acciones = await _filas(
        motor,
        """
        SELECT actor, accion
          FROM evento_seguridad
         WHERE actor = 'admin@example.com'
         ORDER BY id
        """,
    )
    assert acciones == [
        ("admin@example.com", "Asignación de rol MECANICO al usuario id 3"),
        ("admin@example.com", "Revocación de rol MECANICO al usuario id 3"),
    ]


async def test_cambio_de_password_registra_evento(client, login, motor):
    await login("nuevo@example.com")

    cambio = await client.post(
        "/auth/cambiar-password",
        json={
            "password_actual": "secreto123",
            "password_nueva": "NuevaClaveSegura2026",
        },
    )
    assert cambio.status_code == 200

    eventos = await _filas(
        motor,
        """
        SELECT actor, accion
          FROM evento_seguridad
         WHERE accion = 'Cambio de contraseña'
        """,
    )
    assert eventos == [("nuevo@example.com", "Cambio de contraseña")]


# --- US-016: GET /eventos paginado, sólo ADMIN -----------------------------


async def test_get_eventos_paginado_y_solo_admin(client, login):
    await login("admin@example.com")

    respuesta = await client.get("/eventos", params={"size": 1})

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"items", "total", "page", "size", "pages"}
    assert cuerpo["total"] >= 1
    assert cuerpo["size"] == 1
    # El seed deja el evento de la carga inicial con actor 'SISTEMA'.
    assert cuerpo["items"][0]["actor"] == "SISTEMA"

    await login("mecanico@example.com")
    assert (await client.get("/eventos")).status_code == 403

    fuera_de_rango = await client.get("/eventos", params={"page": 99})
    assert fuera_de_rango.status_code == 403  # el rol se decide antes que la página
