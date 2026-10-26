# Reglas de Negocio

Cada regla tiene un código único `RN-{DOMINIO}-{NN}` para trazabilidad. Los enunciados y garantes son los de la consigna (sección «Reglas de negocio», pp. 7–9).

## Dominio: Integridad y unicidad (RN-01)

- **RN-01**: El correo de un usuario y el documento de un cliente son únicos. La patente de un vehículo y el código de un repuesto son únicos **entre los que no están dados de baja**. — *Garante*: UNIQUE e índices únicos parciales en la base; 409 con mensaje propio. La unicidad está garantizada **por la base**, no con una consulta previa.

## Dominio: Registro e identidad (RN-02)

- **RN-02**: El auto-registro crea el usuario, su rol CLIENTE y su ficha de cliente: o quedan las tres filas, o ninguna. Si el documento ya es de un cliente del taller, el registro da 409 y **no se apropia** de esa ficha. — *Garante*: un solo Unit of Work.

## Dominio: Roles y autorización (RN-03 a RN-07)

- **RN-03**: Un usuario tiene a lo sumo una asignación **abierta** por rol. — *Garante*: índice único parcial `(usuario_id, rol) WHERE revocada_en IS NULL`; 409.
- **RN-04**: Los permisos se deciden con los **roles vigentes en la base, en cada petición**. Los roles que trae el token son **informativos**. — *Garante*: dependencia que consulta `asignacion_rol`. Revocar un rol le quita el permiso a una sesión ya abierta, sin esperar a que el token venza (sección 5.9).
- **RN-05**: Un administrador **no puede revocarse su propio rol ADMIN**, y el sistema **nunca queda sin administradores vigentes**. — *Garante*: comprobación en el servicio; 409.
- **RN-06**: Mientras un usuario tenga el cambio de contraseña pendiente (`debe_cambiar_password`), **sólo** puede usar las rutas de `/auth` y las de salud. — *Garante*: dos grupos de rutas; 403 en el resto.
- **RN-07**: Al cambiar la contraseña, las sesiones emitidas **antes** dejan de valer, aunque sean del mismo segundo que el cambio; la que devuelve el propio cambio, no. — *Garante*: comparación de `iat` con `password_cambiada_en`, **sin truncar**; 401. El token se emite con la hora completa (JWT admite fracciones de segundo en `iat`), se compara sin truncar a segundos, y el token nuevo pasa porque se emite después de anotar el cambio (sección 5.10). Si se truncaran, una sesión iniciada en el mismo segundo que el cambio, pero antes, sería indistinguible de la nueva y seguiría valiendo.

## Dominio: Autenticación (RN-08, RN-09)

- **RN-08**: Después de **5 intentos fallidos** con el mismo correo **desde la misma dirección** en **60 segundos**, el login responde **429 sin verificar la contraseña**. Un login correcto reinicia la cuenta: los fallos anteriores siguen en la tabla, pero dejan de contar. — *Garante*: conteo sobre `intento_acceso`; cabecera `Retry-After`. El límite se evalúa **primero** en el login (cuesta una consulta); si se superó, 429 sin calcular ningún hash (sección 5.5).
- **RN-09**: El login responde **lo mismo, y tarda lo mismo**, exista o no el correo. — *Garante*: mismo mensaje; verificación contra un **hash ficticio** cuando el correo no existe (el hash ficticio se calcula una vez en el lifespan). No se revela qué cuentas existen.

## Dominio: Órdenes de trabajo (RN-10 a RN-13, RN-16, RN-17, RN-19)

- **RN-10**: Una orden nace **PENDIENTE** con al menos un ítem y **sin repuestos repetidos**. El precio de cada ítem se **copia** del repuesto, y el total lo calcula el **servidor**. — *Garante*: DTO; el precio y el total **nunca viajan en el cuerpo** del request.
- **RN-11**: Las transiciones de una orden son:
  - `PENDIENTE → EN_REPARACION` (la inicia un **mecánico**, que queda asignado),
  - `EN_REPARACION → TERMINADA` (la termina el **mecánico asignado** o un **administrador**),
  - `PENDIENTE → CANCELADA`.
  — *Garante*: servicio; 409 si el estado no lo permite.
