# Flujos Principales

Cada flujo se documenta extremo a extremo, mostrando interacciones entre componentes. Los componentes son los de la estructura obligatoria: `router.py` → `service.py` → `unit_of_work.py` → `repository.py` → base.

## Flujo 1: Arranque del servidor (lifespan)

**Disparador**: `uvicorn main:app` (o equivalente)
**Actor**: operador

**Pasos**:
1. `main.py` importa la app; **no** se crea ningún motor ni sesión al importar (EA-08).
2. El **lifespan** (context manager de arranque): crea el motor asincrónico con el pool declarado en `Settings`, crea la fábrica de sesiones, y los guarda en `app.state`.
3. El lifespan calcula **una vez** el hash ficticio del login (para RN-09).
4. El servidor atiende peticiones.
5. Al apagar: el lifespan cierra el motor con `dispose()`.

**Casos de error**:
- Faltan `SECRET_KEY` o `POSTGRES_PASSWORD` → la app **no arranca** (Settings sin default).

## Flujo 2: Auto-registro de un cliente (RN-02)

**Disparador**: `POST /auth/registro` (grupo abierto)
**Actor**: cliente potencial

**Pasos**:
1. `router.py` recibe el cuerpo y lo valida contra el contrato (`extra="forbid"`; password ≤ 72 bytes).
2. El router construye el Unit of Work del módulo `usuarios` con una dependencia y se lo pasa al servicio **sin abrirlo**.
3. El service abre el UoW con `async with`:
   a. Calcula el hash de la contraseña con bcrypt **fuera del bucle** (`to_thread` + semáforo) y **antes** de abrir la transacción.
   b. Crea la fila `usuario`.
   c. Crea la fila `asignacion_rol` con `rol='CLIENTE'`.
   d. Crea la fila `cliente` apuntando a ese usuario. Si el `documento` ya es de otro cliente → el repositorio lanza `IntegrityError` al flush; el service lo traduce a **409 con mensaje propio** y el UoW **revierte** (no queda ninguna fila suelta).
   e. Registra el evento de seguridad (actor = el nuevo usuario).
4. Al salir del bloque, el UoW **confirma**.
5. El router responde **201**.

**Diagrama de secuencia**:
```
Cliente → Router → Service → UoW → Repository → DB
                                    (3 inserts + evento en una transacción)
         ← 201  ← traduce 409 si IntegrityError (UoW revierte)
```

**Casos de error**:
- Correo repetido → 409 (única en `usuario.email`)
- Documento repetido → 409 y **no se apropia** de la ficha existente (C-02)
- Contraseña > 72 bytes → 422 (contrato)

## Flujo 3: Login (RN-08, RN-09)

**Disparador**: `POST /auth/login` (grupo abierto)
**Actor**: cualquier persona

**Pasos**:
1. El servicio evalúa **primero** el límite de intentos (RN-08): cuenta en `intento_acceso` los fallos con el mismo `(email, ip)` en los últimos 60 s.
2. Si ≥ 5 fallos → responde **429** con `Retry-After`, **sin calcular ningún hash** y sin verificar la contraseña.
3. Si pasa: busca el usuario.
   - Existe → verifica la contraseña contra su `password_hash` (bcrypt, `to_thread` + semáforo).
   - No existe → verifica contra el **hash ficticio** calculado en el lifespan (misma duración; no revela que la cuenta no existe — RN-09).
4. Cada intento (correcto o fallido) se anota en `intento_acceso` **en su propia sesión y transacción, que se confirman siempre** — única escritura que no comparte la transacción de la petición (sección 6.8.1), porque el fallo que se quiere contar es el mismo que la revierte.
5. Si la verificación falla → **401** con el mismo cuerpo que un correo inexistente.
6. Si pasa: emite el JWT (`sub`, `iat`, `exp`, roles vigentes al emitir) y lo devuelve en `Set-Cookie` (`access_token`, HttpOnly, SameSite=Lax, Max-Age = duración, Secure configurable). Un login correcto **reinicia** la cuenta de fallos (los fallos viejos quedan en la tabla pero dejan de contar).
7. El cuerpo responde 200: `{ "mensaje": "Sesión iniciada", "debe_cambiar_password": ..., "expira_en_segundos": ... }` — **sin token**.

**Casos de error**:
- Credencial mala → 401 (mismo cuerpo que correo inexistente, duración parecida)
- 6 intentos fallidos → el sexto 429 con `Retry-After` (C-05)

## Flujo 4: Cambio obligatorio de contraseña (RN-06, RN-07)

**Disparador**: `POST /auth/cambiar-password` (grupo abierto, con sesión)
**Actor**: usuario con `debe_cambiar_password` (p. ej. `nuevo@example.com` del seed)

