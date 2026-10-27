# Design

Ver `proposal.md` (Why) y las specs `auth-registration`, `auth-login`, `auth-session` y `password-change` (requisitos). Este documento explica **cómo** se cumple ese contrato.

## Context

Al empezar este change, `C-06` dejó contratos (`extra="forbid"`, dinero como string Decimal, contraseñas ≤ 72 bytes) y el manejo central de errores (`IntegrityError` → 409, `RequestValidationError` → 422, `Conflicto`/`RecursoNoEncontrado`), pero no hay autenticación: `get_usuario_actual` no existe, `POST /usuarios` y `POST /repuestos` están montados en abierto y `security.py` sólo aporta primitivas.

Restricciones que condicionan el diseño:

- **Stack cerrado**: FastAPI + SQLModel + SQLAlchemy async + PostgreSQL. No se agregan dependencias; bcrypt y PyJWT ya estaban desde `C-02`.
- **Sin migración**: `intento_acceso`, `usuario.password_cambiada_en` y `usuario.debe_cambiar_password` ya existen en el esquema de `C-04`. Si hiciera falta una columna nueva, este change se detendría y lo reportaría.
- **Reglas duras de `AGENTS.md`**: `iat` sin truncar; límite de intentos **antes** del hash; `intento_acceso` en sesión propia siempre confirmada; token **sólo** en cookie HttpOnly; hash antes de abrir la transacción; `flush()` en repositorios y `commit()` sólo en el UoW; `select` de SQLModel; `app/models.py` registrado antes de consultar.
- **`C-08` todavía no existe**: no se implementan `requiere_rol`, ni el 403 de `debe_cambiar_password`, ni los dos grupos de rutas definitivos. El router de `/auth` ya está separado para que `C-08` pueda montarlo en el grupo abierto (DD-05).

## Goals / Non-Goals

**Goals:**

- Auto-registro atómico: usuario + rol CLIENTE + ficha de cliente, o ninguna de las tres filas (RN-02).
- Login que evalúe el límite de intentos **primero** y que no calcule ningún hash cuando responde 429 (RN-08).
- Login que responda y tarde parecido exista o no el correo (RN-09), usando el hash ficticio del lifespan.
- JWT en cookie `access_token` HttpOnly, SameSite=Lax, `Max-Age` = duración y `Secure` configurable; `Authorization: Bearer` no autentica (caso C-03).
- `/auth/yo` con el usuario, los roles vigentes consultados en la base y los roles informativos del token.
- Cambio de contraseña que invalide las sesiones anteriores sin esperar, comparando `iat` con `password_cambiada_en` **sin truncar** (RN-07 / DD-04).
- Que ninguna respuesta incluya `password_hash` y que ninguna entrada inválida termine en 500.

**Non-Goals:**

- `requiere_rol`, 403 del cambio obligatorio y los dos grupos de rutas definitivos → **`C-08`** (US-013/US-015, DD-05).
- Administración de personal y roles (`POST /usuarios/{id}/roles`, etc.) → `C-08`.
- Evento de seguridad de altas administrativas y cambios de rol → `C-08`; este change sólo registra el evento del auto-registro que pide el Flujo 2.
- Recuperación de contraseña, refresh tokens o revocación por lista negra: fuera del alcance del TP.

## Decisions

### D1 — El login evalúa el límite de intentos **antes** de cualquier hash (RN-08)

**Decisión**: `service.autenticar` abre el UoW de lectura, consulta el último login correcto de `(email, ip)` y cuenta los fallos de los últimos 60 s posteriores a ese éxito. Si hay **5 o más**, lanza 429 con `Retry-After` **dentro** del bloque y sin llamar a bcrypt. Recién si pasa el límite busca el usuario, sus roles y verifica la contraseña.

**Por qué**: US-010 CA-1/CA-2 y la regla dura «NUNCA calcular el hash del login si el límite de intentos ya se alcanzó». Invertir el orden permitiría que un atacante consumiera ~300 ms de bcrypt por petición aunque estuviera bloqueado: el límite dejaría de proteger el recurso que debía proteger. El costo del 429 es una sola consulta indexada por `(email, ip, cuando)`.

