# Design

Ver `proposal.md` (Why) y las specs `customer-management`, `vehicle-lifecycle` y `own-resources` (requisitos). Este documento explica **cómo** se cumple ese contrato.

## Context

Al empezar este change, `C-08` dejó la autorización resuelta: `main.py` monta un grupo abierto (`/health`, `/auth`) y uno protegido con `exigir_password_al_dia` una sola vez; `requiere_rol` consulta `asignacion_rol` en cada petición y los alias `AdminDep`/`PersonalDep` cubren las rutas de personal. El módulo `clientes` sólo tiene `models.py` (las tablas `cliente` y `vehiculo`, sin cambios desde `C-03`) y un `ClienteRepository` mínimo que usa el auto-registro de `C-07` para crear la ficha en el mismo UoW que el usuario y su rol. No hay contratos, servicio, UoW ni router: las cinco rutas de la Épica 6 no existen.

Restricciones que condicionan el diseño:

- **Sin migración ni cambio de esquema**: `cliente.usuario_id` (UNIQUE, nulo), `cliente.documento` (UNIQUE), el índice único parcial `uq_vehiculo_patente_vigente (patente) WHERE borrado_en IS NULL` y el CHECK `ck_vehiculo_anio_rango (1950–2100)` ya existen. Si faltara una columna, el change se detendría y lo reportaría.
- **Reglas duras de `AGENTS.md`**: unicidad por la base (nunca consulta previa), sin carga perezosa (`lazy="raise_on_sql"`), `select` importado de SQLModel, `flush()` en repositorios y `commit()` sólo en el UoW, el servicio no construye el UoW, `app/models.py` como registro central, fechas `timestamptz`.
- **Stack cerrado**: FastAPI + SQLModel + SQLAlchemy async + PostgreSQL. Sin dependencias nuevas.
- **Concurrencia del roadmap**: `C-10` implementa `repuestos` en paralelo. Este change **no toca** `app/modules/repuestos/` ni sus tests; de `main.py` sólo agrega tres `include_router` al grupo protegido.

## Goals / Non-Goals

**Goals:**

- `POST /clientes` (ADMIN/RECEPCION): 201/409/422 con el documento único garantizado por la base (RN-01).
- `GET /clientes/{id}` (ADMIN/RECEPCION): ficha **con sus vehículos vigentes** por carga anticipada en el repositorio, sin carga perezosa.
- `POST /clientes/{id}/vehiculos` (ADMIN/RECEPCION): 201/404/409/422; patente única entre vigentes y `anio` 1950–2100.
- `DELETE /vehiculos/{id}` (ADMIN/RECEPCION): 204 con baja lógica (`borrado_en`); 409 si el vehículo tiene órdenes abiertas (`es_final = false`).
- `GET /mis-vehiculos` (cualquier sesión): sólo los vehículos del cliente dueño de la sesión (RN-17); lista vacía si la cuenta no tiene ficha.
- Caso **C-19**: después de la baja, la misma patente se puede volver a registrar; mientras haya una vigente igual, el alta es 409.
- `SoftDeleteRepository` en uso para `Vehiculo` y evidencia `.http` + suite automatizada.

**Non-Goals:**

- Edición (PATCH) de clientes y vehículos: no está en la Épica 6. El ABM completo de clientes no lo pide la consigna.
- Enlazar una cuenta a una ficha desde la API (`cliente.usuario_id`): lo hace el auto-registro de `C-07`. `usuario_id` no se declara en los contratos de entrada.
- Alta de órdenes y verificación del vehículo dado de baja en una orden nueva → `C-11` (RN-16 lo exige, pero la ruta de órdenes no existe todavía).
- Conteo de consultas y verificación formal de N+1 (`SQL_ECHO`) → `C-12`. Acá la precarga se implementa con dos consultas fijas, pero la medición es de `C-12`.
- Listado paginado de clientes: no está en la Épica 6.

## Decisions

### D1 — Precarga con `selectinload` + criterio de vigencia, en el repositorio

**Decisión**: la ficha y `/mis-vehiculos` se leen con

```python
select(Cliente).options(
    selectinload(Cliente.vehiculos.and_(Vehiculo.borrado_en.is_(None)))
)
```

El repositorio devuelve el `Cliente` con `vehiculos` ya cargados; el servicio y el router sólo leen la colección.

**Por qué**: las relaciones declaran `lazy="raise_on_sql"`: un acceso perezoso lanza una excepción en vez de disparar SQL escondido (regla dura y requisito no funcional). `selectinload` con un criterio `and_()` resuelve la colección con **una** consulta extra fija, y ese criterio es el que aplica RN-16 («un vehículo dado de baja deja de aparecer») sin filtrar en Python. Traer todos los vehículos y descartar los borrados en memoria obligaría a cargar filas que la API no muestra y dejaría la regla en el servicio.