**Pasos**:
1. Con `debe_cambiar_password` activo, cualquier ruta del **grupo protegido** responde **403**; sólo `/auth` y salud pasan (dos grupos de rutas en `main.py`, control montado una sola vez — sección 5.10).
2. El usuario llama `/auth/cambiar-password` con la contraseña actual y la nueva.
3. El servicio verifica la actual (bcrypt) y guarda la nueva; anota `password_cambiada_en` con **hora completa** (fracciones de segundo) y limpia `debe_cambiar_password`.
4. El servicio emite un **token nuevo** (se emite **después** de anotar el cambio).
5. A partir de ahí: el token **nuevo** vale; los **anteriores** dan 401 porque su `iat` es anterior a `password_cambiada_en`, comparados **sin truncar** (RN-07). Aunque sean del mismo segundo que el cambio, los de antes no pasan; el del propio cambio sí (se emite después).

**Casos de error**:
- Contraseña actual mala → 401
- Nueva ≤ 8 bytes o > 72 bytes u otra regla del contrato → 422
- Sin sesión → 401

## Flujo 5: Autorización de una petición protegida (RN-04, RN-06)

**Disparador**: cualquier `GET/POST/PATCH/DELETE` del grupo protegido
**Actor**: usuario con cookie

**Pasos**:
1. `get_usuario_actual` lee `request.cookies['access_token']`.
   - Sin cookie, token inválido/vencido → **401**.
   - Verifica la firma con la clave del entorno.
   - Busca el usuario: no existe o `activo=False` → **401**.
   - Compara `iat` del token con `password_cambiada_en`, **sin truncar**: token anterior → **401** (RN-07).
2. Si `debe_cambiar_password` → **403** (el grupo protegido lo tiene montado).
3. `requiere_rol(...)` consulta `asignacion_rol` **en la base, en cada petición** (RN-04): ¿hay una fila con ese rol, no revocada y sin vencer?
   - No → **403**. Revocar un rol le quita el permiso a la sesión abierta **sin esperar** a que el token venza (C-07).
4. La ruta pasa al handler.

## Flujo 6: Gestión de roles (RN-03, RN-05)

**Disparador**: `POST /usuarios/{id}/roles` o `DELETE /usuarios/{id}/roles/{rol}` (ADMIN)
**Actor**: administrador

**Pasos (asignar)**:
1. Valida el contrato: `vence_en` opcional, pero si viene debe ser **con zona horaria** y en el **futuro** (sin zona o en el pasado → **422**, no 409 — Ejercicio 5).
2. Si el rol ya tiene una asignación **abierta** (no revocada, sin vencer) → **409** (índice único parcial, RN-03). Si el rol anterior **venció**, lo cierra y abre una nueva.
3. Inserta la fila con `desde`, `vence_en`, `otorgada_por`.
4. Registra evento de seguridad.

**Pasos (revocar)**:
1. Autoprotección (RN-05): si el admin intenta revocarse **su propio** ADMIN → **409**. Tampoco puede revocar el último ADMIN vigente.
2. Escribe `revocada_en` en la fila; **no borra** (el historial queda).
3. La siguiente petición de la sesión afectada → **403** (RN-04 consulta en cada request).

**Casos de error**:
- Vencimiento en el pasado o sin zona → 422
- Reasignar un rol abierto → 409
- Autoprotección → 409 (C-08)

## Flujo 7: Alta de una orden de trabajo (RN-10, RN-19)

**Disparador**: `POST /ordenes` (RECEPCION o ADMIN)
**Actor**: recepción

**Pasos**:
1. Contrato: `{vehiculo_id, falla, items: [{repuesto_id, cantidad}]}`. **No** acepta precio, total, estado ni fecha (`extra="forbid"`).
2. El servicio abre el UoW (módulo `ordenes`):
   a. Verifica que el vehículo exista y no esté dado de baja.
   b. Verifica que el catálogo `estado_orden` **no esté vacío**: si lo está → **409 con mensaje propio** (RN-19).
   c. Para cada ítem: lee el repuesto, **copia** su `precio` a `precio_unitario`, valida que esté vigente. Repetido en el request → rechazo (UNIQUE `(orden_id, repuesto_id)` / validación de contrato).
   d. Calcula el `total` en el servidor (`Decimal`).
   e. Inserta `orden_trabajo` con `estado='PENDIENTE'`.
   f. Inserta los `item_orden` (composición: los datos viajan dentro del alta).
   g. Inserta la primera línea de `historial_estado_orden` (`desde=null`, `hasta='PENDIENTE'`).
3. Confirma; responde **201** con la orden enriquecida (patente, cliente, ítems con subtotal, historial).

**Casos de error**:
- Repuesto inexistente o dado de baja → 409 y la orden **no queda creada** (C-10)
- Catálogo vacío → 409
- Vehículo dado de baja → 409

## Flujo 8: Iniciar una orden (RN-11)

