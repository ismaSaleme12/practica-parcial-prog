# Tasks

> Orden TDD: primero la evidencia (`test/rbac.http` + `test/test_rbac.py` + la adaptación de `test/test_contracts.py`), después la implementación mínima que la hace pasar. La suite nueva falló primero (18 fallos + 16 errores de fixture) antes de tocar la autorización.

## 1. Contratos de la Épica 5

- [x] 1.1 Agregar `RolNombre` (los cuatro roles del CHECK), `RolAsignar`, `RolLeer` (con `de_asignacion` y `vigente` calculado) y `EventoLeer` a `app/modules/usuarios/schemas.py`. Verificación: `rol: "SUPER"` → 422; `RolLeer` no expone `usuario_id` ni `otorgada_por`.
- [x] 1.2 Validar `desde`/`vence_en` con zona horaria obligatoria y `vence_en` en el futuro; las dos fallas → 422 con mensaje propio. Verificación: `2026-12-31T23:59:59` → 422 («zona horaria»); `2020-01-01T00:00:00+00:00` → 422 («futura»).

## 2. Repositorios

- [x] 2.1 `AsignacionRolRepository.listar_por_usuario`: todas las filas del usuario, incluidas revocadas y vencidas, ordenadas por `id` (historial completo). Verificación: tras asignar y revocar MECANICO, el listado trae las dos filas.
- [x] 2.2 `AsignacionRolRepository.get_abierta(usuario_id, rol)`: fila con `revocada_en IS NULL`, aunque esté vencida. Verificación: es la que permite cerrar la vencida antes de reabrir.
- [x] 2.3 `AsignacionRolRepository.contar_vigentes(rol, ahora)`: cuenta filas no revocadas y sin vencer (misma definición que `roles_vigentes`). Verificación: con dos ADMINs vigentes devuelve 2; tras revocar uno, 1.

## 3. Dependencias de autorización

- [x] 3.1 `requiere_rol(*roles)`: factory que consulta `asignacion_rol` **en cada petición** y responde 403 con `MENSAJE_SIN_PERMISO` si no hay intersección. Los roles del token **no** se usan. Verificación: token con `roles: ["ADMIN"]` y `sub` de la recepción → 403 en `/eventos`.
- [x] 3.2 `exigir_password_al_dia`: 403 con `MENSAJE_CAMBIO_PENDIENTE` mientras `debe_cambiar_password` esté activo. Depende de `get_usuario_actual`, así que sin cookie el resultado es 401, no 403. Verificación: `nuevo@example.com` en `/repuestos` → 403; sin cookie → 401.
- [x] 3.3 Alias `AdminDep = Depends(requiere_rol("ADMIN"))` y `PersonalDep = Depends(requiere_rol("ADMIN", "RECEPCION", "MECANICO"))`. Verificación: `GET /repuestos` con CLIENTE → 403; con RECEPCION/MECANICO/ADMIN → 200.

## 4. Servicios de personal, roles y auditoría

- [x] 4.1 `actor_de(usuario)` → `email[:120]`, y `crear(..., actor=...)` que da de alta con `debe_cambiar_password=True` y escribe el evento **en el mismo UoW**. Verificación: 201 con `debe_cambiar_password: true`, sin `password_hash`; queda `("admin@example.com", "Alta de usuario id N")`.
- [x] 4.2 `listar_roles`: 404 si el usuario no existe; historial completo si existe. Verificación: `/usuarios/999999/roles` → 404; `/usuarios/4/roles` → una fila MECANICO `vigente: true`.
- [x] 4.3 `asignar_rol`: 404 si el usuario no existe; cierra la abierta vencida; inserta sin comprobar unicidad previa (el índice parcial da 409); escribe el evento en el mismo UoW. Verificación: repetida sobre un rol vigente → 409; rol vencido → dos filas, la primera con `revocada_en`; 201 y evento.
- [x] 4.4 `revocar_rol`: 404 si no hay fila abierta; RN-05 → 409 por autoprotección (propio ADMIN) y por último ADMIN vigente; escribe `revocada_en` sin borrar; registra el evento. Verificación: `/usuarios/1/roles/ADMIN` con el propio admin → 409 y la fila sigue abierta; revocar el de otro admin con dos vigentes → 200 y su sesión pasa a 403.
- [x] 4.5 `listar_eventos` paginado y evento de `cambiar_password` dentro del mismo UoW. Verificación: `GET /eventos?size=1` trae el envoltorio completo; el cambio de `nuevo@example.com` deja `("nuevo@example.com", "Cambio de contraseña")`.