**Alternativa descartada**: `joinedload`. Con una colección y un `get` por id funcionaría, pero `selectinload` es el mismo patrón que usará `C-12` para las colecciones del detalle y no duplica la fila del cliente.

**Consecuencia**: la ficha hace **dos** consultas (cliente + vehículos), independientemente de cuántos vehículos tenga; `/mis-vehiculos` también dos (o una si no hay ficha, porque no hay colección que cargar).

### D2 — Dos contratos de salida: `ClienteLeer` (plana) y `ClienteFicha` (con vehículos)

**Decisión**: el alta responde `ClienteLeer` (`id`, `nombre`, `documento`, `telefono`) y la ficha responde `ClienteFicha`, que agrega `vehiculos: list[VehiculoLeer]`.

**Por qué**: la entidad recién creada por el alta **no tiene la colección cargada**. Un contrato con `vehiculos` obligaría a Pydantic a leer el atributo y dispararía `raise_on_sql` (un 500 en un alta exitosa) o a una consulta extra que la operación no necesita. Separar los contratos deja explícito qué devuelve cada ruta y evita el acceso perezoso por accidente.

**Consecuencia**: el test del alta verifica que la respuesta **no** trae `vehiculos`; el de la ficha verifica que sí.

### D3 — Unicidad por el índice, sin consulta previa (RN-01 / caso C-19)

**Decisión**: ni el servicio ni el repositorio consultan si el documento o la patente ya existen. El alta inserta; si la base rechaza, el `IntegrityError` sube y el handler central de `C-06` responde **409** con mensaje propio. El índice de patente es **parcial** (`WHERE borrado_en IS NULL`), así que una patente dada de baja no ocupa el lugar.

**Por qué**: la regla dura prohíbe verificar unicidad con una consulta previa y el caso C-19 exige que la patente se reutilice tras la baja. Una consulta `WHERE patente = :p` sin el filtro de vigencia rechazaría el alta legítima; con el filtro sería una carrera (dos altas simultáneas pueden pasar el `SELECT` y chocar en el `INSERT`). La base es la única garantía real y el 409 sale con el mismo mensaje uniforme, sin nombre de índice ni texto del motor (RN-18).

**Consecuencia**: el test de patente repetida **vigente** y el de documento repetido esperan 409; el de patente repetida **tras la baja** espera 201.

### D4 — El año se valida en el contrato (422), no en la base

**Decisión**: `VehiculoCrear.anio` es `Annotated[int, Field(ge=1950, le=2100)]`, calcado del CHECK.

**Por qué**: una violación de CHECK en PostgreSQL llega a SQLAlchemy como `IntegrityError`, y el handler central la traduce a **409**. El contrato de la Épica 6 pide **422** para un año fuera de rango: es un cuerpo inválido, no un conflicto con datos guardados. Validarlo en Pydantic da 422 con la lista de campos, sin depender del mensaje del motor.

**Consecuencia**: 1949 y 2101 → 422; 1950 y 2100 → válidos, en los dos extremos.

### D5 — Baja lógica: `soft_delete` y la comprobación de órdenes abiertas en el repositorio

**Decisión**: `VehiculoRepository` hereda `SoftDeleteRepository`. `dar_de_baja_vehiculo` lee el vehículo vigente (404 si no existe), pregunta `tiene_ordenes_abiertas(vehiculo_id)` y, sólo si es falso, llama `soft_delete`. La consulta es un `SELECT orden_trabajo.id ... JOIN estado_orden ... WHERE vehiculo_id = :id AND es_final = false LIMIT 1` **en el repositorio**.

**Por qué**: RN-16 define «orden abierta» por el catálogo (`es_final`), no por una lista de estados en el código: si mañana se agrega un estado no final, la consulta lo cubre sin cambios. La baja escribe `borrado_en` y no borra la fila, porque las órdenes viejas siguen apuntando al vehículo (`FK ON DELETE RESTRICT`) y el comprador nuevo necesita que la patente se libere. Ubicar el `SELECT` en el repositorio respeta las capas: el servicio decide **qué** significa el resultado (409); el repositorio sólo sabe consultar. El servicio no importa lógica de `ordenes`.

**Orden de las comprobaciones**: primero 404 (¿existe el vehículo vigente?), después 409 (¿tiene órdenes abiertas?), después la escritura. Si se escribiera antes de comprobar, una baja rechazada dejaría la fila marcada.

**Límite aceptado**: entre el `SELECT` y el `UPDATE` de `borrado_en` no hay bloqueo. Una orden creada en paralelo sobre ese vehículo en esa ventana no se detectaría; se acepta porque exigiría `SELECT ... FOR UPDATE` sobre el catálogo o un aislamiento mayor, desproporcionado para el TP. Se documenta para que no parezca un olvido.

### D6 — `/mis-vehiculos` por `Cliente.usuario_id`, con lista vacía si no hay ficha (RN-17)

