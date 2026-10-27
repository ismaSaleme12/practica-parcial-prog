# Tasks

> Orden TDD: primero la evidencia (`test/auth.http` + `test/test_auth.py`), después la implementación mínima que la hace pasar.

## 1. Contratos de la Épica 4

- [x] 1.1 Extender `app/modules/usuarios/schemas.py` con `RegistroCrear` (email, nombre, password, documento, teléfono; sin `rol`), `LoginCrear`, `CambioPassword`, `SesionRespuesta`, `MensajeRespuesta` y `YoRespuesta`. Verificación: `registro` con `rol` → 422 por `extra="forbid"`; toda contraseña que termina en bcrypt se mide en bytes UTF-8 (73 bytes → 422, 72 → aceptada).
- [x] 1.2 Implementar la regla de la contraseña **nueva** del cambio (más de 8 bytes y hasta 72 bytes, en UTF-8) con mensajes propios. Verificación: 8 bytes → 422; 4 «ñ» (8 bytes) → 422; 73 bytes → 422; 9 bytes → 200. Decisión documentada en `design.md` D7 con la cita del Flujo 4.

## 2. Repositorios y Unit of Work

- [x] 2.1 En `app/modules/usuarios/repository.py`: `UsuarioRepository.get_by_email` (parámetro ligado), `AsignacionRolRepository.roles_vigentes` (no revocada y sin vencer), `IntentoAccesoRepository.ultimo_exito`/`contar_fallos` y `EventoSeguridadRepository`. Verificación: ningún repositorio llama a `commit()`; las consultas usan `select` de SQLModel y filtros ligados.
- [x] 2.2 Crear `app/modules/clientes/repository.py` con `ClienteRepository(BaseRepository[Cliente])` y componerlo en `UsuariosUnitOfWork` junto con roles, intentos y eventos. Verificación: el UoW del auto-registro escribe las tres filas sobre la **misma** sesión.

## 3. Servicios

- [x] 3.1 `service.registrar`: hash **antes** del `async with uow`; dentro, `Usuario` → `AsignacionRol(CLIENTE)` → `Cliente` → `EventoSeguridad`. Verificación: alta válida crea las tres filas; documento de Jorge → 409 y su `usuario_id` sigue nulo; email repetido → 409 sin ficha suelta.
- [x] 3.2 `service.autenticar`: límite de intentos **primero** (429 con `Retry-After` sin hash), verificación contra el hash real o el ficticio, intento en sesión propia confirmada, token con roles vigentes. Verificación: 5 fallos + 6.º → 429; correo inexistente y clave mala devuelven el mismo cuerpo; un login correcto reinicia la cuenta.
- [x] 3.3 `service.roles_vigentes` y `service.cambiar_password`: verifica la actual (401 si no), calcula el hash nuevo antes del UoW de escritura, anota `password_cambiada_en` con hora completa, limpia `debe_cambiar_password` y emite el token **después** del commit. Verificación: el token anterior da 401 y el nuevo 200, sin esperar.
- [x] 3.4 `_anotar_intento`: sesión y transacción propias siempre confirmadas (DD-09), con comentario que declara la excepción y su costo. Verificación: tras 5 fallos, `intento_acceso` tiene 5 filas aunque todas las respuestas hayan sido 401.

## 4. Dependencia de sesión y router de auth

- [x] 4.1 `app/core/dependencies.py`: `get_usuario_actual` lee **sólo** `request.cookies["access_token"]`; 401 sin cookie, con token inválido/vencido, con usuario inexistente/inactivo o con `iat` anterior a `password_cambiada_en` (comparación sin truncar). Verificación: `Authorization: Bearer` con un token válido → 401; la misma petición con la cookie → 200.
- [x] 4.2 Crear `app/modules/usuarios/auth_router.py` con `prefix="/auth"`: `registro` (201), `login` (200 sin token), `logout` (200, borra la cookie), `yo` (200/401) y `cambiar-password` (200/401/422). Cookie `access_token` HttpOnly, SameSite=Lax, `Max-Age` = duración y `Secure` = `settings.COOKIE_SECURE`. Verificación: `Set-Cookie` con los cuatro atributos y cuerpo del login sin `access_token`.
- [x] 4.3 `main.py`: calcular el hash ficticio **una vez** en el lifespan (`app.state.hash_ficticio`) y montar `auth_router`. Comentario del re-montaje de `C-08` (DD-05). Verificación: el login de un correo inexistente no falla y no revela cuentas.

## 5. Evidencia y verificación

- [x] 5.1 Escribir `test/auth.http` con la respuesta esperada comentada: registro OK/repetido, login OK/mal/429, hash ficticio, cookie vs Bearer, cambio de contraseña, longitudes inválidas y logout.
- [x] 5.2 Escribir `test/test_auth.py` como réplica automatizada (18 tests) usando los fixtures `client`/`login` de `C-05`: registro documento repetido → 409 (C-02), cookie vs Bearer → 401 (C-03), cambio invalida el token previo (C-04), 429 con `Retry-After` (C-05), correo inexistente == clave mala (RN-09), `debe_cambiar_password` en el login de `nuevo@example.com`, tres filas + no apropiación (RN-02) y `password_hash` ausente en todas las respuestas.
- [x] 5.3 Correr `python -m pytest test/ -q` desde la raíz: **45 passed** (27 de `C-05`/`C-06` + 18 de `C-07`).
- [x] 5.4 `openspec validate 2026-10-27-c-07-auth --strict` en verde.

## Workflow follow-up

- **Pendiente explícito de `C-08`**: `requiere_rol(...)`, el 403 de `debe_cambiar_password`, los dos grupos de rutas de `main.py` y el re-montaje de `auth`/`health` en el grupo abierto (DD-05). Este change no los implementa.
- Revisar los artefactos y archivar con `/opsx:archive c-07-auth` cuando el orquestador lo pida (no archivar desde este change).
- No commitear: el orquestador lo hace.
