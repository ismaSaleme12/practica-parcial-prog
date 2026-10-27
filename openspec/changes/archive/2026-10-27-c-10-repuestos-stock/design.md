# Design

Ver `proposal.md` (Why) y las specs `spare-part-management`, `stock-ledger` y `price-history` (requisitos). Este documento explica **cómo** se cumple ese contrato.

## Context

Al empezar este change, el módulo `repuestos` ya tenía las seis capas de `C-01`/`C-03` y los contratos de `C-06`:

- `Repuesto`, `MovimientoStock` e `HistorialPrecioRepuesto` con sus CHECK, el índice único parcial `uq_repuesto_codigo_vigente WHERE borrado_en IS NULL` y el disparador que rechaza UPDATE y DELETE sobre las dos tablas de auditoría (`C-04`).
- `RepuestoRepository(SoftDeleteRepository[Repuesto])` con `filtro_busqueda` parametrizado.
- `GET /repuestos`, `GET /repuestos/{id}` y `POST /repuestos` con `PersonalDep`/`AdminDep`, montados en el grupo protegido de `main.py` (`C-08`).

Lo que faltaba era el ABM completo: PATCH, baja lógica, reposición y los dos historiales. El seed ya deja los cuatro repuestos con su movimiento «Stock inicial» y una línea de precio para `FA-001`, así que la suite arranca con datos auditables.

Restricciones que condicionan el diseño:

- **Stack cerrado**: FastAPI + SQLModel + SQLAlchemy async + PostgreSQL. Sin dependencias nuevas.
- **Sin migraciones**: las tres tablas ya existen con todo lo que hace falta. Si hubiera faltado una columna, el change se detenía y lo reportaba.
- **Reglas duras**: `flush()` en repositorios y `commit()` sólo en el UoW; `select` de SQLModel; sin lazy loading; `timestamptz`; `Decimal` y dinero como string; el servicio no construye su UoW; las tablas de auditoría son de sólo agregado; ningún `IntegrityError` crudo al cliente.

## Goals / Non-Goals

**Goals:**

- El stock sólo se escribe en el alta con `stock_inicial` y en la reposición, y cada escritura deja su `MovimientoStock` en el mismo UoW (RN-14).
- PATCH limitado a `descripcion` y `precio` con `exclude_unset`; `stock` en el cuerpo → 422 (caso C-16).
- Una línea de `historial_precio_repuesto` por cambio efectivo de precio y ninguna cuando el precio no cambia (RN-20, caso C-18).
- Baja lógica: 204, después 404, y el `codigo` queda libre por el índice parcial.
- Historiales paginados con el envoltorio uniforme, ordenados por `cuando` e `id`, y 404 si el repuesto no existe.

**Non-Goals:**

- Descontar stock al terminar una orden: es `C-11` (RN-13) y reutiliza el mismo punto único de escritura.
- Precarga de los historiales dentro del detalle del repuesto: no se pide y sería una relación más en una lectura que hoy no la usa.
- Reabrir un repuesto dado de baja o editar el `codigo`: fuera del alcance del TP.
- Roles distintos de ADMIN en las rutas del ABM: la matriz de `03_actores_y_roles.md` no los admite.

## Decisions

### D1 — `stock_inicial` es una instrucción, no una columna

**Decisión**: `RepuestoCrear` declara `stock_inicial: int = 0` (`ge=0`) y **no** `stock`. `crear` construye el `Repuesto` con `stock=datos.stock_inicial` y, si es mayor que cero, agrega un `MovimientoStock(cantidad=stock_inicial, motivo="Stock inicial", usuario_id=usuario_actual)` en el mismo `async with uow`.

**Por qué**: el modelo tiene una columna `stock` y un contrato que la aceptara dejaría la puerta abierta a nacer con cualquier stock sin movimiento que lo explique. Con `stock_inicial` el cliente dice **cuánto entra** y el servicio escribe las dos filas coherentes. `stock` sigue prohibido y el mensaje de 422 nombra el campo, así el caso C-16 se verifica también en el alta.

**Consecuencia**: el alta con `stock_inicial = 0` no escribe movimiento (una entrada de cero no existe: CHECK `cantidad <> 0`) y el repuesto nace con stock 0, exactamente como en `C-06`.

**Alternativa descartada**: declarar `stock` en el alta y generar el movimiento sólo si es mayor que cero. El cliente podría mandar un `stock` que no coincide con ningún movimiento y el contrato dejaría de distinguir «stock inicial» de «stock editable».

### D2 — El PATCH aplica `exclude_unset` y no toca el stock

