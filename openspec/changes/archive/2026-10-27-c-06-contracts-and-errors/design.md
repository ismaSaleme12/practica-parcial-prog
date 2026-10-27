# Design

Ver `proposal.md` (Why) y las specs `request-contracts`, `error-handling` y `list-pagination-stub` (requisitos). Este documento explica **cómo** se cumple ese contrato.

## Context

Al empezar este change la app sólo monta `health`: no hay un solo contrato Pydantic, ningún router de dominio y ninguna traducción de errores. `C-02` dejó listas las piezas transversales (repositorios que sólo hacen `flush`, `UnitOfWork` como único punto de confirmación, `Page`/`PageParams` y las primitivas de seguridad), y `C-04` dejó las trece tablas migradas y el seed cargado.

Restricciones que condicionan el diseño:

- Stack cerrado: FastAPI + SQLModel + SQLAlchemy async. **No** se agrega `email-validator`, `pydantic[email]` ni ninguna librería de validación extra.
- `AGENTS.md`: `Decimal` (nunca `float`) y dinero como **string** en la respuesta; ninguna respuesta con `password_hash`; ningún texto crudo de `IntegrityError`; SQL siempre parametrizado; ninguna entrada inválida termina en 500.
- Sin autenticación todavía (`C-07`/`C-08`): los endpoints de este change son **prototipos** y no exigen rol.
- El historial de precio (`RN-20`) y el movimiento de stock inicial (`RN-14`) exigen un `usuario_id` que todavía no existe en una petición: por eso el ABM completo queda para `C-10`.

## Goals / Non-Goals

**Goals:**
- Que todo contrato de entrada rechace campos no declarados y que toda respuesta de `usuario` esté libre de `password_hash`.
- Que el dinero viaje como string Decimal en las respuestas y nunca como número ni `float`.
- Que una contraseña de más de 72 bytes dé **422** y nunca llegue a bcrypt.
- Que un `IntegrityError` dé **409 con mensaje propio**, sin filtrar el esquema.
- Que un listado real use el envoltorio de paginación, la búsqueda `q` parametrizada y el 422 de página fuera de rango.

**Non-Goals:**
- Endpoints de auth, cookie, `requiere_rol` y hash ficticio → `C-07`/`C-08`.
- ABM completo de repuestos (`stock_inicial`, historial de precio, baja lógica, `reponer`) → `C-10`.
- Autorización de `POST /usuarios` (ADMIN) y asignación de rol → `C-08`.
- Suite de tests completa → `C-05` (infra) y `C-13` (consolidación).

## Decisions

### D1 — El manejo de errores vive en `app/core/errors.py`, registrado una sola vez

**Decisión**: un módulo `app/core/errors.py` con los handlers y una función `registrar_manejadores(app)` que `main.py` invoca al construir la app. Los servicios **no** atrapan `IntegrityError`: lo dejan subir y el handler de aplicación lo traduce.

**Por qué**: RN-18 es una regla transversal; si cada servicio escribiera su `try/except IntegrityError` habría un mensaje distinto por endpoint y alguno se olvidaría. Un handler de aplicación cubre también los `commit()` del `UnitOfWork` (restricciones diferidas) y los casos que el servicio no anticipó. El `UnitOfWork` ya revierte la transacción al salir con excepción, así que cuando el handler responde 409 la sesión quedó limpia.

**Alternativas descartadas**: (a) middleware propio — más código y duplicated para distinguir tipos; (b) `try/except` por endpoint — repetitivo y fácil de olvidar.

### D2 — `IntegrityError` → 409 con mensaje propio, sin inspeccionar el texto del motor

**Decisión**: el handler responde `409` con un mensaje fijo y propio («La operación entra en conflicto con datos ya guardados.»). No se lee `exc.orig` ni el texto de la excepción. Cuando el servicio **conoce** la regla (por ejemplo, autoprotección de `C-08`), lanza `Conflicto("mensaje específico")` antes de tocar la base.

**Por qué**: el texto de PostgreSQL está en el idioma configurado del servidor, cambia entre versiones y contiene nombres de tablas, columnas y valores — exactamente el mapa del esquema que RN-18 prohíbe. Discriminar por `pgcode` para armar un mensaje distinto agregaría acoplamiento al motor sin que la consigna lo pida; la unicidad la garantiza la base (índice), no una consulta previa, y el 409 genérico ya es el código correcto.

**Consecuencia aceptada**: dos violaciones distintas (código repetido, email repetido) comparten el mismo mensaje. El cliente distingue por el campo que envió, y los errores de negocio con mensaje específico se lanzan desde el servicio con `Conflicto`.

### D3 — El dinero es `Decimal` en Python y **string** en JSON

**Decisión**: `app/core/schemas.py` define `Dinero = Annotated[Decimal, PlainSerializer(..., return_type=str, when_used="json")]`. El serializador formatea con dos decimales (`f"{valor:.2f}"`). La entrada usa `Decimal` con `gt=0`, `max_digits=10` y `decimal_places=2` (calca `NUMERIC(10,2)`).

