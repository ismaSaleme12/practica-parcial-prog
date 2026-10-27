# Design

Ver `proposal.md` (Why) y las specs `route-groups`, `role-requirement`, `role-management` y `security-events` (requisitos). Este documento explica **cómo** se cumple ese contrato.

## Context

Al empezar este change, `C-07` dejó la identidad resuelta: `get_usuario_actual` lee la cookie `access_token`, valida `iat` contra `password_cambiada_en` sin truncar y devuelve un `UsuarioActual` con el `Usuario` y los `claims` (entre ellos `roles`, **informativos**). `auth_router` ya existe como objeto separado de `usuarios_router` justamente para que este change pueda montarlos en grupos distintos. Pero no hay autorización: `requiere_rol` no existe, nada bloquea `debe_cambiar_password`, y `usuarios_router` y `repuestos_router` siguen montados en abierto (herencia de `C-06`), así que **cualquiera** puede crear personal o repuestos.

Restricciones que condicionan el diseño:

- **Stack cerrado**: FastAPI + SQLModel + SQLAlchemy async + PostgreSQL. Sin Redis, sin caché de permisos, sin middleware de autorización, sin dependencias nuevas.
- **Sin migración**: `asignacion_rol` ya tiene el índice único parcial `(usuario_id, rol) WHERE revocada_en IS NULL` y `evento_seguridad` existe con `actor` de 120 caracteres. Si hiciera falta una columna nueva, el change se detendría y lo reportaría.
- **Reglas duras de `AGENTS.md`**: el rol se consulta en la base **en cada petición**; el 409 se produce por el índice y **no** por una consulta previa de unicidad; `select` de SQLModel; `flush()` en repositorios y `commit()` sólo en el UoW; ninguna respuesta expone `password_hash`.
- **DD-05 / §5.10**: FastAPI **suma** dependencias y no las resta. El 403 del cambio obligatorio tiene que montarse **una sola vez**, en el grupo, y no puede «sustraerse» por ruta.

## Goals / Non-Goals

**Goals:**

- 401 cuando no hay sesión y 403 cuando la hay pero falta el permiso: dos respuestas distintas y con mensajes propios (US-013).
- `requiere_rol` decide con `asignacion_rol` en cada petición; revocar un rol afecta a la sesión abierta en la petición siguiente (RN-04, caso C-07).
- Dos grupos de rutas con el control de `debe_cambiar_password` montado **una sola vez** en el protegido (DD-05, US-015 CA-1).
- Alta de personal con clave provisoria, historial de roles, asignación con vigencia validada y revocación que escribe `revocada_en` sin borrar (US-014).
- Autoprotección: un ADMIN no se revoca su propio ADMIN y el sistema no queda con 0 ADMINs vigentes (RN-05, caso C-08).
- Auditoría en `evento_seguridad` de altas, cambios de rol y cambios de contraseña, y `GET /eventos` paginado sólo para ADMIN (US-016).

**Non-Goals:**

- Módulos de dominio (`clientes`, `repuestos` completo, `ordenes`) → `C-09` a `C-12`. Acá sólo se protegen las rutas que ya existían.
- `POST /ordenes/{id}/cancelar` sin `requiere_rol` (el servicio decide identidad) → `C-11`, DD-06.
- Caché o invalidación de permisos: la decisión es una consulta por petición; es el precio de que la revocación sea inmediata.
- Recuperación de contraseña, bloqueo de cuentas por inactividad o refresh tokens: fuera del alcance del TP.

## Decisions

### D1 — Dos grupos de rutas y el 403 montado una sola vez (DD-05 / §5.10)

**Decisión**: `main.py` crea

```python
grupo_abierto = APIRouter()
grupo_protegido = APIRouter(dependencies=[Depends(exigir_password_al_dia)])
```

El abierto incluye `health_router` y `auth_router`; el protegido incluye `usuarios_router`, `eventos_router` y `repuestos_router`. `exigir_password_al_dia` **no** se repite en ninguna ruta ni en ningún router.

