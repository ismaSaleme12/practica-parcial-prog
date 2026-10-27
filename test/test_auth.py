"""Réplica automatizada de ``test/auth.http`` (change C-07).

Cubre la autenticación completa del módulo ``usuarios``:

- Registro abierto: usuario + rol CLIENTE + ficha de cliente en un solo UoW
  (RN-02); documento/email repetido → 409 sin apropiarse de la ficha existente.
- Login: límite de intentos **antes** del hash (RN-08, 429 con ``Retry-After``),
  hash ficticio cuando el correo no existe (RN-09), token sólo en la cookie
  ``access_token`` (nunca en el cuerpo ni por ``Authorization: Bearer``).
- Sesión: ``/auth/yo`` y ``/auth/cambiar-password``.
- Cambio de contraseña: invalida los tokens anteriores sin esperar (RN-07),
  comparando ``iat`` con ``password_cambiada_en`` sin truncar.
- ``password_hash`` nunca aparece en ninguna respuesta.

Usa los fixtures de ``C-05`` (``test/conftest.py``): ``client`` es un
``httpx.AsyncClient`` con ``ASGITransport``, el seed se re-ejecuta antes de cada
test y ``asyncio_mode = auto`` evita el decorador en cada ``async def``.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from app.modules.usuarios import service

MENSAJE_CREDENCIALES = "Credenciales inválidas."


async def _escalar(motor, sql: str, **parametros: Any):
    """Ejecuta una consulta escalar contra la base real de test."""
    async with motor.connect() as conexion:
        resultado = await conexion.execute(text(sql), parametros)
        return resultado.scalar_one()


async def _filas(motor, sql: str, **parametros: Any) -> list[tuple]:
    """Ejecuta una consulta y devuelve todas sus filas."""
    async with motor.connect() as conexion:
        resultado = await conexion.execute(text(sql), parametros)
        return list(resultado.all())


# --- registro (RN-02) -------------------------------------------------------


async def test_registro_crea_usuario_rol_y_ficha_en_un_solo_uow(client, motor):
    respuesta = await client.post(
        "/auth/registro",
        json={
            "email": "autoregistro@example.com",
            "nombre": "Auto Registro",
            "password": "secreto123",
            "documento": "40111222",
            "telefono": "1145550099",
        },
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["email"] == "autoregistro@example.com"
    assert cuerpo["nombre"] == "Auto Registro"
    assert cuerpo["activo"] is True
    assert cuerpo["debe_cambiar_password"] is False
    assert "password_hash" not in cuerpo
    assert "$2b$" not in respuesta.text

    usuario_id = await _escalar(
        motor, "SELECT id FROM usuario WHERE email = :email", email=cuerpo["email"]
    )
    roles = await _filas(
        motor,
        """
        SELECT rol, revocada_en
          FROM asignacion_rol
         WHERE usuario_id = :usuario_id
        """,
        usuario_id=usuario_id,
    )
    assert roles == [("CLIENTE", None)]

    ficha = await _filas(
        motor,
        """
        SELECT usuario_id, nombre, documento, telefono
          FROM cliente
         WHERE documento = :documento
        """,
        documento="40111222",
    )
    assert ficha == [(usuario_id, "Auto Registro", "40111222", "1145550099")]


async def test_registro_documento_repetido_responde_409_y_no_se_apropia(client, motor):
    # Jorge existe en el seed como cliente SIN usuario; su documento no se puede
    # reutilizar para crear una cuenta y la ficha no debe quedar asociada.
    antes = await _filas(
        motor,
        "SELECT id, usuario_id FROM cliente WHERE documento = :documento",
        documento="27888999",
    )
    assert len(antes) == 1
    assert antes[0][1] is None

    respuesta = await client.post(
        "/auth/registro",
        json={
            "email": "intruso@example.com",
            "nombre": "Intruso",
            "password": "secreto123",
            "documento": "27888999",
            "telefono": "1145550088",
        },
    )

    assert respuesta.status_code == 409
    assert "duplicate key" not in respuesta.text.lower()
    assert "uq_cliente_documento" not in respuesta.text

    # Ni usuario, ni rol, ni ficha nueva: el UoW revirtió las tres escrituras.
    creados = await _escalar(
        motor,
        "SELECT count(*) FROM usuario WHERE email = :email",
        email="intruso@example.com",
    )
    assert creados == 0

    despues = await _filas(
        motor,
        "SELECT id, usuario_id FROM cliente WHERE documento = :documento",
        documento="27888999",
    )
    assert despues == antes  # la ficha de Jorge sigue sin usuario


async def test_registro_email_repetido_responde_409(client, motor):
    respuesta = await client.post(
        "/auth/registro",
        json={
            "email": "admin@example.com",
            "nombre": "Administrador Repetido",
            "password": "secreto123",
            "documento": "40999888",
            "telefono": "1145550090",
        },
    )

    assert respuesta.status_code == 409
    assert "password_hash" not in respuesta.text
    ficha = await _escalar(
        motor,
        "SELECT count(*) FROM cliente WHERE documento = :documento",
        documento="40999888",
    )
    assert ficha == 0  # el rollback no deja la ficha suelta


# --- login (RN-08, RN-09) y cookie (US-011) --------------------------------


async def test_login_exitoso_responde_sin_token_y_deja_cookie_httponly(client):
    respuesta = await client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "secreto123"}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"mensaje", "debe_cambiar_password", "expira_en_segundos"}
    assert cuerpo["mensaje"] == "Sesión iniciada"
    assert cuerpo["debe_cambiar_password"] is False
    assert cuerpo["expira_en_segundos"] > 0
    assert "access_token" not in respuesta.text  # el token NO viaja en el cuerpo

    cookie = respuesta.headers.get("set-cookie", "")
    assert "access_token=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert f"Max-Age={cuerpo['expira_en_segundos']}" in cookie
    # COOKIE_SECURE=false en la suite: la cookie no lleva Secure, pero el
    # atributo es configurable (settings.COOKIE_SECURE).


async def test_login_de_nuevo_informa_el_cambio_obligatorio(client):
    respuesta = await client.post(
        "/auth/login", json={"email": "nuevo@example.com", "password": "secreto123"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["debe_cambiar_password"] is True


async def test_correo_inexistente_responde_igual_que_password_mala(client):
    inexistente = await client.post(
        "/auth/login",
        json={"email": "no-existe@example.com", "password": "secreto123"},
    )
    mala = await client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "clave-equivocada"},
    )

    assert inexistente.status_code == 401
    assert mala.status_code == 401
    assert inexistente.json() == mala.json() == {"detail": MENSAJE_CREDENCIALES}


async def test_cinco_fallos_activan_429_con_retry_after_sin_calcular_hash(
    client, motor, monkeypatch
):
    for _ in range(5):
        respuesta = await client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "mala"},
        )
        assert respuesta.status_code == 401

    # Los cinco fallos quedaron anotados: cada intento se escribió en su propia
    # sesión y transacción, confirmada siempre (DD-09).
    fallos = await _escalar(
        motor,
        """
        SELECT count(*)
          FROM intento_acceso
         WHERE email = :email AND exito = false
        """,
        email="admin@example.com",
    )
    assert fallos == 5

    async def _prohibido(*_args, **_kwargs):
        raise AssertionError("el 429 no debe calcular ni verificar ningún hash")

    monkeypatch.setattr(service, "verify_password", _prohibido)

    bloqueado = await client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "mala"}
    )

    assert bloqueado.status_code == 429
    assert "retry-after" in bloqueado.headers
    assert int(bloqueado.headers["retry-after"]) >= 1
    assert "hash" not in bloqueado.text.lower()
    # El sexto intento ni siquiera anota una fila nueva: no se verificó.
    fallos = await _escalar(
        motor,
        """
        SELECT count(*)
          FROM intento_acceso
         WHERE email = :email AND exito = false
        """,
        email="admin@example.com",
    )
    assert fallos == 5


async def test_un_login_correcto_reinicia_la_cuenta_de_fallos(client):
    for _ in range(4):
        fallida = await client.post(
            "/auth/login", json={"email": "admin@example.com", "password": "mala"}
        )
        assert fallida.status_code == 401

    correcta = await client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "secreto123"}
    )
    assert correcta.status_code == 200

    for _ in range(4):
        despues = await client.post(
            "/auth/login", json={"email": "admin@example.com", "password": "mala"}
        )
        assert despues.status_code == 401

    # Sólo hay 4 fallos después del último login correcto: todavía no hay 429.
    ultimo = await client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "mala"}
    )
    assert ultimo.status_code == 401


# --- cookie vs Bearer (caso C-03) ------------------------------------------


async def test_authorization_bearer_no_autentica_solo_sirve_la_cookie(client, login):
    token = await login("admin@example.com")
    client.cookies.clear()

    por_bearer = await client.get(
        "/auth/yo", headers={"Authorization": f"Bearer {token}"}
    )
    assert por_bearer.status_code == 401

    sin_cookie = await client.get("/auth/yo")
    assert sin_cookie.status_code == 401

    por_cookie = await client.get(
        "/auth/yo", headers={"Cookie": f"access_token={token}"}
    )
    assert por_cookie.status_code == 200
    assert por_cookie.json()["usuario"]["email"] == "admin@example.com"


async def test_yo_devuelve_roles_vigentes_y_roles_del_token(client, login):
    await login("mecanico@example.com")

    respuesta = await client.get("/auth/yo")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["usuario"]["email"] == "mecanico@example.com"
    assert cuerpo["roles_vigentes"] == ["MECANICO"]
    assert cuerpo["roles_token"] == ["MECANICO"]


# --- cambio de contraseña (RN-07) ------------------------------------------


async def test_cambio_de_password_invalida_el_token_anterior_sin_esperar(client, login):
    token_viejo = await login("nuevo@example.com")
    assert "MECANICO" in (
        await client.get("/auth/yo")
    ).json()["roles_vigentes"]

    cambio = await client.post(
        "/auth/cambiar-password",
        json={
            "password_actual": "secreto123",
            "password_nueva": "NuevaClaveSegura2026",
        },
    )

    assert cambio.status_code == 200, cambio.text
    assert cambio.json()["debe_cambiar_password"] is False
    token_nuevo = cambio.cookies.get("access_token") or client.cookies.get(
        "access_token"
    )
    assert token_nuevo and token_nuevo != token_viejo
    assert "access_token" not in cambio.text

    client.cookies.clear()
    anterior = await client.get(
        "/auth/yo", headers={"Cookie": f"access_token={token_viejo}"}
    )
    nuevo = await client.get(
        "/auth/yo", headers={"Cookie": f"access_token={token_nuevo}"}
    )

    # El token emitido antes deja de valer en la misma petición siguiente: no
    # se espera a que venza (RN-07, iat vs password_cambiada_en sin truncar).
    assert anterior.status_code == 401
    assert nuevo.status_code == 200
    assert nuevo.json()["usuario"]["debe_cambiar_password"] is False


async def test_password_actual_mala_responde_401(client, login):
    await login("nuevo@example.com")

    respuesta = await client.post(
        "/auth/cambiar-password",
        json={"password_actual": "no-es-la-actual", "password_nueva": "NuevaClave2026"},
    )

    assert respuesta.status_code == 401


@pytest.mark.parametrize(
    "password_nueva",
    [
        "12345678",  # exactamente 8 bytes: el Flujo 4 la rechaza (≤ 8)
        "ñ" * 4,  # 4 caracteres, 8 bytes: el límite se mide en bytes
        "a" * 73,  # más de 72 bytes (bcrypt la rechazaría con 500)
    ],
)
async def test_password_nueva_fuera_de_rango_responde_422(
    client, login, password_nueva
):
    await login("nuevo@example.com")

    respuesta = await client.post(
        "/auth/cambiar-password",
        json={"password_actual": "secreto123", "password_nueva": password_nueva},
    )

    assert respuesta.status_code == 422
    assert "bytes" in respuesta.text


async def test_password_nueva_de_nueve_bytes_se_acepta(client, login):
    await login("nuevo@example.com")

    respuesta = await client.post(
        "/auth/cambiar-password",
        json={"password_actual": "secreto123", "password_nueva": "123456789"},
    )

    assert respuesta.status_code == 200


# --- logout ----------------------------------------------------------------


async def test_logout_borra_la_cookie(client, login):
    await login("cliente@example.com")

    respuesta = await client.post("/auth/logout")

    assert respuesta.status_code == 200
    cookie = respuesta.headers.get("set-cookie", "")
    assert "access_token=" in cookie
    assert "Max-Age=0" in cookie

    # Tras el logout, el cliente ya no tiene la cookie y /auth/yo da 401.
    respuesta_yo = await client.get("/auth/yo")
    assert respuesta_yo.status_code == 401


# --- ninguna respuesta filtra el hash --------------------------------------


async def test_ninguna_respuesta_de_auth_incluye_password_hash(client):
    registro = await client.post(
        "/auth/registro",
        json={
            "email": "sin-hash@example.com",
            "nombre": "Sin Hash",
            "password": "secreto123",
            "documento": "41222333",
            "telefono": "1145550077",
        },
    )
    login = await client.post(
        "/auth/login", json={"email": "sin-hash@example.com", "password": "secreto123"}
    )
    yo = await client.get("/auth/yo")
    cambio = await client.post(
        "/auth/cambiar-password",
        json={"password_actual": "secreto123", "password_nueva": "OtraClaveSegura2026"},
    )

    assert [registro.status_code, login.status_code, yo.status_code] == [201, 200, 200]
    assert cambio.status_code == 200

    for respuesta in (registro, login, yo, cambio):
        assert "password_hash" not in respuesta.text
        assert "$2b$" not in respuesta.text