**`Retry-After`**: se calcula con el fallo más antiguo que todavía cuenta: `ceil((más_antiguo + 60 s − ahora).total_seconds())`, con mínimo 1. Así el valor es una espera real y no un número fijo arbitrario.

**Consecuencia aceptada**: una petición bloqueada con 429 **no** se anota en `intento_acceso`, porque no se verificó ninguna credencial y no debe extender la ventana de bloqueo de forma indefinida mientras el atacante sigue golpeando. Se documenta acá para que la decisión no parezca un olvido.

### D2 — Hash ficticio calculado una vez en el lifespan y recibido por parámetro (RN-09)

**Decisión**: `main.py`, dentro del lifespan, ejecuta `await hash_password(secrets.token_urlsafe(32))` y guarda el resultado en `app.state.hash_ficticio`. El router de login lo pasa al servicio como argumento; el servicio no lo importa ni lo recalcula.

**Por qué**: el hash ficticio es caro (~300 ms con el costo de producción) y debe existir antes de la primera petición. Calcularlo en el módulo de servicio lo haría depender de un estado global y de un bucle de eventos; hacerlo por petición duplicaría el costo y volvería a abrir una diferencia de tiempo. Con la contraseña aleatoria, nadie puede autenticarse contra el hash ficticio aunque lo conozca (sólo se usa como blanco de verificación cuando el correo no existe).

**Alternativas descartadas**: comparar contra un hash de una constante conocida (permitiría una cuenta fantasma si alguien adivina la constante); responder 401 sin verificar (rompe la uniformidad de duración de RN-09).

### D3 — Cada intento se anota en su propia sesión y transacción, siempre confirmadas (DD-09)

**Decisión**: `_anotar_intento` abre una sesión desde `app.state.session_maker`, la envuelve en un `UnitOfWork` propio y confirma. Es la **única** escritura del servicio que no comparte la transacción de la petición. El comentario del código lo declara junto con su costo (deja filas aunque la petición falle).

**Por qué**: el fallo que se quiere contar es el mismo que revierte el login fallido. Si el intento se anotara en la transacción de la petición, el rollback del 401 lo borraría y el límite nunca se activaría. La sesión de la petición no se reutiliza porque su transacción puede quedar abortada; una sesión nueva garantiza el commit del intento.

**Excepción consciente a «ningún servicio construye su UoW»**: la regla protege al UoW de la **petición**, que sigue llegando armado por el router. El UoW del intento es de una sesión distinta que el router no puede construir (todavía no existe); DD-09 exige que el servicio la abra. Se documenta para que la excepción sea explícita y no un atajo.

### D4 — El token viaja sólo en la cookie; el cuerpo del login no lo lleva (US-011)

**Decisión**: el router llama a `response.set_cookie("access_token", token, max_age=segundos, httponly=True, samesite="lax", secure=settings.COOKIE_SECURE, path="/")`. El cuerpo es `{mensaje, debe_cambiar_password, expira_en_segundos}`. `get_usuario_actual` lee **sólo** `request.cookies.get("access_token")`; nunca `Authorization`.

**Por qué**: US-011 CA-2 a CA-4 y caso C-03. `HttpOnly` saca el token del alcance de JavaScript, `SameSite=Lax` acompaña la navegación normal sin exponerlo en peticiones cruzadas, y `Secure` queda configurable para desarrollo (`false`) y producción (`true`). Aceptar también `Bearer` abriría una segunda vía que la consigna no pide y que complicaría la regla «sólo cookie».

**Consecuencia**: los clientes de la API (`.http`, httpx) deben conservar la cookie entre peticiones. La evidencia y la suite lo hacen así.

### D5 — `iat` sin truncar contra `password_cambiada_en` con hora completa (RN-07 / DD-04)

**Decisión**: `crear_token` ya emite `iat = datetime.now(timezone.utc).timestamp()` (con microsegundos) y la dependencia compara `float(iat) < password_cambiada_en.timestamp()` de forma estricta. El cambio de contraseña anota `password_cambiada_en` con `datetime.now(timezone.utc)` (timestamptz) y **emite el token después del commit**, no antes.