**Por qué**: es la lectura literal de DD-05 y de la sección 5.10 de `07_flujos_principales.md`: «FastAPI suma dependencias y no las resta (sección 5.10); montar el control una vez en el grupo evita olvidos y garantiza que toda ruta nueva del grupo protegido quede protegida por defecto». Montarlo por router no alcanzaría para el «no se puede restar», y montarlo por ruta haría que una ruta nueva quede desprotegida por olvido. Con el grupo, el default es seguro.

**Orden de las respuestas**: la dependencia del grupo corre antes que las de la ruta. `exigir_password_al_dia` depende de `get_usuario_actual`, así que sin cookie se lanza **401 antes** de evaluar `debe_cambiar_password`; y el 403 del cambio pendiente se lanza **antes** de `requiere_rol`. El orden esperado es 401 (identidad) → 403 (cambio pendiente) → 403 (rol) → handler.

**Consecuencia**: `POST /usuarios` y `POST /repuestos`, que en `C-06` eran públicos, ahora responden 401 sin cookie. Eso obligó a adaptar los tests de contrato (D8).

**Alternativa descartada**: una dependencia por endpoint. Falla por omisión: cualquier ruta nueva sin la dependencia quedaría accesible con clave provisoria, y el requisito es justamente que no dependa de la memoria del programador.

### D2 — `requiere_rol` es una factory que consulta la base en cada petición (RN-04)

**Decisión**: `requiere_rol(*roles)` devuelve una función `_verificar_rol(actual, session)` que consulta `AsignacionRolRepository(session).roles_vigentes(actual.usuario.id)` y compara con un `frozenset` de los roles aceptados. Si la intersección es vacía → 403 con `MENSAJE_SIN_PERMISO`. Se usa como valor por defecto (`actual: UsuarioActual = AdminDep`), **no** como `dependencies=[...]` del grupo.

**Por qué**: RN-04 y el caso C-07 exigen que la revocación tenga efecto inmediato. Un claim `roles` en el JWT es una foto del momento del login: revocar un rol no lo cambiaría hasta que el token venza. Consultar la tabla cuesta una consulta indexada por `usuario_id` y es la única forma de que «revocar» signifique algo.

**Por qué factory y no dependencia fija con un parámetro**: los roles aceptados son distintos por ruta (`ADMIN` vs `ADMIN, RECEPCION, MECANICO`) y el contrato de FastAPI no permite pasar argumentos a una dependencia sin `Query`/`Path`. La factory cierra sobre el conjunto y devuelve la dependencia ya configurada. Los alias `AdminDep` y `PersonalDep` evitan repetir el literal en cada ruta.

**Por qué no como dependencia del grupo**: el grupo ya exige sesión y cambio al día, pero el rol es una **decisión por ruta**. Además, `C-11` necesitará rutas del grupo protegido sin `requiere_rol` (cancelar por el dueño, DD-06); si el rol estuviera en el grupo, no se podría quitar.

**Un solo `get_usuario_actual` y una sola sesión**: FastAPI cachea las dependencias por petición (`use_cache=True` por defecto), así que `exigir_password_al_dia` y `requiere_rol` comparten la misma resolución de usuario y la misma sesión de `get_session`. No hay dos lecturas de `usuario` ni dos transacciones.

### D3 — Vigencia de un rol: una sola definición, la misma en tres lugares

**Decisión**: «vigente» = `revocada_en IS NULL` **y** (`vence_en IS NULL` **o** `vence_en > ahora`). Se implementa en `roles_vigentes` (para `requiere_rol` y `/auth/yo`), en `contar_vigentes` (autoprotección) y en `RolLeer.vigente` (contrato de salida). `listar_por_usuario` devuelve **todas** las filas, incluidas revocadas y vencidas.

