# Design

Ver `proposal.md` (Why) y las specs `work-order-management`, `work-order-lifecycle`, `work-order-catalog` y `stock-ledger` (requisitos). Este documento explica **cómo** se cumple ese contrato.

## Context

Al empezar este change, la API ya tenía todo lo que una orden necesita para existir:

- `orden_trabajo`, `item_orden`, `historial_estado_orden` y `estado_orden` con sus FK, CHECK, índices y el disparador de sólo agregado sobre el historial (`C-03`/`C-04`).
- `ClienteRepository`/`VehiculoRepository` con `get_by_id` que excluye las bajas lógicas y `get_by_usuario_id` para «lo propio» (`C-06`/`C-09`).
- `RepuestoRepository`, `MovimientoStockRepository` y el punto único de escritura del stock (`C-10`).
- `AsignacionRolRepository.roles_vigentes` para consultar el rol **vigente** en cada petición (`C-03`), y el grupo protegido de `main.py` con el 401 y el 403 del cambio obligatorio (`C-08`).

Lo que faltaba era el hecho central del dominio: abrir una orden, moverla por su ciclo de vida y descontar el stock al terminarla. El seed deja dos órdenes utilizables —la 1 PENDIENTE de Laura y la 2 EN_REPARACION de Jorge con 4 unidades de `BU-003`, que sólo tiene stock 2— justamente para que el caso C-11 sea reproducible sin preparar datos.

Restricciones que condicionan el diseño:

- **Stack cerrado**: FastAPI + SQLModel + SQLAlchemy async + PostgreSQL. `BackgroundTasks` viene con Starlette; no se agrega nada.
- **Sin migraciones**: las cuatro tablas existen completas. Si hubiera faltado una columna, el change se detenía y lo reportaba.
- **Reglas duras**: el router arma el UoW y el servicio lo abre; `flush()` en repositorios y `commit()` sólo en el UoW; `select` de SQLModel; sin carga perezosa; `timestamptz`; `Decimal` y dinero como string; historial de sólo agregado; ningún `IntegrityError` crudo al cliente.
- **Nomenclatura del enunciado**: el PDF no etiqueta la épica con A-01..A-04. Usa C-10 (alta), C-11 (stock insuficiente al terminar), C-12 (aviso al cliente) y C-13 (cancelación). La evidencia conserva esos códigos y documenta el alias A-01→C-10, A-02→C-11, A-03→C-12, A-04→C-13 que pedía el roadmap. Es una ambigüedad de rótulos, no de comportamiento.

## Goals / Non-Goals

**Goals:**

- Alta PENDIENTE con precio copiado del repuesto, total calculado en `Decimal` y primera línea de historial, todo en un UoW (RN-10).
- `iniciar` asigna el mecánico de la sesión; `terminar` descuenta **todos** los ítems y deja **un** movimiento negativo por ítem; `cancelar` sólo desde PENDIENTE.
- Identidad antes que estado: un mecánico no asignado y un cliente ajeno reciben 403 aunque la transición tampoco fuera válida (SU-04).
- Terminación atómica: si falta stock de un solo ítem, 409 y **cero** escrituras (caso C-11).
- Detalle y listados sin carga perezosa, con un número fijo de consultas.
- Aviso al cliente agendado sólo después del commit (US-026/DD-13).
- Catálogo `GET /estados-orden` de sólo lectura y filtro `estado` validado por contrato (422).

**Non-Goals:**

- Bloqueos de fila o control de concurrencia explícito (ver D7).
- Reabrir una orden TERMINADA o CANCELADA, o borrar órdenes: no está en el TP.
- Editar una orden (falla, ítems o mecánico) después del alta: no hay US que lo pida.
- Escribir el catálogo de estados desde la API: RN-19 lo prohíbe.
- Notificación real (correo, WhatsApp): el alcance pide un aviso simulado.

## Decisions

### D1 — Una sola transacción para la orden, sus ítems, el stock y el historial

**Decisión**: `OrdenesUnitOfWork` declara `ordenes`, `items`, `historial`, `estados`, `clientes`, `vehiculos`, `repuestos` y `movimientos`, todos construidos sobre `self.session`. El router obtiene el UoW con la dependencia `get_uow` **sin abrirlo**; cada servicio lo abre con `async with uow`. Los repositorios sólo hacen `add`/`update` (con `flush()`); el `commit()` ocurre una única vez en `UnitOfWork.__aexit__`, y una excepción dispara `rollback()`.