**Por qué**: si se truncara a segundos, una sesión iniciada en el mismo segundo que el cambio pero **antes** sería indistinguible de la nueva y seguiría valiendo. Emitir el token después de anotar el cambio garantiza que el `iat` del token nuevo sea mayor; los anteriores quedan estrictamente menores y la dependencia los rechaza con 401, aunque compartan el segundo.

**Borde**: `password_cambiada_en` nulo (usuario que nunca cambió la clave) no invalida ningún token. La comparación defensiva convierte una fecha naive en UTC, aunque el esquema garantiza `timestamptz`.

### D6 — El auto-registro usa un solo UoW y no consulta la unicidad antes de escribir (RN-02)

**Decisión**: `service.registrar` calcula el hash **antes** del `async with uow` y dentro agrega, en orden, `Usuario`, `AsignacionRol(rol="CLIENTE")`, `Cliente` y el `EventoSeguridad` del alta. No hay `SELECT` previo de email ni de documento: la unicidad la garantizan los UNIQUE de la base y el `IntegrityError` lo traduce el handler central a 409.

**Por qué**: RN-02 exige atomicidad y «no apropiarse» de una ficha existente. Con un solo UoW, un choque en `cliente.documento` revierte también el usuario y el rol: no queda ninguna fila suelta ni se escribe `usuario_id` sobre la ficha de Jorge. Una consulta previa de unicidad sería una carrera (dos registros simultáneos podrían pasar el `SELECT` y chocar en el `INSERT`) y la regla dura prohíbe verificar unicidad por consulta previa.

**Alternativa descartada**: buscar por documento y, si existe, adoptar la ficha. Es exactamente lo que RN-02 prohíbe: un desconocido podría quedarse con el historial de un cliente del taller.

### D7 — La contraseña nueva del cambio: **más de 8 bytes y hasta 72 bytes** (decisión explícita)

**Decisión**: `CambioPassword.password_nueva` sólo es válida si `8 < len(valor.encode("utf-8")) <= 72`. Con 8 bytes o menos → 422; con más de 72 → 422. Se mide en **bytes UTF-8**, no en caracteres.

**Por qué**: el enunciado es ambiguo en `CHANGES.md` («nueva ≤ 8 y ≤ 72 bytes según contrato»), pero el Flujo 4 de `07_flujos_principales.md` es explícito en la lista de errores:

> «Nueva ≤ 8 bytes o > 72 bytes u otra regla del contrato → 422»

La lectura literal es que **ambos extremos son inválidos**: el mínimo no es «al menos 8», sino «más de 8». Se elige la fuente de flujo (más específica) y se deja la cita acá para que la decisión sea auditable. Cuatro «ñ» son 4 caracteres y 8 bytes: también se rechazan, lo que demuestra que el límite es en bytes.

**Consecuencia**: 9 bytes se aceptan (hay un test), 8 se rechazan. Si el corrector esperara «≥ 8», el cambio es de una constante y de un test; la decisión queda registrada, no oculta en el código.

### D8 — `get_usuario_actual` mínimo, sin `requiere_rol` (pendiente de `C-08`)

**Decisión**: `app/core/dependencies.py` implementa `get_usuario_actual`, que devuelve un `UsuarioActual` con el `Usuario` y los `claims` del token. Valida cookie presente, firma/vencimiento (`verificar_token`), `sub` entero, usuario existente y activo, y `iat` contra `password_cambiada_en`. **No** implementa `requiere_rol` ni el 403 de `debe_cambiar_password`.

**Por qué**: `/auth/yo` y `/auth/cambiar-password` necesitan identificar al usuario, pero la autorización por rol y el cambio obligatorio son la Épica 5 (`C-08`). El `UsuarioActual` ya expone `claims["roles"]` para que `/auth/yo` muestre los roles del token sin confiar en ellos; `C-08` agregará `requiere_rol` consultando `asignacion_rol` en cada petición.

**Pendiente explícito de C-08**: `requiere_rol(...)`, el 403 de `debe_cambiar_password`, los dos grupos de rutas de `main.py` y el re-montaje de `auth`/`health` en el grupo abierto (DD-05). Este change no los adelanta.

### D9 — Dos objetos de router en el módulo `usuarios` (DD-05)

**Decisión**: `app/modules/usuarios/router.py` sigue siendo el de `POST /usuarios` (prototipo de `C-06`). Se agrega `app/modules/usuarios/auth_router.py` con `prefix="/auth"` y las cinco rutas de autenticación. `main.py` monta ambos.