**Por qué**: si la definición viviera en un solo lugar y el contrato usara otra (por ejemplo, sólo `revocada_en IS NULL`), una fila vencida aparecería como `vigente: true` cuando la autorización ya la ignora. El test de roles verifica el historial y el `vigente` del contrato; el caso C-07 verifica el efecto en la autorización. Las tres vistas tienen que coincidir.

**Consecuencia**: `GET /usuarios/{id}/roles` devuelve el historial completo, no sólo los roles actuales. Es lo que pide US-014: revocar no borra y el historial de quién tuvo qué y hasta cuándo se conserva.

### D4 — Asignación repetida: 409 por el índice parcial, sin consulta previa (RN-03)

**Decisión**: `asignar_rol` busca la fila **abierta** (`revocada_en IS NULL`) de `(usuario_id, rol)`. Si existe **y está vencida**, le escribe `revocada_en = ahora` para liberar el índice. Después inserta la fila nueva **sin** comprobar si ya había una vigente: si la había, el `INSERT` choca con el índice único parcial y el handler central traduce el `IntegrityError` a 409.

**Por qué**: la regla dura prohíbe verificar unicidad con una consulta previa; además sería una carrera (dos asignaciones simultáneas podrían pasar el `SELECT` y chocar en el `INSERT`). El índice parcial es la garantía real, y el 409 sale con el mismo mensaje propio de `C-06` (RN-18), sin texto del motor ni nombre del índice.

**Por qué cerrar la vencida en lugar de ignorarla**: el índice parcial sólo filtra por `revocada_en IS NULL`; **no** mira `vence_en`. Una fila vencida sigue ocupando el lugar de `(usuario_id, rol)` y bloquearía la reasignación. Escribir `revocada_en` la cierra (el historial conserva `vence_en`) y libera el índice. El orden importa: cerrar y luego insertar, en el mismo UoW.

**Alternativa descartada**: cambiar el índice para que también filtre `vence_en > now()`. Los índices parciales no admiten `now()` (no es inmutable) y cambiar el esquema está fuera del alcance de `C-08`.

### D5 — Revocar escribe `revocada_en`; nunca borra (RN-03)

**Decisión**: `revocar_rol` busca la fila abierta; si no existe → 404 con mensaje propio. Escribe `revocada_en = ahora`, actualiza y registra el evento. El `DELETE` HTTP **no** borra la fila.

**Por qué**: US-014 CA-1 y el Flujo 6: «Escribe `revocada_en` en la fila; no borra (el historial queda)». Borrar destruiría la auditoría de quién tuvo un rol y hasta cuándo, que es justamente lo que `GET /usuarios/{id}/roles` muestra.

**Consecuencia**: una segunda revocación del mismo rol devuelve 404 (ya no hay fila abierta). Es correcto: la operación pide revocar **algo abierto**, y no hay nada abierto que revocar. La fila revocada sigue visible en el historial.

### D6 — Autoprotección en el servicio, antes de escribir (RN-05)

**Decisión**: dentro de `revocar_rol`, cuando `rol == "ADMIN"`:

1. Si `usuario_id == admin.id` → 409 `MENSAJE_AUTOPROTECCION`.
2. Si `contar_vigentes("ADMIN", ahora) <= 1` → 409 `MENSAJE_ULTIMO_ADMIN`.

Las dos comprobaciones corren **antes** de escribir `revocada_en`.

**Por qué**: RN-05 y el Flujo 6. El orden importa: si se escribiera primero y se comprobara después, una revocación rechazada habría dejado la fila cerrada de todos modos. La comprobación del propio ADMIN va primero para dar el mensaje más específico cuando se cumplen las dos condiciones.

**Por qué en el servicio y no en la ruta**: la regla depende del rol que se revoca y de quién lo pide, no de la ruta; el servicio es el punto único que puede garantizarla. La ruta ya exige ADMIN, que es una condición distinta.

