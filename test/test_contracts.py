"""Réplica automatizada de ``test/contracts.http`` (change C-06).

Cubre los contratos de entrada y el manejo central de errores:

- ``extra="forbid"`` → 422 (repuestos y usuarios).
- Contraseña de más de 72 **bytes** → 422 (y 72 exactos → 201).
- Página fuera de rango y parámetros de paginación inválidos → 422.
- ``IntegrityError`` → 409 con mensaje propio (sin texto del motor).
- Recurso de la ruta inexistente → 404 con mensaje propio.
- Dinero como string Decimal y búsqueda ``q`` con parámetros ligados.

Usa los fixtures de ``C-05`` (``test/conftest.py``): ``client`` es un
``httpx.AsyncClient`` con ``ASGITransport`` y el seed se re-ejecuta antes de
cada test, así que cada uno arranca con los cuatro repuestos y los siete
usuarios base. ``asyncio_mode = auto``: los ``async def`` corren sin decorador.

``C-08`` movió ``/usuarios`` y ``/repuestos`` al grupo protegido: los tests que
los ejercitan reciben el fixture ``admin`` para conservar exactamente la misma
cobertura del contrato, ahora con una sesión ADMIN real. Ningún caso se eliminó.
"""

import pytest
from pydantic import ValidationError

from app.core.schemas import cambios_enviados
from app.modules.repuestos.schemas import RepuestoPatch

MENSAJE_VALIDACION = "La petición no cumple el contrato."
MENSAJE_CONFLICTO = "La operación entra en conflicto con datos ya guardados."


@pytest.fixture
async def admin(login):
    """Sesión ADMIN para los endpoints que dejaron de ser públicos en C-08.

    ``C-06`` ejercitó los contratos de ``/usuarios`` y ``/repuestos`` sin
    cookie porque todavía no existía autorización. ``C-08`` los movió al grupo
    protegido: la cobertura es la misma, ahora con una sesión ADMIN real.
    """
    await login("admin@example.com")


def _campos(cuerpo: dict) -> str:
    """Concatena los campos del error de validación para poder buscarlos."""
    return " ".join(error.get("campo", "") for error in cuerpo.get("errores", []))


# --- extra="forbid" ---------------------------------------------------------


async def test_extra_forbid_rechaza_stock_en_el_alta_de_repuesto(client, admin):
    respuesta = await client.post(
        "/repuestos",
        json={
            "codigo": "ZZ-999",
            "descripcion": "Repuesto de prueba",
            "precio": "1000.00",
            "stock": 5,
        },
    )

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["detail"] == MENSAJE_VALIDACION
    assert "stock" in _campos(cuerpo)


async def test_extra_forbid_rechaza_rol_y_password_hash_en_usuarios(client, admin):
    respuesta = await client.post(
        "/usuarios",
        json={
            "email": "nuevo-staff@example.com",
            "nombre": "Nuevo Staff",
            "password": "secreto123",
            "rol": "ADMIN",
            "password_hash": "x",
        },
    )

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["detail"] == MENSAJE_VALIDACION
    campos = _campos(cuerpo)
    assert "rol" in campos
    assert "password_hash" in campos


# --- contraseñas: el límite es en bytes ------------------------------------


async def test_password_de_73_bytes_responde_422(client, admin):
    respuesta = await client.post(
        "/usuarios",
        json={
            "email": "clave-larga@example.com",
            "nombre": "Clave Larga",
            "password": "a" * 73,
        },
    )

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert "72 bytes" in " ".join(
        error.get("mensaje", "") for error in cuerpo.get("errores", [])
    )


async def test_password_multibyte_se_mide_en_bytes_no_en_caracteres(client, admin):
    # 37 «ñ» son 37 caracteres y 74 bytes en UTF-8.
    password = "ñ" * 37
    assert len(password) == 37
    assert len(password.encode("utf-8")) == 74

    respuesta = await client.post(
        "/usuarios",
        json={
            "email": "clave-multibyte@example.com",
            "nombre": "Clave Multibyte",
            "password": password,
        },
    )

    assert respuesta.status_code == 422
    assert "72 bytes" in " ".join(
        error.get("mensaje", "") for error in respuesta.json().get("errores", [])
    )