**Por qué**: `C-08` necesita montar `/auth` (+ `health`) en el **grupo abierto** y `/usuarios` (+ `/repuestos`, etc.) en el **grupo protegido**, con el control del cambio obligatorio montado una sola vez en el protegido (DD-05 / US-015 CA-1). Si `/auth` viviera en el router de `/usuarios`, no se podría montar en dos grupos distintos sin duplicar rutas o condicionar dependencias por endpoint.

**Consecuencia**: los dos routers comparten el mismo `UsuariosUnitOfWork` (cada uno lo arma con su dependencia), pero se montan por separado. `main.py` documenta que `C-08` hará el re-montaje definitivo.

### D10 — `password_hash` nunca sale: contratos de salida explícitos

**Decisión**: todas las respuestas usan `response_model` (`UsuarioLeer`, `SesionRespuesta`, `YoRespuesta`, `MensajeRespuesta`). Ninguno declara `password_hash`. El servicio devuelve la entidad del ORM y el router la mapea con `UsuarioLeer.model_validate(...)`.

**Por qué**: US-007 CA-2 y la regla dura. `response_model` filtra incluso si un refactor futuro devolviera otra entidad; el test recorre las respuestas de registro, login, `/auth/yo` y cambio de contraseña buscando `password_hash` y `$2b$`.

## Risks / Trade-offs

- **`intento_acceso` deja filas aunque la petición falle** → es el costo aceptado de DD-09; sin él, el límite de RN-08 no podría contar los fallos. La tabla es de auditoría, no de negocio.
- **429 no se anota** → decisión D1: evita extender el bloqueo indefinidamente por peticiones que no verificaron credenciales. Si se quisiera un bloqueo «deslizante», habría que anotar también los 429 y revisar el `Retry-After`.
- **Un login correcto reinicia la cuenta sin borrar filas** → se implementa contando sólo los fallos posteriores al último `exito=true` de `(email, ip)`. La tabla conserva el historial completo.
- **`password_cambiada_en` con microsegundos** → depende de que el reloj del proceso sea monótono hacia adelante; un salto de reloj hacia atrás entre el login y el cambio podría invalidar tokens de forma inesperada. Se acepta: es el mismo reloj para emitir y comparar, y el esquema guarda `timestamptz`.
- **`get_usuario_actual` devuelve `claims`** → `C-08` no debe autorizar con ellos; sólo los usa `/auth/yo` para mostrarlos. La autorización real seguirá consultando `asignacion_rol` en cada petición (RN-04).
- **Sesión implícita de la petición antes de bcrypt en el cambio de contraseña** → para verificar la contraseña actual hay que leer el hash, y leerlo abre una transacción de lectura. El hash **nuevo** sí se calcula antes de abrir el UoW de escritura; la lectura previa es inevitable y no escribe nada.
- **Router `auth` en abierto** → hasta `C-08`, `/usuarios` y `/repuestos` siguen públicos (heredado de `C-06`). `C-08` cierra esa brecha con los dos grupos de rutas.

## Migration Plan

1. Agregar los contratos de la Épica 4 a `app/modules/usuarios/schemas.py`.
2. Agregar los repositorios de roles, intentos y eventos; crear `app/modules/clientes/repository.py` y componerlos en el UoW.
3. Implementar los servicios de registro, login, roles y cambio de contraseña.
4. Implementar `get_usuario_actual` en `app/core/dependencies.py`.
5. Crear `app/modules/usuarios/auth_router.py` y montarlo en `main.py`; calcular el hash ficticio en el lifespan.
6. Escribir `test/auth.http` y `test/test_auth.py`; correr la suite completa.
7. Verificar `openspec validate 2026-10-27-c-07-auth --strict`.

**Rollback**: no hay migraciones. Borrar `auth_router.py` y `clientes/repository.py`, revertir los cambios en `schemas/repository/unit_of_work/service`, `dependencies.py` y `main.py`, y el repo vuelve al estado de `C-06`. La base no se modifica (las filas de prueba viven en la base de test).

## UI Mockups

Decision: no (no UI). Es una API sin frontend; no aplica el gate de mockups.