**Límite aceptado**: `contar_vigentes` no bloquea filas. Dos revocaciones simultáneas de los dos últimos ADMINs podrían leer «2» las dos y dejar 0. Se acepta porque exigiría un `SELECT ... FOR UPDATE` o un aislamiento mayor, desproporcionado para este TP; el índice parcial sí garantiza la unicidad, y el camino normal (un solo ADMIN revocándose) queda cubierto por la comprobación del propio ADMIN. Se documenta acá para que no parezca un olvido.

### D7 — `vence_en`/`desde`: zona horaria obligatoria; sólo `vence_en` exige futuro

**Decisión**: `RolAsignar` valida con `field_validator` que `desde` y `vence_en`, si vienen, tengan `tzinfo` y `utcoffset()`; y que `vence_en > datetime.now(timezone.utc)`. Las dos fallas son 422.

**Por qué**: el Flujo 6 dice «sin zona o en el pasado → **422**, no 409» y el Ejercicio 5 marca que una fecha sin zona es ambigua. Es un error de contrato, no de estado del recurso: por eso 422 y no 409. `desde` no exige futuro porque registrar el inicio en el pasado es legítimo (una asignación retroactiva); `vence_en` en el pasado no tiene sentido.

**Por qué los dos validadores y no uno**: `desde` y `vence_en` comparten la regla de zona, pero sólo `vence_en` la de futuro. Separarlos deja el mensaje de error específico («debe ser futura») en el campo correcto.

**Consecuencia**: `2026-12-31T23:59:59` (sin offset) → 422; `2020-01-01T00:00:00+00:00` → 422; ambos casos están en `test/test_rbac.py`.

### D8 — Story de contrato: los tests de `C-06` se adaptan, no se eliminan

**Decisión**: los 16 tests de `test/test_contracts.py` que pegaban a `POST /usuarios`, `POST /repuestos`, `GET /repuestos` y `GET /repuestos/{id}` pasan a recibir `(client, admin)`, con un fixture `admin` que hace login como `admin@example.com`. **Ningún caso se elimina ni se debilita**: los mismos cuerpos, los mismos códigos y las mismas aserciones.

**Por qué**: el contrato que verifican (422 por `extra="forbid"`, 409 por integridad, búsqueda parametrizada, página fuera de rango) sigue vigente; lo único que cambió es que la ruta ahora exige una sesión ADMIN. Borrar los tests habría perdido cobertura de `C-06` para «arreglar» una consecuencia de `C-08`. Adaptarlos conserva la intención original y, de paso, documenta el nuevo requisito de autorización.

**Fixture `admin`**: se agrega a `test/test_contracts.py` (no a `conftest.py`) porque es una necesidad local de ese archivo: hace login y deja la cookie en el cliente. El `login` de `C-05` ya existe; el fixture sólo lo envuelve.

**Tests que se vuelven obsoletos**: ninguno. Si en el futuro una ruta de `C-06` cambia de forma (por ejemplo `POST /repuestos` pasa a exigir `stock_inicial` en `C-10`), el test se adapta en ese change, no se elimina.

### D9 — Actor del evento: el correo, recortado a 120 (US-016)

**Decisión**: `service.actor_de(usuario)` devuelve `usuario.email[:120]` y se usa como `actor` de las altas, asignaciones y revocaciones; el cambio de contraseña usa el mismo helper. El seed conserva `'SISTEMA'`. Las acciones son textos fijos: `Alta de usuario id {id}`, `Asignación de rol {ROL} al usuario id {id}`, `Revocación de rol {ROL} al usuario id {id}` y `Cambio de contraseña`.

**Por qué**: `evento_seguridad.actor` es `VARCHAR(120)` y el contrato de email admite hasta 320. Recortar en el servicio evita que un correo larguísimo convierta una auditoría en un `DataError` (500) después de una operación que ya se hizo. El correo es legible y estable; el id solo no dice quién fue. Los textos fijos permiten buscar por acción y hacen la evidencia `.http` verificable.