**Por qué**: la regla dura prohíbe `float` para dinero. Pydantic v2 convierte el literal JSON directamente a `Decimal` (sin pasar por `float`), y con `PlainSerializer` el contrato de salida declara `string` en el OpenAPI. Formatear a dos decimales en el borde hace que el contrato no dependa de cómo llegó el valor (`"8500"`, `8500`, `8500.0` → `"8500.00"`).

**Alternativas descartadas**: `str` en el modelo de salida y conversión manual en el router (se olvida en el próximo módulo); `float` (prohibido por `AGENTS.md`).

### D4 — Contraseña ≤ 72 **bytes**, validada en el contrato

**Decisión**: `UsuarioCrear.password` valida `len(valor.encode("utf-8")) > 72` → `ValueError` de Pydantic, que el handler de validación traduce a 422 con el campo identificado. No se valida por caracteres.

**Por qué**: bcrypt ≥ 5 rechaza entradas de más de 72 **bytes** con excepción; sin el límite en el contrato la petición terminaría en 500. Es bytes y no caracteres: 37 «ñ» son 74 bytes y 37 caracteres. El límite vive en el contrato (no en `hash_password`) porque la primitiva de `C-02` documenta esa precondición y debe seguir siendo reutilizable.

**Consecuencia**: 72 bytes exactos se aceptan; 73 se rechazan. Queda cubierto por dos tests (borde y multibyte).

### D5 — Contratos separados de los modelos, con una base común

**Decisión**: `ContratoEntrada` (`extra="forbid"`, `str_strip_whitespace=True`) y `ContratoSalida` (`from_attributes=True`) en `app/core/schemas.py`. Cada módulo declara sus propios schemas y **nunca** expone el modelo de tabla. Los campos de texto llevan `max_length` igual al `VARCHAR` de la base (email 320, nombre 120, código 40, descripción 200) para que un texto demasiado largo sea 422 y no un `DataError`.

**Por qué**: US-007 CA-1 y CA-2. `extra="forbid"` es lo que impide registrarse con `rol`, editar el `stock` por PATCH o inyectar `precio`/`total` en una orden. `UsuarioLeer` declara sólo id, email, nombre, activo y `debe_cambiar_password`: `password_hash` no existe en el contrato de salida (y `response_model` lo garantiza aunque alguien devuelva el ORM).

**Nota sobre `app/core/schemas.py`**: la estructura obligatoria de la KB enumera siete archivos en `app/core/`. Este change agrega `errors.py` (pedido por el roadmap) y `schemas.py` (piezas de contrato compartidas por dos módulos). Se prefiere un archivo chico y compartido antes que duplicar `Dinero`/`extra="forbid"` en cada módulo y que las copias se desincronicen.

### D6 — `exclude_unset` es una convención con helper, no un endpoint todavía

**Decisión**: `cambios_enviados(contrato)` devuelve `model_dump(exclude_unset=True, exclude_none=True)`, y `RepuestoPatch` declara sólo `descripcion` y `precio` (con `extra="forbid"`, así que `stock` es 422). **No** se publica `PATCH /repuestos/{id}` en este change.

**Por qué**: el PATCH real de repuestos exige, en la misma transacción, una línea en `historial_precio_repuesto` (RN-20) y esa tabla tiene `usuario_id` NOT NULL; sin autenticación (`C-07`/`C-08`) no hay actor que anotar. Publicar el PATCH sin historial sería violar RN-20; inventar un actor sería peor. La convención queda fijada en el helper y el contrato, y `C-10` los usa cuando ya existe el usuario actual. `exclude_none=True` evita que un `{"descripcion": null}` explícito intente escribir `NULL` en una columna NOT NULL (sería un 500).

**Alternativa descartada**: PATCH que sólo permita `descripcion` — deja el caso de dinero sin cubrir y `C-10` igual tiene que reescribirlo.

### D7 — `q` con parámetros ligados

**Decisión**: `RepuestoRepository.filtro_busqueda(q)` devuelve `Repuesto.descripcion.ilike(f"%{texto}%")`, que SQLAlchemy compila a `descripcion ILIKE $1` con el patrón como parámetro. Sin `text()`, sin `f"..."` dentro del SQL y sin `%` interpolado en la sentencia.

**Por qué**: US-008 CA-5 y caso C-16. Un `q` con `' OR '1'='1` viaja como **valor** del parámetro y no cambia la forma de la consulta: devuelve lista vacía con `total: 0`. Se buscan coincidencias parciales en la descripción (no se escapan `%`/`_`: son comodines de búsqueda, no sintaxis SQL).

### D8 — Endpoints de prototipo, montados en abierto hasta `C-08`

**Decisión**: `main.py` monta `usuarios_router` y `repuestos_router` y registra los manejadores. Ninguno exige autenticación todavía; el comentario del `main.py` y la tarea 6.2 lo declaran.