**Disparador**: `POST /ordenes/{id}/iniciar` (MECANICO)
**Actor**: mecánico

**Pasos**:
1. La ruta exige rol MECANICO (`requiere_rol`).
2. El servicio verifica que el estado sea `PENDIENTE` (si no → **409**).
3. Cambia a `EN_REPARACION`, asigna `mecanico_id` = el usuario actual.
4. Deja una línea de `historial_estado_orden` (`PENDIENTE → EN_REPARACION`).
5. Confirma; 200.

## Flujo 9: Terminar una orden — descuento de stock en una sola transacción (RN-13, RN-14)

**Disparador**: `POST /ordenes/{id}/terminar` (mecánico asignado o ADMIN)
**Actor**: mecánico asignado / administrador

**Pasos**:
1. El servicio verifica la identidad: ¿es el mecánico asignado o ADMIN? Si no → **403** (antes de mirar el estado — RN-12 manda 403 antes que 409 en cancelar; acá aplica el mismo criterio de identidad primero).
2. Verifica el estado `EN_REPARACION` (si no → **409**).
3. Dentro de **un solo bloque** `async with uow` (un Unit of Work):
   a. Para **cada** `item_orden`: descuenta `repuesto.stock` y crea un `movimiento_stock` (cantidad de salida, `orden_id`, usuario, motivo).
   b. Cambia el estado a `TERMINADA`.
   c. Inserta la línea de `historial_estado_orden`.
   d. Si **algún** repuesto no alcanza (`stock < cantidad`) → lanza el error **antes** de escribir nada más; el UoW **revierte** y responde **409**: el estado, el stock, los movimientos y el historial quedan **exactamente como estaban** (C-11).
4. Al salir del bloque sin excepción: **confirma**.
5. **Después** de enviar la respuesta, corre el `BackgroundTasks` del aviso al cliente (simulado con `await asyncio.sleep(0.5)` + log) — sólo si la operación se confirmó (C-12).

**Casos de error**:
- Stock insuficiente en cualquier ítem → 409, rollback total (C-11)
- Estado no `EN_REPARACION` → 409

## Flujo 10: Cancelar una orden (RN-11, RN-12)

**Disparador**: `POST /ordenes/{id}/cancelar` (RECEPCION, ADMIN o el **dueño** del vehículo)
**Actor**: recepción / admin / cliente dueño

**Pasos**:
1. La ruta **no** lleva `requiere_rol` — el dueño no tiene rol de personal.
2. El servicio decide **primero quién es y qué relación tiene** con la orden:
   - Es RECEPCION o ADMIN → pasa.
   - Es el dueño del vehículo de la orden → pasa.
   - No tiene relación → **403**.
3. **Recién después** mira el estado: si no es `PENDIENTE` (p. ej. TERMINADA) → **409**.
4. Cambia a `CANCELADA` + línea de historial. Confirma. 200.

**Casos de error**:
- Orden ajena → 403 (C-13)
- Orden TERMINADA → 409 (C-13)

## Flujo 11: Reposición de stock y cambio de precio (RN-14, RN-20)

**Disparador**: `POST /repuestos/{id}/reponer` o `PATCH /repuestos/{id}` (ADMIN)

**Reponer**:
1. El servicio abre el UoW: incrementa `stock` y crea un `movimiento_stock` (entrada). **Punto único de escritura de stock** (RN-14). Confirma. 200.

**Cambiar precio**:
1. `PATCH /repuestos/{id}` sólo acepta `descripcion` y `precio` (no `stock` — 422 si viene, C-16).
2. Si viene `precio` y es distinto del actual: en el **mismo UoW**, actualiza el repuesto **e inserta** una línea en `historial_precio_repuesto` (`precio_anterior`, `precio_nuevo`, usuario, cuando). Un PATCH que no cambia el precio **no deja línea** (C-18).

## Flujo 12: Salud (liveness vs readiness)

**Disparador**: `GET /health/live` o `GET /health/ready`
**Actor**: orquestador / operador

**Pasos**:
- `/health/live`: no toca la base → 200 siempre que el proceso atienda.
- `/health/ready`: ejecuta `SELECT 1`; si la base contesta → 200; si no → **503**. El proceso puede estar vivo y no estar listo, y reiniciarlo no arregla una base caída.

## Flujo 13: Sólo agregado verificado en psql (C-14)

**Disparador**: consultas manuales en psql (no pasan por la API)
**Actor**: corrector / desarrollador

**Pasos**:
1. `UPDATE` y `DELETE` sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` → **los seis rechazados por el disparador** de la migración 2 (venga de donde venga — RN-15).
2. Insertar una `orden_trabajo` con un `estado` que **no** está en el catálogo → rechazado por la **clave foránea**.
3. La evidencia es un `test/solo_agregado.sql` con captura de psql.