**Por qué**: RN-13 pide que terminar sea atómico. Si el descuento del repuesto, su `movimiento_stock`, el estado de la orden y la línea de historial no compartieran sesión y transacción, un fallo intermedio podría dejar stock descontado sin movimiento —o una orden TERMINADA sin haber descontado—. Con un solo UoW, la unidad de confirmación es exactamente la unidad de negocio. Reutilizar los repositorios de clientes y repuestos en vez de duplicarlos mantiene un único punto de escritura del stock (`C-10`).

**Escrituras por operación**:

| Operación | Filas que escribe |
|---|---|
| `crear` | `orden_trabajo` + N `item_orden` + 1 `historial_estado_orden` |
| `iniciar` | `orden_trabajo` (estado, mecánico) + 1 historial |
| `terminar` | N `repuesto` (stock) + N `movimiento_stock` + `orden_trabajo` + 1 historial |
| `cancelar` | `orden_trabajo` + 1 historial |

**Consecuencia**: el servicio nunca confirma por su cuenta ni cierra la sesión; si el `commit` falla, el UoW revierte y relanza, y el handler central traduce. No hay `try/except` local que pueda convertir un fallo parcial en éxito.

**Alternativa descartada**: un UoW por repositorio o un `commit` dentro de `terminar`. Sería más simple de escribir y exactamente lo que la regla dura prohíbe: perdería la atomicidad y el rollback del caso C-11.

### D2 — El orden de las verificaciones es parte del contrato: 404 → 403 → 409 → stock

**Decisión**:

- `obtener`: 404 si la orden no existe; después roles vigentes + dueño; si no es personal ni dueño → 403.
- `terminar`: 404 → 403 (ADMIN **o** el mecánico asignado) → 409 de estado → 409 de stock → recién entonces escribe.
- `cancelar`: 404 → 403 (ADMIN/RECEPCION **o** dueño) → 409 (sólo PENDIENTE) → escribe.
- `iniciar`: 404 → 409 (sólo PENDIENTE); la ruta ya exige MECANICO con `requiere_rol`.

Los roles se consultan **en la base** con `AsignacionRolRepository.roles_vigentes(usuario_id)` dentro del servicio, no se confían al token. `terminar` necesita esa consulta porque `requiere_rol("ADMIN", "MECANICO")` sólo prueba que la sesión es personal de taller: no sabe **cuál** mecánico tiene asignada la orden. `cancelar` no lleva `requiere_rol` (DD-06) y el servicio decide entre personal de atención y dueño.

**Por qué**: SU-04 es explícito: la identidad se evalúa antes que el estado. Si se invirtiera, un mecánico no asignado recibiría 409 («la orden no admite esa transición») y aprendería el estado de una orden que no le corresponde; un cliente ajeno recibiría 409 en una orden TERMINADA. Además, un 403 uniforme es la respuesta correcta para una acción no autorizada, incluso cuando la acción tampoco sería posible. El 404 va primero para no disfrazar de «sin permiso» un id inexistente.

**Consecuencia**: `terminar` sobre una orden TERMINADA por su mecánico asignado da 409 (identidad válida, estado inválido); la misma orden por un mecánico ajeno da 403 (caso SU-04 cubierto en los dos sentidos). `cancelar` sobre una orden ajena TERMINADA da 403, y sobre una propia no PENDIENTE da 409.

**Alternativa descartada**: usar `requiere_rol("ADMIN")` en una ruta y otra ruta para el mecánico asignado. Duplicaría endpoints y dejaría el 403 dependiendo de qué ruta eligió el cliente, no de la identidad.

### D3 — La validación de stock precede a toda escritura

**Decisión**: `terminar` recorre `orden.items` y comprueba `item.repuesto.stock >= item.cantidad` **antes** del primer `update`. Si alguno falla, lanza `Conflicto` con `"No hay stock suficiente para terminar la orden."` y el UoW revierte. Si todos alcanzan, recorre otra vez para descontar y agregar el movimiento.

**Por qué**: el caso C-11 es exactamente la orden 2 del seed (4 × `BU-003` con stock 2). Validar y escribir en el mismo bucle dejaría el primer repuesto descontado cuando el segundo falla; el rollback lo repararía, pero la regla pide además que el servicio **no intente** una escritura que ya sabe inválida, y así el mensaje es de negocio y no de integridad. La comprobación usa el repuesto precargado por `get_con_items` (sin consulta por ítem).