## 5. Routers y grupos de rutas

- [x] 5.1 Reescribir `app/modules/usuarios/router.py`: `POST /usuarios`, `GET/POST /usuarios/{id}/roles`, `DELETE /usuarios/{id}/roles/{rol}` (todas ADMIN) y `eventos_router` separado con `GET /eventos` (ADMIN, paginado). Verificación: sin cookie → 401 en las cinco; con MECANICO → 403; con ADMIN → el código esperado.
- [x] 5.2 Aplicar la matriz de `03_actores_y_roles.md` a `app/modules/repuestos/router.py`: GET con `PersonalDep`, POST con `AdminDep`. Verificación: la matriz del test (RECEPCION/MECANICO 200 en GET y 403 en POST; ADMIN 201 en POST).
- [x] 5.3 `main.py`: `grupo_abierto` (`health` + `auth`) y `grupo_protegido` (`usuarios`, `eventos`, `repuestos`) con `dependencies=[Depends(exigir_password_al_dia)]` **una sola vez** (DD-05). Verificación: `/auth/yo` responde 200 con clave provisoria y `/repuestos` responde 403 con la misma cookie.

## 6. Evidencia y verificación

- [x] 6.1 Adaptar `test/test_contracts.py` con el fixture `admin` (login como ADMIN) en los 16 tests que pegan a rutas ahora protegidas. **No se elimina ni se debilita ningún caso**; decisión documentada en `design.md` D8. Verificación: los 16 pasan con el mismo cuerpo y las mismas aserciones.
- [x] 6.2 Escribir `test/rbac.http` con la respuesta esperada comentada: 401 vs 403, matriz de repuestos, claim `roles` que no autoriza, revocación inmediata (C-07), historial, 409 por índice, `vence_en` 422 (sin zona y pasado), reasignación de vencido, autoprotección (C-08), cambio obligatorio 403 vs `/auth`, alta con clave provisoria, eventos y `GET /eventos` paginado.
- [x] 6.3 Escribir `test/test_rbac.py` (18 tests) como réplica automatizada, usando `client`, `login` y `motor` de `C-05`. Cubre 401 vs 403, efecto inmediato de la revocación (C-07), autoprotección → 409 (C-08), `vence_en` → 422, reasignación de vencido, `/eventos` paginado y sólo ADMIN, y `debe_cambiar_password` 403 vs `/auth` accesible.
- [x] 6.4 Correr `python -m pytest test/ -q` desde la raíz: **63 passed** (45 de `C-05`/`C-06`/`C-07` + 18 de `C-08`).
- [x] 6.5 `openspec validate 2026-10-27-c-08-authorization-rbac --strict` en verde.

## Workflow follow-up

- **Pendiente explícito de `C-09`/`C-10`**: el ABM de `clientes`/`vehiculos` y el de `repuestos` (PATCH, baja lógica, reposición e historiales) usan `AdminDep`/`PersonalDep` y el grupo protegido ya montados acá; `C-11` necesitará una ruta protegida **sin** `requiere_rol` para cancelar por el dueño (DD-06), por eso el rol no se monta en el grupo.
- Revisar los artefactos y archivar con `/opsx:archive c-08-authorization-rbac` cuando el orquestador lo pida (no archivar desde este change).
- No commitear: el orquestador lo hace.