**Decisión**: `actualizar` toma `cambios_enviados(datos)` (que es `model_dump(exclude_unset=True, exclude_none=True)`) y escribe en el ORM sólo las claves presentes. `stock` no está declarado en `RepuestoPatch`: el `extra="forbid"` de `ContratoEntrada` lo rechaza con 422 **antes** de llegar al handler.

**Por qué**: es la convención de PATCH que fijó `C-06` (`exclude_unset`). Un cuerpo `{}` es válido y no cambia nada (200); un `null` explícito se ignora (`exclude_none`) en vez de intentar escribir `NULL` en una columna NOT NULL (sería un 500). El 422 del stock no necesita código nuevo: el contrato lo garantiza y el handler central lo formatea con la lista de campos.

**Consecuencia**: no existe ninguna ruta que acepte `stock` en el cuerpo. El único otro camino es `POST /{id}/reponer`.

### D3 — Historial de precio: una línea por cambio efectivo, comparando en el servicio (RN-20)

**Decisión**: dentro del mismo `async with uow`, `actualizar` compara `precio_nuevo != repuesto.precio`. Si difieren, guarda `precio_anterior` **antes** de pisar el atributo e inserta `HistorialPrecioRepuesto(repuesto_id, usuario_id, precio_anterior, precio_nuevo)`. Si son iguales, no inserta nada y responde 200 con el precio actual.

**Por qué**: RN-20 pide la línea **en la misma transacción** y un PATCH sin cambio **no** deja línea (caso C-18). Se compara en el servicio y no con un `WHERE` condicional porque la decisión depende del valor actual que ya se leyó para el 404 y para el `precio_anterior`; además el CHECK `precio_nuevo <> precio_anterior` rechazaría la fila igual, pero sería un 409 por integridad en una operación que no debía fallar.

**Por qué `Decimal`**: `precio` llega como `Decimal` del contrato y del motor. La comparación es numérica (`Decimal("9000.0") == Decimal("9000.00")`), así que un formato distinto con el mismo valor tampoco deja línea. Nunca se convierte a `float`.

**Orden**: insertar la línea y actualizar el repuesto comparten el UoW; si cualquiera falla, el `__aexit__` revierte todo y no queda ni el cambio ni la línea.

**Alternativa descartada**: usar el resultado del `UPDATE` o un `RETURNING` para decidir si hubo cambio. No aporta nada sobre un valor que ya está en memoria y complica el mapeo ORM → contrato.

### D4 — La reposición es el único incremento manual del stock (RN-14)

**Decisión**: `reponer` lee el repuesto (404 si no existe), suma `cantidad` al `stock`, hace `update` y agrega `MovimientoStock(cantidad=positiva, motivo="Reposición", usuario_id)`. Todo dentro del mismo UoW. La respuesta es el repuesto actualizado (200).

**Por qué**: RN-14 dice que el stock sólo cambia por movimientos. El servicio es el punto único: el PATCH no lo expone y el alta sólo lo usa para nacer con `stock_inicial`. Dejar el incremento en el router o en un endpoint que acepte `stock` absoluto volvería a abrir el atajo que la regla prohíbe.

**Por qué `cantidad > 0` en el contrato**: una reposición es una entrada. La salida la produce `C-11` al terminar una orden, con su propio movimiento negativo. Permitir negativos acá duplicaría la responsabilidad y haría que una «reposición negativa» pudiera vaciar el stock sin pasar por la regla de la orden.

**Consecuencia**: el CHECK `stock >= 0` de la base sigue siendo la última defensa; el servicio no necesita comprobarlo porque sólo suma.

### D5 — Baja lógica con `soft_delete` y código reutilizable

**Decisión**: `eliminar` llama a `SoftDeleteRepository.soft_delete`, que escribe `borrado_en = now(UTC)` y hace `flush()`. Si el repuesto no existe o ya estaba dado de baja devuelve `None` y el servicio responde 404. La ruta devuelve `204` con `Response` vacío.

**Por qué**: RN-16 y US-021 CA-3. El `DELETE` HTTP no borra la fila: los movimientos y el historial de precios siguen apuntando a un repuesto que existe (las FK son `RESTRICT` y las tablas de auditoría son de sólo agregado). El índice único parcial `(codigo) WHERE borrado_en IS NULL` es lo que permite volver a usar el código: **no** se consulta antes, se deja que la base lo garantice.

**Consecuencia**: un repuesto dado de baja desaparece del listado y del detalle (404), pero sus movimientos y precios se conservan y su código se puede reutilizar en un alta nueva.

### D6 — Los historiales se leen paginados, con orden determinista y 404 previo