**Por qué dos bucles**: el primero es una decisión de negocio sobre el estado leído; el segundo, la aplicación. Separarlos hace evidente que no hay escritura antes de la última validación y permite citar la línea exacta en la suite.

**Consecuencia**: ante faltante no se escribe ningún `movimiento_stock`, ninguna orden cambia de estado y no se agrega historial. El CHECK `stock >= 0` de la base sigue existiendo como última defensa, pero no es el camino esperado.

**Alternativa descartada**: descontar con un `UPDATE ... WHERE stock >= cantidad` y contar filas. Sería atómico a nivel fila, pero exigiría SQL manual, perdería el mensaje uniforme y complicaría el rollback total que pide el caso.

### D4 — El aviso al cliente se agenda después del commit, nunca dentro del UoW

**Decisión**: `terminar` en el servicio sólo devuelve la orden ya confirmada. El router, después del `await service.terminar(...)`, llama a `background_tasks.add_task(service.avisar_cliente, orden.id)`. `avisar_cliente` hace `await asyncio.sleep(0.5)` y un `logger.info`.

**Por qué**: DD-13/US-026. Un aviso enviado antes de confirmar mentiría si la transacción revierte, y un 403/404/409 nunca debe producir un aviso. Como el `add_task` está después del `return` del servicio —y el servicio confirmó al salir del `async with`—, sólo se agenda una terminación exitosa. Además, la tarea no corre dentro de la transacción: no alarga el UoW ni comparte su sesión.

**Verificación**: la suite usa `caplog` sobre el logger `app.ordenes` y comprueba que una terminación válida deja la línea del aviso y que un rechazo (403/409) no la deja. `migrations/env.py` llama a `logging.config.fileConfig` con el valor por defecto `disable_existing_loggers=True`, que deshabilita el logger del módulo; el test lo rehabilita con un helper explícito antes de capturar. No es un defecto del servicio, es una interacción con la configuración de Alembic.

**Alternativa descartada**: ejecutar el aviso con `asyncio.create_task` desde el servicio. No queda atado al ciclo de la petición, puede perderse al cerrar el proceso y no hay forma de saber si el commit ocurrió.

### D5 — Precargas fijas: tres consultas para el detalle y un `listar` propio

**Decisión**:

- `get_detalle` hace **tres** consultas, independientes de la cantidad de ítems: (1) orden + `vehiculo` + `vehiculo.cliente` con `joinedload` anidado, (2) `items` con su `repuesto` con `selectinload(...).joinedload(...)`, (3) `historial_estados` con `selectinload`.
- `get_con_items` (terminar) hace dos: orden + vehículo y sus ítems con repuesto.
- `get_con_vehiculo` (iniciar) y `get_con_dueno` (cancelar) hacen una.
- `OrdenTrabajoRepository.listar` es propio: cuenta con `count(*filtros)` y página con `joinedload(vehiculo)`, `order_by(creada_en DESC, id DESC)`, `offset/limit`.

**Por qué**: todas las relaciones del esquema declaran `lazy="raise_on_sql"`, así que un acceso no precargado **lanza** en vez de emitir una consulta silenciosa. Eso convierte cualquier N+1 en un error visible, pero obliga a precargar exactamente lo que el contrato usa. El detalle necesita patente, nombre del cliente, ítems con código/descripción/precio y el historial: tres consultas fijas cubren todo y C-12 podrá medirlas.

**Por qué no `BaseRepository.list_page`**: ese método no acepta opciones de carga y el listado necesita `orden.vehiculo.patente` por fila. Usarlo obligaría a un acceso perezoso (prohibido) o a una consulta por orden (N+1). El `listar` propio replica el contrato de `Page` y pasa los mismos filtros al `count`, para que `total` y la página no discrepen.

**Consecuencia**: `listar_mis_ordenes` reutiliza ese `listar` con `vehiculo_id.in_(...)`; una sesión sin ficha de cliente devuelve una página vacía sin consultar órdenes.

**Alternativa descartada**: `selectinload` para el vehículo en el listado. Sería correcto pero agrega una consulta por página; un `joinedload` de muchos-a-uno no multiplica filas.

### D6 — El contrato no acepta precio, total, estado ni mecánico