**Por qué**: `C-07` no existe aún y sin endpoints no hay forma de demostrar los contratos ni la evidencia `.http`. `C-08` es el change que crea los dos grupos de rutas (DD-05) y mueve estos routers al protegido con `requiere_rol`.

**Riesgo asumido y declarado**: mientras `C-07`/`C-08` no estén archivados, `POST /usuarios` y `POST /repuestos` son públicos. Es un estado transitorio de un proyecto de práctica sin datos reales; queda anotado como bloqueante de la fase 4 en `tasks.md`.

### D9 — `POST /repuestos` crea con `stock = 0`

**Decisión**: el contrato de alta declara `codigo`, `descripcion` y `precio`; **no** declara `stock` ni `stock_inicial`. El repuesto nace con stock 0.

**Por qué**: RN-14 dice que el stock sólo cambia por movimientos, y `movimiento_stock.usuario_id` es NOT NULL. Sin actor no se puede dejar el movimiento «Stock inicial»; crear stock sin movimiento rompería la invariante que el seed mantiene. `C-10` agrega `stock_inicial` + movimiento en el mismo UoW cuando ya hay usuario actual. Mientras tanto, enviar `stock` o `stock_inicial` es 422 (`extra="forbid"`), que es justamente el espíritu del caso C-16.

### D10 — El 422 de validación tiene mensaje propio y lista de campos

**Decisión**: el handler de `RequestValidationError` responde `422` con `{"detail": "La petición no cumple el contrato.", "errores": [{"campo", "mensaje", "tipo"}]}`. Los 422 que lanza la paginación (`PageParams`/`Page.create`) conservan su `{"detail": "<mensaje propio>"}`.

**Por qué**: se reemplaza el `detail` por defecto de FastAPI (que mezcla `input` y `url` y no da un mensaje legible) por uno estable y propio, sin exponer rutas internas del código. No se incluye `ctx` (puede traer objetos no serializables). Los dos formatos conviven porque ambos son 422 y el cliente mira `detail` primero.

### D11 — `list_page` ordena de forma determinista cuando el repositorio lo declara

**Decisión**: `BaseRepository` expone `_orden_por: tuple[...] = ()` y `list_page` aplica `order_by(*_orden_por)` cuando no está vacía. `RepuestoRepository` declara `(Repuesto.id,)`.

**Por qué**: sin `ORDER BY`, PostgreSQL puede devolver las filas en cualquier orden (y cambiar de orden tras un `UPDATE`), con lo que dos páginas consecutivas podrían repetir u omitir filas. La consigna pide paginar «sin sorpresas». La tupla vacía por defecto deja el comportamiento de `C-02` intacto para los repositorios que no la declaren. El orden por `id` coincide con el ejemplo de listado de la KB (`FA-001`, `PF-002`).

## Risks / Trade-offs

- **Handler global de `IntegrityError`** → cualquier violación (UNIQUE, CHECK, FK) responde 409, incluso una que semánticamente fuera 422. Se acepta: la consigna pide 409 para choques con lo guardado y el contrato de entrada ya filtra el resto. El caso C-13 podrá endurecerlo por regla.
- **`DataError` → 422** (defensa en profundidad por textos más largos que el `VARCHAR`) → si un bug de código enviara un tipo inválido, el cliente vería 422 en vez de 500. Es preferible a filtrar el error del motor.
- **Fecha/hora y `Decimal` en el handler** → el handler no toca la base ni serializa objetos: sólo strings, así que no puede fallar por un `Decimal`.
- **Endpoints públicos hasta `C-08`** → declarado en D8 y en `tasks.md` (bloqueante de la fase 4).
- **`app/core/schemas.py` como octavo archivo de `core/`** → se documenta en D5; la alternativa (duplicar el tipo `Dinero` en cada módulo) es peor a mediano plazo.
- **`POST /usuarios` crea el usuario sin rol** → `C-08` asigna el rol y registra el evento de seguridad. No afecta a este change porque no hay autorización todavía; el seed sigue siendo la fuente de usuarios con rol.
- **`Page[Repuesto]` no valida contra `Page[RepuestoLeer]`** → el router construye el `Page[RepuestoLeer]` mapeando cada fila con `RepuestoLeer.model_validate(...)`. El mapeo ORM → contrato queda explícito y visible.

## Migration Plan

1. Crear `app/core/schemas.py` y `app/core/errors.py`.
2. Crear los schemas de `usuarios` y `repuestos`.
3. Crear repositorio, UoW, servicio y router de cada módulo.
4. Registrar manejadores y montar routers en `main.py`.
5. Escribir `test/contracts.http` y `test/test_contracts.py`.
6. Verificar contra una base migrada y sembrada (script temporal fuera del repo).

Rollback: no hay migraciones; borrar los archivos nuevos y revertir `main.py` deja el repo en el estado de `C-04`. La base no se toca (las filas de prueba se crean en la base de verificación).