**Decisión**: `listar_movimientos` y `listar_precios` abren el UoW, verifican que el repuesto exista (`get_by_id`, que ya excluye las bajas) y recién entonces llaman a `list_page` del repositorio correspondiente. El orden es `(cuando, id)` y el envoltorio es el de `paginacion.py`.

**Por qué**: US-022 CA-2 pide 200/404 y el resto de los listados de la API ya usa el envoltorio uniforme; devolver arrays sueltos rompería esa convención y la paginación fuera de rango (422). El orden por `cuando` e `id` evita que dos páginas consecutivas repitan u omiten una fila cuando dos movimientos comparten el instante (pasa en el seed y en los tests).

**Por qué verificar el repuesto primero**: un repuesto inexistente con historial vacío no es «200 con 0 items», es 404. El `get_by_id` del `SoftDeleteRepository` ya resuelve el caso de la baja lógica sin consultas extra.

**Por qué `BaseRepository` y no `SoftDeleteRepository`**: las dos tablas de auditoría no tienen `borrado_en` y nunca se dan de baja (RN-15). Heredar el borrado lógico sería una mentira en el tipo.

### D7 — Sin migraciones y sin tocar `main.py`

**Decisión**: el change no crea migraciones ni modifica `main.py`. `repuestos_router` ya está incluido en `grupo_protegido`, así que las cinco rutas nuevas heredan el 401 de la sesión y el 403 del cambio obligatorio sin declararlos.

**Por qué**: el esquema de `C-04` ya tiene las tres tablas, sus CHECK, el índice parcial y el disparador de sólo agregado. Tocar `main.py` habría sido redundante y arriesgado con `C-09` corriendo en paralelo sobre el mismo archivo.

**Verificación**: `openspec validate` y la suite no detectan rutas nuevas fuera del grupo. El test de 401 sin sesión y el de 403 con RECEPCION/MECANICO cubren las seis rutas ADMIN, incluida la que ya existía.

## Risks / Trade-offs

- **El movimiento y el repuesto se escriben en la misma transacción** → si la inserción del movimiento fallara (p. ej. `usuario_id` inexistente), se revierte el alta completa; es el comportamiento correcto y no queda un repuesto con stock sin explicación. No se agrega un `try` local: el UoW revierte y el handler central traduce.
- **Un `PATCH` con el mismo precio responde 200 sin línea** → es lo que pide RN-20. Un cliente que quiera «forzar» una línea no puede; el historial sólo refleja cambios reales, que es justamente su valor probatorio.
- **La reposición no limita el stock máximo** → no hay regla de negocio que lo pida y el esquema no tiene un techo. El CHECK sólo impide negativos.
- **El historial de precios no registra el motivo del cambio** → la tabla no tiene esa columna y agregarla sería una migración fuera de alcance. El usuario y el instante quedan, que es lo que pide RN-20.
- **Un repuesto dado de baja no se puede editar** → 404, coherente con «deja de aparecer». Reabrirlo está fuera del TP.
- **La comparación de precios es exacta con `Decimal`** → un cliente que mande `9000.000` con tres decimales recibe 422 del contrato (`decimal_places=2`), no una línea con redondeo.

## Migration Plan

1. Extender `app/modules/repuestos/schemas.py`: `stock_inicial`, `ReponerStock`, `MovimientoStockLeer` e `HistorialPrecioLeer`.
2. Agregar `MovimientoStockRepository` e `HistorialPrecioRepository` a `repository.py`.
3. Exponer `movimientos` e `historial_precios` en `RepuestosUnitOfWork`.
4. Implementar `crear` con movimiento, `actualizar`, `eliminar`, `reponer`, `listar_movimientos` y `listar_precios` en `service.py`.
5. Agregar las cinco rutas a `router.py` con `AdminDep`.
6. Escribir `test/repuestos.http` y `test/test_repuestos.py` (TDD: primero fallaron 36 de 46).
7. Correr `python -m pytest test/ -q` y `openspec validate 2026-10-27-c-10-repuestos-stock --strict`.

**Rollback**: no hay migraciones. Revertir `router.py` a las tres rutas de `C-06`, quitar los métodos nuevos de `service.py`/`repository.py`/`unit_of_work.py` y `stock_inicial` de `RepuestoCrear`; la base queda idéntica. Los movimientos y líneas de precio que se hayan escrito son de sólo agregado y no se pueden borrar (RN-15), pero no bloquean nada: el código vuelve a su estado de `C-08`.

## UI Mockups

Decision: no (no UI). Es una API sin frontend; no aplica el gate de mockups.