async def test_password_de_exactamente_72_bytes_se_acepta(client, admin):
    respuesta = await client.post(
        "/usuarios",
        json={
            "email": "clave-limite@example.com",
            "nombre": "Clave Límite",
            "password": "a" * 72,
        },
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["email"] == "clave-limite@example.com"
    assert cuerpo["debe_cambiar_password"] is True


# --- respuestas sin password_hash ------------------------------------------


async def test_alta_de_usuario_no_expone_password_hash(client, admin):
    respuesta = await client.post(
        "/usuarios",
        json={
            "email": "nuevo-staff@example.com",
            "nombre": "Nuevo Staff",
            "password": "secreto123",
        },
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert "password_hash" not in cuerpo
    assert "$2b$" not in respuesta.text  # ni siquiera el hash como valor suelto


# --- listado paginado ------------------------------------------------------


async def test_listado_devuelve_el_envoltorio_uniforme(client, admin):
    respuesta = await client.get("/repuestos", params={"size": 2})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"items", "total", "page", "size", "pages"}
    assert cuerpo["total"] == 4
    assert cuerpo["page"] == 1
    assert cuerpo["size"] == 2
    assert cuerpo["pages"] == 2
    assert [item["codigo"] for item in cuerpo["items"]] == ["FA-001", "PF-002"]


async def test_paginas_consecutivas_no_repiten_filas(client, admin):
    primera = await client.get("/repuestos", params={"page": 1, "size": 2})
    segunda = await client.get("/repuestos", params={"page": 2, "size": 2})

    codigos_primera = [item["codigo"] for item in primera.json()["items"]]
    codigos_segunda = [item["codigo"] for item in segunda.json()["items"]]

    assert codigos_primera == ["FA-001", "PF-002"]
    assert codigos_segunda == ["BU-003", "AC-004"]
    assert set(codigos_primera).isdisjoint(codigos_segunda)


async def test_dinero_viaja_como_string_decimal(client, admin):
    respuesta = await client.get("/repuestos", params={"q": "Filtro"})

    assert respuesta.status_code == 200
    items = respuesta.json()["items"]
    assert len(items) == 1
    precio = items[0]["precio"]
    assert isinstance(precio, str)
    assert precio == "8500.00"


async def test_pagina_fuera_de_rango_responde_422_con_mensaje_propio(client, admin):
    respuesta = await client.get("/repuestos", params={"page": 3, "size": 2})

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == "La página 3 no existe: hay 2."


async def test_parametros_de_paginacion_invalidos_responden_422(client, admin):
    pagina_cero = await client.get("/repuestos", params={"page": 0})
    size_grande = await client.get("/repuestos", params={"size": 101})
    pagina_no_entera = await client.get("/repuestos", params={"page": "abc"})

    assert pagina_cero.status_code == 422
    assert size_grande.status_code == 422
    assert pagina_no_entera.status_code == 422


# --- búsqueda con parámetros ligados --------------------------------------


async def test_busqueda_con_comilla_no_inyecta_sql(client, admin):
    respuesta = await client.get("/repuestos", params={"q": "' OR '1'='1"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["items"] == []
    assert cuerpo["total"] == 0
    assert cuerpo["pages"] == 0


# --- IntegrityError → 409 --------------------------------------------------


async def test_codigo_de_repuesto_repetido_responde_409_sin_texto_del_motor(client, admin):
    respuesta = await client.post(
        "/repuestos",
        json={
            "codigo": "FA-001",
            "descripcion": "Otro filtro",
            "precio": "9999.00",
        },
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == MENSAJE_CONFLICTO
    texto = respuesta.text.lower()
    assert "duplicate" not in texto
    assert "uq_repuesto" not in texto
    assert "fa-001" not in texto
    assert "traceback" not in texto


async def test_email_repetido_responde_409_sin_texto_del_motor(client, admin):
    respuesta = await client.post(
        "/usuarios",
        json={
            "email": "admin@example.com",
            "nombre": "Administrador Repetido",
            "password": "secreto123",
        },
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == MENSAJE_CONFLICTO
    texto = respuesta.text.lower()
    assert "duplicate" not in texto
    assert "uq_usuario_email" not in texto
    assert "admin@example.com" not in texto


# --- 404 -------------------------------------------------------------------


async def test_repuesto_inexistente_responde_404_con_mensaje_propio(client, admin):
    respuesta = await client.get("/repuestos/999999")

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "No existe el repuesto con id 999999."


async def test_ruta_inexistente_responde_404_sin_traza(client):
    respuesta = await client.get("/ruta-que-no-existe")

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "La ruta solicitada no existe."


# --- entrada inválida: nunca 500 ------------------------------------------


async def test_entradas_invalidas_nunca_terminan_en_500(client, admin):
    precio_cero = await client.post(
        "/repuestos",
        json={"codigo": "ZZ-998", "descripcion": "Inválido", "precio": "0.00"},
    )
    email_invalido = await client.post(
        "/usuarios",
        json={"email": "no-es-un-email", "nombre": "Sin Arroba", "password": "secreto123"},
    )
    nombre_largo = await client.post(
        "/usuarios",
        json={"email": "largo@example.com", "nombre": "x" * 121, "password": "secreto123"},
    )

    assert precio_cero.status_code == 422
    assert email_invalido.status_code == 422
    assert nombre_largo.status_code == 422


# --- convención de PATCH (exclude_unset) ----------------------------------


def test_patch_aplica_solo_los_campos_enviados():
    cambios = cambios_enviados(RepuestoPatch(descripcion="Pastillas nuevas"))

    assert cambios == {"descripcion": "Pastillas nuevas"}


def test_patch_no_declara_stock():
    with pytest.raises(ValidationError):
        RepuestoPatch(stock=5)