- **RN-12**: Cancelan una orden la **recepción**, el **administrador** o el **dueño del vehículo**. El permiso se evalúa **antes** que el estado. — *Garante*: servicio; **403 antes que 409**. Por eso la ruta `/ordenes/{id}/cancelar` no lleva `requiere_rol`: el dueño no tiene rol de personal y recibiría «no tenés permiso» cuando sí lo tiene.
- **RN-13**: Terminar una orden **descuenta el stock de cada ítem**, deja **un movimiento por cada salida** y **una línea de historial**. Si un repuesto no alcanza, **no queda ninguna de esas escrituras**. — *Garante*: un solo Unit of Work; 409. (Caso C-11: la orden 2 pide 4 bujías cuando hay 2 → 409 y todo queda exactamente como estaba.)
- **RN-16**: Un vehículo o un repuesto dado de baja **deja de aparecer** y **no se puede usar en órdenes nuevas**, pero sus datos se conservan. Un vehículo con **órdenes abiertas** —en un estado que el catálogo no marca como final (`es_final`)— **no se da de baja**. — *Garante*: borrado lógico; `es_final`; 409.
- **RN-17**: Lo propio **sólo pide estar autenticado**: un cliente ve sus vehículos y las órdenes de sus vehículos, y ninguna otra. — *Garante*: rutas `/mis-*` y comprobación de dueño; 403.
- **RN-19**: Los estados posibles de una orden son las **filas del catálogo** `estado_orden`. El catálogo se **consulta desde la API** y **no se edita desde ella**. Si está vacío, crear una orden responde **409 con un mensaje propio**. — *Garante*: clave foránea; repositorio de sólo lectura (el catálogo no hereda de `BaseRepository`: su clave primaria no es `id` y desde la API no se escribe).

## Dominio: Stock e historiales — sólo agregado (RN-14, RN-15, RN-20)

- **RN-14**: El stock de un repuesto **sólo cambia a través de movimientos**: el alta con stock inicial, la reposición y la terminación de órdenes. **No se edita por PATCH**. — *Garante*: punto único de escritura de stock.
- **RN-15**: `historial_estado_orden`, `movimiento_stock` y `historial_precio_repuesto` son de **sólo agregado**: nadie puede modificar ni borrar sus filas. — *Garante*: **disparador en la base**, instalado por la migración escrita a mano (la comparación automática de Alembic no ve funciones ni disparadores). El disparador rechaza **cualquier** UPDATE o DELETE sobre esas tres tablas, **venga de donde venga** (sección 6.9; caso C-14 en psql).
- **RN-20**: Cada cambio del precio de un repuesto deja una línea en `historial_precio_repuesto`, **en la misma transacción** que el cambio. Un PATCH que **no cambia el precio** **no deja línea**. — *Garante*: un solo Unit of Work; CHECK `precio_nuevo` distinto de `precio_anterior`.

## Dominio: Errores y contratos (RN-18)

- **RN-18**: **Ningún error** devuelve al cliente texto interno de la base, que le entregaría el mapa del esquema (sección 4.13). **Ninguna entrada inválida termina en un 500**. — *Garante*: traducción del `IntegrityError` a un 409 con mensaje propio; validación en el contrato (`extra="forbid"`, 422).

## Dominio: Excepciones globales

- **Dinero**: `NUMERIC` en la base y `Decimal` en Python; **nunca** `float` (sección 2.7). Los montos viajan como string en los contratos (p. ej. `"total": "68000.00"`).
- **Fechas**: todas las columnas de fecha son `timestamptz`. El vencimiento de un rol llega **con zona horaria y en el futuro**: una fecha sin zona es ambigua (¿la hora de quién?) y una que ya pasó no choca con nada guardado; las dos son **422, no 409** (Ejercicio 5).
- **Sólo agregado**: además del disparador, la sección 6.9 describe un segundo mecanismo independiente (el rol de base de la aplicación no tiene permiso de modificar esas tablas). **No se pide** en el TP porque usa un solo rol de base; cualquiera de los dos alcanza, tener los dos es defensa en profundidad.
- **Intento de acceso**: es la **única** escritura del sistema que no comparte la transacción de su petición — se anota en sesión y transacción propias, que se confirman **siempre**, porque el fallo que se quiere contar es el mismo que la revierte (sección 6.8.1). El código lo declara en un comentario, junto con su costo: deja filas aunque la petición falle.
