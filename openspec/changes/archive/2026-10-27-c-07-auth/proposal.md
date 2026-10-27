# Proposal

## Why

`C-06` dejó los contratos y el manejo de errores, pero la API todavía **no tiene identidad**: no existe forma de registrarse, iniciar sesión ni saber quién hace una petición. Todos los endpoints de negocio que vienen (`C-08` a `C-12`) necesitan un usuario actual, y la consigna pide explícitamente (Ejercicio 4) que la autenticación no filtre cuentas, no frene el bucle de eventos y no deje el token al alcance de un script.

Sin este change, cada módulo inventaría su propia autenticación y las reglas críticas quedarían dispersas: el límite de intentos podría evaluarse **después** de calcular el hash (RN-08), el correo inexistente respondería distinto o más rápido (RN-09), el token viajaría en el cuerpo o en `Authorization` (caso C-03), el cambio de contraseña no invalidaría las sesiones anteriores (RN-07) y el auto-registro podría apropiarse de la ficha de un cliente que ya existe en el taller (RN-02).

Este change implementa la **Épica 4** completa (US-009 a US-012) en el módulo `usuarios` y deja listo el punto de apoyo para `C-08`, que sólo tendrá que agregar `requiere_rol`, el 403 del cambio obligatorio y los dos grupos de rutas.

## What Changes

- **`app/modules/usuarios/schemas.py`**: se agregan los contratos de la Épica 4 — `RegistroCrear` (email, nombre, password, documento, teléfono), `LoginCrear`, `CambioPassword`, `SesionRespuesta` (sin token), `MensajeRespuesta` y `YoRespuesta`. Toda contraseña que termina en bcrypt se mide en **bytes** UTF-8 y admite **hasta 72**; la nueva del cambio además exige **más de 8 bytes**.
- **`app/modules/usuarios/repository.py`**: `UsuarioRepository.get_by_email` (parámetro ligado), `AsignacionRolRepository.roles_vigentes` (no revocada y sin vencer), `IntentoAccesoRepository` (último login correcto, conteo de fallos en la ventana y fallo más antiguo) y `EventoSeguridadRepository`. Ningún repositorio confirma.
- **`app/modules/usuarios/unit_of_work.py`**: compone además los repositorios de roles, intentos, eventos y —para RN-02— el de clientes.
- **`app/modules/clientes/repository.py`** (nuevo): `ClienteRepository(BaseRepository[Cliente])`, que `C-09` extenderá. `C-07` lo necesita para crear la ficha en el mismo UoW que el usuario y su rol.
- **`app/modules/usuarios/service.py`**: `registrar` (hash antes de abrir la transacción y las tres filas en un solo UoW), `autenticar` (límite de intentos **primero**, verificación contra el hash real o el ficticio, intento en sesión propia confirmada, token con roles vigentes), `roles_vigentes` y `cambiar_password` (verifica la actual, anota `password_cambiada_en` con hora completa, limpia el cambio obligatorio y emite el token **después**).
- **`app/core/dependencies.py`**: versión mínima de `get_usuario_actual`, que lee **sólo** `request.cookies["access_token"]` y responde 401 sin cookie, con token inválido/vencido, con usuario inexistente o inactivo, o cuando el `iat` es anterior a `password_cambiada_en` (comparación sin truncar).
- **`app/modules/usuarios/auth_router.py`** (nuevo): router propio con `prefix="/auth"` y las cinco rutas (`registro`, `login`, `logout`, `yo`, `cambiar-password`). Es un objeto separado del router de `/usuarios` porque `C-08` monta `/auth` y `/usuarios` en grupos distintos (DD-05).
- **`main.py`**: el lifespan calcula **una vez** el hash ficticio (con `hash_password` sobre una contraseña aleatoria y el costo de `Settings`) y lo guarda en `app.state.hash_ficticio`; se monta `auth_router` en el grupo abierto.
- **Evidencia**: `test/auth.http` con la respuesta esperada en cada bloque y `test/test_auth.py` como réplica automatizada (18 tests), usando los fixtures `client`/`login` de `C-05`.

## Capabilities

### New Capabilities
- `auth-registration`: auto-registro de cliente con usuario + rol CLIENTE + ficha en un solo Unit of Work, conflicto de documento/email sin apropiarse de una ficha existente y contraseña acotada por bytes.
- `auth-login`: orden del login (límite de intentos antes del hash), 429 con `Retry-After`, respuesta uniforme con hash ficticio, intento en sesión propia y JWT sólo en cookie HttpOnly.
- `auth-session`: lectura de la sesión desde la cookie, `GET /auth/yo`, logout y rechazo de tokens anteriores al último cambio de contraseña.
- `password-change`: cambio de contraseña con verificación de la actual, regla de longitud de la nueva, `password_cambiada_en` con hora completa y emisión del token nuevo después del cambio.

### Modified Capabilities
- Ninguna. `request-contracts` y `error-handling` (de `C-06`) se reutilizan sin cambios; `security-primitives` (de `C-02`) ya emitía `iat` sin truncar y no se toca.

## Impact

- **Código**: `main.py`, `app/core/dependencies.py`, `app/modules/usuarios/{schemas,repository,unit_of_work,service}.py`, `app/modules/usuarios/auth_router.py` (nuevo), `app/modules/clientes/repository.py` (nuevo).
- **Base de datos**: **sin migraciones**. Se usan columnas y tablas ya existentes (`usuario.password_cambiada_en`, `usuario.debe_cambiar_password`, `asignacion_rol`, `intento_acceso`, `evento_seguridad`, `cliente`). No hay columnas nuevas.
- **Dependencias**: ninguna nueva (bcrypt y PyJWT ya estaban en el stack de `C-02`).
- **Habilitado**: `C-08 authorization-rbac` (usa `get_usuario_actual`, agrega `requiere_rol`, el 403 del cambio obligatorio y los dos grupos de rutas), y a través suyo los módulos de dominio.