**Decisión**: `OrdenCrear` declara sólo `vehiculo_id` (`gt=0`), `falla` (1..2000) e `items` (`min_length=1`). `ItemOrdenCrear` declara `repuesto_id` y `cantidad` (`gt=0`); el precio **no** existe en el contrato. Un validador rechaza el mismo `repuesto_id` repetido. `ContratoEntrada` aplica `extra="forbid"`, así que `precio_unitario`, `total`, `estado`, `mecanico_id`, `creada_en` o `cliente_id` producen 422 nombrando el campo.

**Por qué**: RN-10. El servidor copia `repuesto.precio` a cada ítem y suma `precio * cantidad` con `Decimal`; el total nunca llega del cliente. Aceptar `precio_unitario` permitiría inventar la factura; aceptar `estado` o `mecanico_id` permitiría nacer EN_REPARACION o asignarse una orden sin pasar por `iniciar`. Los repetidos se rechazan en el contrato —y no en la base— porque no hay un índice único parcial que los impida y el mensaje debe nombrar `items`.

**Por qué `Decimal`**: `Dinero` serializa `Decimal` como string con dos decimales (`"6000.00"`), tanto en `model_dump()` como en el JSON. El subtotal se calcula en el mapeo (`precio_unitario * cantidad`) y también viaja como string. Nunca hay `float`.

**Consecuencia**: el alta con un repuesto o vehículo inexistente/dado de baja es 409 y no crea nada (ni orden ni ítems ni historial); el catálogo sin `PENDIENTE` también es 409 (caso C-09). Los 409 de negocio no exponen el `IntegrityError`.

**Alternativa descartada**: declarar `precio_unitario` como opcional y comparar con el del repuesto. Seguiría permitiendo que el cliente fije el precio cuando coincide, y obliga a decidir qué hacer cuando no: dos comportamientos para el mismo campo.

### D7 — Máquina de estados mínima y catálogo de sólo lectura

**Decisión**: las transiciones implementadas son PENDIENTE→EN_REPARACION (`iniciar`), EN_REPARACION→TERMINADA (`terminar`) y PENDIENTE→CANCELADA (`cancelar`). Cualquier otra combinación es 409 con `"La orden no admite esa transición de estado."`. `EstadoOrdenRepository` **no** hereda de `BaseRepository` (DD-07): la PK es `codigo` y desde la API no se escribe, así que sólo expone `get(codigo)` y `listar()` por `posicion`. El filtro de `GET /ordenes` usa `EstadoOrdenCodigo(StrEnum)`: un valor no declarado es 422 antes de tocar la base (caso C-17).

**Por qué**: `crear` verifica que `PENDIENTE` exista antes de insertar; un catálogo vacío no puede producir una orden con un estado que no está en la tabla. Heredar `BaseRepository` le daría `add`/`update`/`delete` a un catálogo que RN-19 declara inmutable: la forma del tipo debe decir la verdad. El enum del contrato y la tabla son dos fuentes distintas a propósito: el enum valida la entrada (422) y la tabla es la fuente de verdad de la descripción y la posición.

**Consecuencia**: `GET /estados-orden` devuelve las filas ordenadas por `posicion`, con `es_final`; cualquier sesión válida puede leerlo. No hay ninguna ruta que escriba el catálogo.

**Alternativa descartada**: validar el filtro contra la tabla y devolver 409/400. Sería una consulta extra para un error de contrato y rompería la convención de 422 del resto de la API.

### D8 — Sin bloqueos de fila: se acepta la carrera y la base es la última defensa

**Decisión**: la validación de stock de `terminar` lee el stock sin `SELECT ... FOR UPDATE`. Dos terminaciones concurrentes sobre el mismo repuesto pueden pasar la validación con el mismo stock; la primera confirma y la segunda choca contra el CHECK `stock >= 0`. Esa segunda transacción revierte entera (orden, ítems, movimientos e historial) y el handler central responde 409 por integridad, sin texto crudo.

**Por qué**: el TP no pide control de concurrencia y agregar bloqueos de fila introduciría un modo de fallo (deadlocks entre órdenes que comparten repuestos en distinto orden) que hoy no existe. El CHECK de la base ya garantiza el invariante «stock nunca negativo»; el rollback total garantiza que la perdedora no deje rastros. Se documenta como límite conocido en vez de esconderlo.

**Consecuencia**: en el caso raro de carrera, el cliente recibe 409 y puede reintentar. La suite no simula concurrencia real; el caso C-11 prueba el camino secuencial, que es el que pide el enunciado.