**Consecuencia**: si dos usuarios comparten los primeros 120 caracteres del correo, el actor los confunde. Se acepta: el correo es único en la base y 120 caracteres son más que cualquier correo real; la alternativa (id numérico) perdería legibilidad y la de guardar el correo completo exigiría migración.

**Mismo UoW**: el alta, la asignación, la revocación y el cambio de contraseña escriben el evento **dentro** del `async with uow` de la operación. Si la operación falla, el evento no queda; si queda, la operación se confirmó.

## Risks / Trade-offs

- **Una consulta de roles por petición** → es el costo de RN-04 y del efecto inmediato de la revocación. La consulta es por `usuario_id` (FK indexada) y devuelve sólo la columna `rol`. Cachear reintroduciría la ventana en la que un rol revocado sigue autorizando.
- **`contar_vigentes` no bloquea concurrencia** → dos revocaciones simultáneas podrían dejar 0 ADMINs. Aceptado y documentado en D6; la comprobación del propio ADMIN cubre el caso normal.
- **Fila vencida cerrada con `revocada_en`** → el historial muestra `revocada_en` aunque nadie la revocó explícitamente. Es la única forma de liberar el índice parcial sin cambiar el esquema; `vence_en` sigue en la fila y cuenta la verdad.
- **`POST /usuarios` y `POST /repuestos` dejan de ser públicos** → los tests de `C-06` y cualquier cliente `.http` viejo necesitan sesión ADMIN. Se adaptó la suite; la evidencia de `C-06` (`test/contracts.http`) se mantiene como evidencia histórica del contrato, no como guion ejecutable sin login.
- **`GET /usuarios/{id}/roles` devuelve todo el historial** → una cuenta con muchos cambios de rol devuelve una lista larga. No se pagina porque el volumen por usuario es bajo y US-014 pide el historial completo.
- **El rol CLIENTE no se administra desde estas rutas** → `POST /usuarios` crea personal (sin rol) y la asignación de roles es explícita. Un ADMIN podría asignar CLIENTE a un usuario de personal; no se bloquea porque la matriz no lo prohíbe y es reversible.
- **`requiere_rol` no valida que el rol exista en el CHECK** → los alias usan literales del esquema. Un typo daría 403 siempre, no 500; el test de la matriz lo detectaría.

## Migration Plan

1. Extender `app/core/dependencies.py` con `requiere_rol`, `exigir_password_al_dia`, `AdminDep` y `PersonalDep`.
2. Agregar `RolNombre`, `RolAsignar`, `RolLeer` y `EventoLeer` a `app/modules/usuarios/schemas.py`.
3. Agregar `listar_por_usuario`, `get_abierta` y `contar_vigentes` a `app/modules/usuarios/repository.py`.
4. Implementar `actor_de`, el evento del alta y del cambio de contraseña, y los servicios de roles y eventos en `app/modules/usuarios/service.py`.
5. Reescribir `app/modules/usuarios/router.py` con las rutas de `/usuarios` y el `eventos_router` de `/eventos`.
6. Aplicar la matriz a `app/modules/repuestos/router.py` con `AdminDep`/`PersonalDep`.
7. Reorganizar `main.py` en los dos grupos.
8. Adaptar `test/test_contracts.py` al fixture `admin`; escribir `test/rbac.http` y `test/test_rbac.py`.
9. Correr `python -m pytest test/ -q` y `openspec validate 2026-10-27-c-08-authorization-rbac --strict`.

**Rollback**: no hay migraciones. Revertir `main.py` al montaje plano de `C-07`, quitar `requiere_rol`/`exigir_password_al_dia` de `dependencies.py` y las rutas nuevas de `usuarios/router.py`, y la API vuelve al estado de `C-07` (con `POST /usuarios` y `POST /repuestos` públicos). La base no se modifica: `asignacion_rol` y `evento_seguridad` ya existían.

## UI Mockups

Decision: no (no UI). Es una API sin frontend; no aplica el gate de mockups.