**Decisión**: el servicio busca la ficha con `ClienteRepository.get_by_usuario_id(usuario_actual.id)`. Si devuelve `None`, responde `[]` (200). La ruta usa `UsuarioActualDep` y **no** `requiere_rol`.

**Por qué**: RN-17 dice que lo propio **sólo pide estar autenticado**. Un mecánico o un admin no son «dueños» de nada: no es un 403, es una lista vacía; y un 404 diría que falta un recurso que nadie pidió por id. La identidad del cliente se resuelve por `cliente.usuario_id` (UNIQUE), que es la única relación entre la cuenta y la cartera.

**Consecuencia**: el test verifica que Laura ve los vehículos 1 y 2 y **no** el 3 (de Jorge), y que recepción y admin reciben `[]` con 200.

### D7 — Tres routers en el módulo porque los prefijos no coinciden

**Decisión**: `router` (`/clientes`), `vehiculos_router` (`/vehiculos`) y `propios_router` (`/mis-vehiculos`), los tres montados en el grupo protegido de `main.py`. Es el mismo patrón que `eventos_router` en `usuarios` (`C-08`).

**Por qué**: `DELETE /vehiculos/{id}` no comparte el prefijo `/clientes` (la matriz de la KB lo declara así) y `/mis-vehiculos` tampoco; meterlos con `prefix="/clientes"` inventaría rutas que la consigna no pide. Separar los routers deja la matriz de permisos legible ruta por ruta y permite que `main.py` los monte todos en el grupo protegido sin excepciones.

### D8 — Roles: alias local `AtencionDep` (ADMIN, RECEPCION), sin tocar `app/core/dependencies.py`

**Decisión**: el router del módulo define `AtencionDep = Depends(requiere_rol("ADMIN", "RECEPCION"))`. No se agrega un alias nuevo a `app/core/dependencies.py`.

**Por qué**: `PersonalDep` incluye MECANICO y estas rutas no lo admiten; `AdminDep` deja afuera a RECEPCION, que es el actor principal de la Épica 6. El alias es una necesidad local de este módulo y, al declararlo acá, `C-10` (que corre en paralelo y sí usa los alias de personal) no compite por el mismo archivo compartido. Si un tercer módulo necesitara la misma combinación, se promovería a `app/core/dependencies.py` con su test.

## Risks / Trade-offs

- **La colección de vehículos no se pagina** → un cliente con muchos vehículos devuelve todos en la ficha. La Épica 6 no pide paginarla y el volumen por cliente es bajo; si creciera, se agregaría un listado paginado sin cambiar la ficha.
- **La comprobación de órdenes abiertas no bloquea filas** → ventana de carrera documentada en D5. La alternativa (`FOR UPDATE`) no está justificada para el TP.
- **La patente se compara tal cual llega** (sensible a mayúsculas) → `aaa111` y `AAA111` serían patentes distintas. La consigna no pide normalizar y el seed usa mayúsculas; normalizar en el contrato sería una decisión de producto que este change no toma.
- **`usuario_id` no se puede enlazar desde la API** → una ficha creada por recepción queda sin cuenta para siempre (el auto-registro de `C-07` crea su propia ficha). Es coherente con RN-02 y con la Épica 6; enlazar cuentas sería otra historia de usuario.
- **El alta responde una ficha plana** → el cliente de la API necesita un `GET` para ver los vehículos. Evita el acceso perezoso de D2; es una decisión de contrato, no una limitación técnica.
- **Un vehículo con órdenes sólo puede darse de baja cuando todas son finales** → es la lectura literal de RN-16; una orden CANCELADA o TERMINADA no bloquea.

## Migration Plan

1. Crear `app/modules/clientes/schemas.py` con los cinco contratos.
2. Extender `app/modules/clientes/repository.py`: `get_ficha`, `get_by_usuario_id` y `VehiculoRepository` con `tiene_ordenes_abiertas`.
3. Crear `app/modules/clientes/unit_of_work.py` con `ClientesUnitOfWork`.
4. Implementar `app/modules/clientes/service.py` (cinco operaciones) y `app/modules/clientes/router.py` (tres routers).
5. Montar los tres routers en el grupo protegido de `main.py` (cambio aditivo).
6. Escribir `test/clientes.http` y `test/test_clientes.py`; correr la suite con la base aislada `taller_mecanico_c09`.
7. `openspec validate 2026-10-27-c-09-clientes-vehiculos --strict`.

**Rollback**: no hay migraciones. Quitar los tres `include_router` de `main.py` y borrar los cinco archivos nuevos del módulo (`schemas`, `unit_of_work`, `service`, `router`) junto con los métodos y la clase agregados a `repository.py`; la API vuelve al estado de `C-08`. La base no cambia: `cliente` y `vehiculo` ya existían con sus índices y CHECK.

## UI Mockups

Decision: no (no UI). Es una API sin frontend; no aplica el gate de mockups.