**Alternativa descartada**: bloquear los repuestos en orden de id antes de validar. Correcto, pero fuera de alcance, con más superficie de error y sin un caso de prueba que lo exija.

### D9 — Sin migraciones; `main.py` sólo suma el import y tres routers

**Decisión**: el change no crea migraciones, no toca modelos, `seed.py` ni `test/conftest.py`. En `main.py` se agrega el import de `ordenes.router` y tres `include_router` dentro del `grupo_protegido` ya existente: `ordenes_router` (`/ordenes`), `estados_orden_router` (`/estados-orden`) y `ordenes_propios_router` (`/mis-ordenes`).

**Por qué**: el esquema de `C-04` ya tiene las cuatro tablas, sus FK, CHECK, índices y el disparador. Los routers nuevos deben heredar el 401 de la sesión y el 403 del cambio obligatorio, y el grupo protegido es el único lugar donde eso se monta una sola vez. `main.py` no tenía ningún router de órdenes, así que el cambio es aditivo y no compite con otros módulos.

**Consecuencia**: sin cookie, las ocho rutas responden 401; con una sesión que no cumplió el cambio obligatorio, 403. `GET /estados-orden` y `GET /mis-ordenes` no llevan `requiere_rol` porque cualquier sesión válida puede consultarlos; sí llevan la sesión.

**Alternativa descartada**: montar los routers fuera del grupo y declarar la dependencia de sesión en cada ruta. Duplicaría la seguridad y abriría la puerta a olvidarla en una ruta nueva.

## Risks / Trade-offs

- **Carrera de stock sin bloqueo** → dos terminaciones simultáneas pueden competir; la perdedora revierte entera y recibe 409 por el CHECK. Es el trade-off explícito de D8.
- **El aviso simulado bloquea la respuesta en los tests** → `httpx.ASGITransport` espera las `BackgroundTasks` antes de devolver. En producción Starlette las corre después de enviar la respuesta. El `sleep` de 0.5 s sólo afecta la suite (2 tests que lo ejercitan), no la latencia real del endpoint.
- **El logger del módulo está deshabilitado por Alembic** → `fileConfig(..., disable_existing_loggers=True)` en `migrations/env.py` desactiva `app.ordenes` al importar la app. El test que verifica el aviso lo rehabilita; en un proceso sin Alembic el logger funciona normalmente.
- **`crear` relee el detalle dentro del mismo UoW** → una consulta más en el alta (tres, igual que el detalle). Evita mapear ids recién asignados a mano y garantiza que la respuesta 201 tenga exactamente la misma forma que el `GET`.
- **Sin edición de órdenes** → corregir la falla o los ítems exige cancelar y volver a crear. No hay US que pida edición y agregarla abriría la puerta a recalcular el total fuera del alta.
- **El catálogo vacío es 409, no 500** → es una precondición de datos de despliegue; el mensaje nombra el catálogo para que el operador sepa qué falta (caso C-09).

## Migration Plan

1. Escribir los contratos en `app/modules/ordenes/schemas.py` (enums, alta sin precio, salidas con `Dinero`).
2. Implementar `repository.py` (precargas fijas, `listar` propio, catálogo de sólo lectura) y `unit_of_work.py` (ocho repositorios sobre la misma sesión).
3. Implementar `service.py` con el orden de verificaciones de D2 y la transacción de D1/D3.
4. Implementar `router.py` con los tres routers, el mapeo ORM → contrato y el `BackgroundTasks` de D4.
5. Sumar el import y los tres `include_router` en `main.py`.
6. Escribir `test/ordenes.http` y `test/test_ordenes.py` (TDD: la suite nueva falló primero).
7. Correr `TEST_POSTGRES_DB=taller_mecanico_c11 python -m pytest test/ -q` y `openspec validate 2026-10-27-c-11-ordenes-trabajo --strict`.

**Rollback**: no hay migraciones. Revertir `main.py` (quitar el import y los tres `include_router`), borrar `app/modules/ordenes/{schemas,repository,unit_of_work,service,router}.py` y la evidencia nueva; la base queda idéntica. Los movimientos e historiales que se hayan escrito en pruebas son de sólo agregado y no se pueden borrar (RN-15), pero no bloquean nada: el código vuelve al estado de `C-10`.

## UI Mockups

Decision: no (no UI). Es una API sin frontend; no aplica el gate de mockups.
