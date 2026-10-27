# Proposal

## Why

`C-07` dejó la autenticación: hay identidad (`get_usuario_actual`), cookie `access_token` y `/auth/yo`. Pero la API todavía **no autoriza**: agregar `requiere_rol` a mano en cada endpoint, leer los roles del token o confiar en que el cliente manda el rol correcto dejaría las decisiones de permiso dispersas y, peor, **desactualizadas** respecto de la base.

La consigna (Ejercicio 5) pide tres cosas que sólo se sostienen juntas:

1. **RBAC decidido en la base en cada petición** (RN-04). Revocar un rol tiene que quitarle el permiso a una sesión ya abierta **sin esperar** a que el JWT venza (caso C-07). Un token con roles «congelados» no puede cumplirlo.
2. **El cambio obligatorio de contraseña** (RN-06) tiene que bloquear el grupo protegido con 403 **sin** bloquear `/auth` (US-015 CA-1): si el afectado no puede loguearse ni cambiar la clave, queda encerrado. Eso exige **dos grupos de rutas** con el control montado **una sola vez** (DD-05).
3. **Administración de personal y roles** (US-014, US-016) con vigencia, autoprotección del último ADMIN (RN-05) y auditoría en `evento_seguridad`. Un ADMIN no puede revocarse su propio ADMIN ni dejar el sistema con 0 administradores vigentes.

Sin este change, `POST /usuarios` y `POST /repuestos` seguirían públicos (heredado de `C-06`), cualquier sesión podría crear personal, y revocar un rol no tendría efecto real hasta que venciera el token.

## What Changes

- **`app/core/dependencies.py`**: `requiere_rol(*roles)` como **factory de dependencia** que responde 403 y consulta `asignacion_rol` **en cada petición** (vigente = `revocada_en IS NULL` y `vence_en` nulo o futuro). `exigir_password_al_dia` responde 403 mientras `debe_cambiar_password` siga activo. Alias `AdminDep` y `PersonalDep`.
- **`main.py`**: **dos grupos de rutas** (DD-05). El **abierto** monta `health` y `auth`; el **protegido** monta `usuarios`, `eventos` y `repuestos` con `Depends(exigir_password_al_dia)` **una sola vez**. Los routers conservan su prefix y sus tags.
- **`app/modules/usuarios/schemas.py`**: `RolNombre` (los cuatro roles del CHECK), `RolAsignar` (`desde`/`vence_en` con zona horaria obligatoria y `vence_en` futuro → 422), `RolLeer` (con `vigente` calculado) y `EventoLeer`.
- **`app/modules/usuarios/repository.py`**: `AsignacionRolRepository.listar_por_usuario` (historial completo), `get_abierta` (fila con `revocada_en IS NULL`) y `contar_vigentes` (autoprotección).
- **`app/modules/usuarios/service.py`**: `actor_de`, `crear` (alta ADMIN con clave provisoria + evento en el mismo UoW), `listar_roles`, `asignar_rol` (repetida → 409 por el índice; vencida → cerrar y reabrir), `revocar_rol` (escribe `revocada_en`, no borra; RN-05 → 409), `listar_eventos` y el evento del cambio de contraseña.
- **`app/modules/usuarios/router.py`**: las rutas de `/usuarios` y un `eventos_router` separado para `/eventos` (no comparte el prefix). Todas exigen ADMIN.
- **`app/modules/repuestos/router.py`**: la matriz de la KB aplicada con dependencias — GET para ADMIN/RECEPCION/MECANICO, POST sólo ADMIN.
- **`test/test_contracts.py`**: los 16 tests de `C-06` se adaptan a `(client, admin)` porque sus endpoints dejaron de ser públicos. **No se elimina cobertura**: los mismos casos (422 de contrato, 409 de integridad, búsqueda parametrizada, página fuera de rango) siguen verificándose, ahora con una sesión ADMIN.
- **Evidencia**: `test/rbac.http` con la respuesta esperada en cada bloque y `test/test_rbac.py` como réplica automatizada (18 tests), usando los fixtures `client`/`login`/`motor` de `C-05`.

## Capabilities

### New Capabilities

- `route-groups`: dos grupos de rutas con el 401 de la sesión y el 403 del cambio obligatorio montado una sola vez en el protegido, dejando `/auth` y `/health` abiertos.
- `role-requirement`: autorización por rol consultada en `asignacion_rol` en cada petición, con efecto inmediato de la revocación y sin confiar en los roles del token.
- `role-management`: alta de personal, historial de roles, asignación con vigencia validada, revocación sin borrar filas y autoprotección del último ADMIN.
- `security-events`: registro de altas, cambios de rol y cambios de contraseña en `evento_seguridad`, y su consulta paginada sólo para ADMIN.

### Modified Capabilities

- Ninguna. `request-contracts` y `error-handling` (de `C-06`) se reutilizan: el 409 por índice parcial y el 422 de contrato ya están resueltos por el handler central. `auth-session` (de `C-07`) no cambia: `get_usuario_actual` se reutiliza tal cual.

## Impact

- **Código**: `main.py`, `app/core/dependencies.py`, `app/modules/usuarios/{schemas,repository,service,router}.py`, `app/modules/repuestos/router.py`, `test/test_contracts.py`.
- **Base de datos**: **sin migraciones**. Se usan `asignacion_rol` (con su índice único parcial `(usuario_id, rol) WHERE revocada_en IS NULL`) y `evento_seguridad`, creados en `C-04`.
- **Dependencias**: ninguna nueva. No se agrega Redis, caché de permisos ni middleware de autorización.
- **Rutas**: `POST /usuarios` y `POST /repuestos` dejan de ser públicos; `GET /eventos`, `GET/POST /usuarios/{id}/roles` y `DELETE /usuarios/{id}/roles/{rol}` son nuevas y sólo ADMIN.
- **Habilitado**: `C-09 clientes-vehiculos` y `C-10 repuestos-stock`, que usan `AdminDep`/`PersonalDep` y el grupo protegido.
- **Límite conocido**: la comprobación de «último ADMIN» cuenta filas vigentes sin bloquear concurrencia; dos revocaciones simultáneas de los dos últimos ADMINs podrían dejar 0. Se documenta en `design.md`; el índice parcial sí garantiza la unicidad entre vigentes.
