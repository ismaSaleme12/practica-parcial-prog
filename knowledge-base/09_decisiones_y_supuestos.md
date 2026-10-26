# Decisiones y Supuestos

## Decisiones documentadas

### DD-01 — Catálogo `estado_orden` en lugar de un CHECK
**Decisión**: los estados de una orden son filas de una tabla de referencia con clave primaria `codigo`, apuntada por clave foránea desde `orden_trabajo.estado` e `historial_estado_orden`, y no un CHECK con la lista escrita adentro.
**Contexto**: el dominio pide una lista fija de estados que el sistema necesita para funcionar.
**Alternativas consideradas**: CHECK con la lista de valores.
**Justificación**: con el catálogo, la base sigue rechazando un estado inexistente (ahora por la clave foránea), y cada estado lleva **datos propios** que la API puede mostrar y las consultas pueden cruzar — p. ej. `es_final`, que decide qué es una orden abierta (RN-16). La clave primaria es el `codigo` y no un `id`, para que `orden_trabajo.estado` se lea igual en psql que en la API.
**Trade-offs aceptados**: un estado nuevo funciona sólo si se tocan **dos lugares** — el catálogo (fila) y el enum del código (contrato de la API; un estado que no declara da 422) — y el servicio. El catálogo no automatiza eso.

### DD-02 — Roles en su propia tabla (`asignacion_rol`), no columna en `usuario`
**Decisión**: `usuario` no tiene columna `rol`. Los roles de una persona son las filas de `asignacion_rol` vigentes: no revocadas y sin vencer.
**Contexto**: el taller tiene cuatro roles que el administrador asigna y revoca **con vigencia**.
**Alternativas consideradas**: columna `rol` (o tabla intermedia simple) en `usuario`.
**Justificación**: la autorización se decide **en la base, en cada petición** (RN-04). Revocar escribe `revocada_en` y la fila **no se borra nunca**: queda el historial de quién tuvo qué rol y hasta cuándo (sección 5.9). El índice único parcial `(usuario_id, rol) WHERE revocada_en IS NULL` garantiza a lo sumo una asignación **abierta** por rol (RN-03).
**Trade-offs aceptados**: consultas un poco más largas (join o filtro por vigencia) a cambio de auditoría completa e inmediatez de la revocación.

### DD-03 — Índices únicos parciales para la unicidad entre vigentes
**Decisión**: `patente` y `codigo` **no** son UNIQUE comunes; la unicidad es un índice único parcial `WHERE borrado_en IS NULL` (y lo mismo para la asignación abierta de roles).
**Contexto**: `vehiculo` y `repuesto` tienen borrado lógico: la fila dada de baja sigue en la tabla.
**Alternativas consideradas**: UNIQUE común.
**Justificación**: con un UNIQUE común, el comprador de un auto vendido no podría registrarlo, y la base respondería «ya existe» de un vehículo que la aplicación **no muestra** en ningún listado. El índice parcial cuenta sólo los vigentes (sección 4.9).
**Trade-offs aceptados**: las consultas que quieren unicidad global deben filtrar ellos mismos; y un UNIQUE común no protege contra reutilizar el código de un baja… que es justamente lo que se quiere permitir.

### DD-04 — `iat` del JWT sin truncar a segundos
**Decisión**: el `iat` se emite con la hora completa (JWT admite fracciones de segundo) y la comparación con `password_cambiada_en` se hace **sin truncar** (RN-07).
**Contexto**: al cambiar la contraseña, las sesiones anteriores deben dejar de valer, **aunque sean del mismo segundo** que el cambio; la token del propio cambio, no.
**Alternativas consideradas**: truncar `iat` y `password_cambiada_en` a segundos.
**Justificación**: si se truncara, una sesión iniciada en el mismo segundo que el cambio, pero **antes** de él, sería indistinguible de la nueva y seguiría valiendo. El token nuevo pasa porque se emite **después** de anotar el cambio (sección 5.10).
**Trade-offs aceptados**: requiere precisión sub-segundo en la comparación (y `password_cambiada_en` con timezone).

### DD-05 — Dos grupos de rutas para el cambio obligatorio
**Decisión**: `main.py` define un grupo **abierto** y otro **protegido**, con el control del cambio obligatorio montado **una sola vez** en el protegido.
**Contexto**: mientras `debe_cambiar_password`, el usuario sólo puede usar `/auth` y salud (RN-06).
**Alternativas consideradas**: una dependencia por ruta.
**Justificación**: FastAPI **suma** dependencias y no las resta (sección 5.10); montar el control una vez en el grupo evita olvidos y garantiza que toda ruta nueva del grupo protegida quede protegida por defecto.
**Trade-offs aceptados**: hay que recordar montar cada router en el grupo correcto.

### DD-06 — Cancelar sin `requiere_rol`; el servicio decide identidad y luego estado
**Decisión**: `POST /ordenes/{id}/cancelar` no lleva `requiere_rol`. El servicio evalúa **primero** quién es y qué relación tiene con la orden (403), y **recién después** si el estado permite cancelarla (409) — RN-12.
**Contexto**: el dueño de un vehículo puede cancelar su orden y **no tiene un rol de personal**.
**Alternativas consideradas**: exigir RECEPCION o ADMIN en la ruta.
**Justificación**: si la ruta exigiera rol de personal, el dueño recibiría «no tenés permiso» cuando **sí** lo tiene.
**Trade-offs aceptados**: la lógica de permiso queda en el servicio (más código de servicio) en vez de declararse en la ruta.

### DD-07 — El catálogo tiene un repositorio propio de sólo lectura
**Decisión**: `EstadoOrdenRepository` **no** hereda de `BaseRepository`.
**Contexto**: su clave primaria no es `id` y desde la API no se escribe.
**Alternativas consideradas**: heredar y no usar `add`/`update`/`delete`.
**Justificación**: heredar le daría `add`, `update` y `delete` que **no debe ofrecer**; la imposibilidad de escribir el catálogo desde la API es estructural, no una convención (RN-19).
**Trade-offs aceptados**: un repositorio a medida (chico).

### DD-08 — Hash calculado antes de abrir la transacción
**Decisión**: toda llamada a bcrypt (hash y verificación) corre **fuera del bucle** (`to_thread` + semáforo) y el hash se calcula **antes** de abrir la transacción.
**Contexto**: bcrypt tarda ~300 ms; dentro de la transacción la conexión quedaría tomada sin usar la base.
**Alternativas consideradas**: calcular el hash dentro del UoW.
**Justificación**: sección 5.6/5.4 — no se frena el bucle de eventos y no se sostiene una transacción ociosa.
**Trade-offs aceptados**: el orden del código queda más explícito (primero crypto, después DB).

### DD-09 — `intento_acceso` en sesión y transacción propias, siempre confirmadas
**Decisión**: cada intento de login (correcto o fallido) se anota con **una sesión y una transacción propias**, que se confirman **siempre**.
**Contexto**: el intento debe **sobrevivir al rollback** del login fallido.
**Alternativas consideradas**: anotar en la misma transacción de la petición.
**Justificación**: el fallo que se quiere contar es **el mismo** que la revierte (sección 6.8.1). Es la **única** escritura del sistema que no comparte la transacción de su petición.
**Trade-offs aceptados**: deja filas aunque la petición falle — el código lo declara en un comentario, junto con su costo.

### DD-10 — Sólo agregado por disparador (migración escrita a mano)
**Decisión**: el UPDATE/DELETE sobre las tres tablas de auditoría se rechaza con un **disparador** instalado por una migración **escrita a mano** (la comparación automática de Alembic no ve funciones ni disparadores).
**Contexto**: RN-15; el TP entrega dos migraciones.
**Alternativas consideradas**: permisos de rol de base (sección 6.9).
**Justificación**: el TP usa un **solo rol de base**, así que el disparador es el mecanismo que se pide; cualquiera de los dos alcanza y tener los dos es defensa en profundidad.
**Trade-offs aceptados**: hay que escribir y leer la migración a mano; el disparador rechaza también a un DBA (eso es lo pedido).

### DD-11 — El esquema se crea sólo con Alembic
**Decisión**: **no** se usa `create_all`; el esquema nace de `alembic upgrade head` (plantilla asincrónica) y debe sobrevivir el ciclo `upgrade head → downgrade base → upgrade head` sobre una base vacía.
**Contexto**: requisito duro del TP (un proyecto que no crea su esquema así no se corrige).
**Alternativas consideradas**: `create_all` de SQLModel/SQLAlchemy.
**Justificación**: versionado, reproducibilidad y alineación con el capítulo 4.
**Trade-offs aceptados**: todo cambio de esquema exige una migración.

### DD-12 — Estructura por módulo con seis capas repetidas
**Decisión**: organización **por módulo funcional** (`health`, `usuarios`, `clientes`, `repuestos`, `ordenes`), cada uno con las mismas seis capas (`models`, `schemas`, `repository`, `unit_of_work`, `service`, `router`).
**Contexto**: estructura obligatoria de la consigna; los casos de prueba y la corrección la usan.
**Alternativas consideradas**: capa por capa a todo el proyecto (`app/models/...`).
**Justificación**: localidad de cambio; cada módulo se lee solo; el UoW del módulo compone sólo los repositorios que sus operaciones necesitan.
**Trade-offs aceptados**: algo de repetición de patrón entre módulos (a cambio de simetría).

### DD-13 — Aviso con `BackgroundTasks` (sin Redis)
**Decisión**: el aviso al cliente al terminar una orden se simula con `BackgroundTasks` + `await asyncio.sleep(0.5)` + log, en el **mismo proceso**.
**Contexto**: fuera de alcance las colas del capítulo 8.
**Alternativas consideradas**: Redis + workers.
**Justificación**: el aviso es simulado y perderlo no rompe nada. Comparte dos de los tres problemas de una tarea suelta: si el proceso se reinicia el aviso se pierde, y no hay reintento — se acepta deliberadamente (sección 3.9).
**Trade-offs aceptados**: no duradero, no reintentable; el capítulo 8 lo resuelve.

### DD-14 — Dos migraciones: autogenerate + manual
**Decisión**: migración 1 **generada** con `--autogenerate` (todas las tablas); migración 2 **escrita a mano** (disparador de sólo agregado). Cada una **se lee antes de aplicarla** y lleva un comentario que lo diga.
**Contexto**: la comparación automática no ve funciones ni disparadores.
**Alternativas consideradas**: una sola migración.
**Justificación**: separar lo que la herramienta ve de lo que hay que escribir a mano; legibilidad del review.
**Trade-offs_ACCEPTados**: dos archivos que deben aplicarse en orden.

## Supuestos inferidos

### SU-01 — El PDF no incluye el diagrama de clases en texto
**Supuesto**: la Figura 1 (diagrama de clases con rombo de composición, flecha de asociación, «catalog» y «appendOnly») es una imagen; su contenido se infiere de la tabla de entidades y de las notas del texto.
**Origen**: consigna p. 4 (la figura) vs pp. 5–6 (la tabla de columnas/restricciones, que es completa).
**Riesgo si es falso**: una relación no listada en la tabla podría existir en la figura.
**Cómo validar**: abrir la Figura 1 del PDF original y contrastar con el ERD de `04_modelo_de_datos.md`.

### SU-02 — Los CHECK «`>>`» del PDF son erratas de extracción
**Supuesto**: los CHECK impresos como `CHECK cantidad >> 0` (movimiento_stock) y `CHECK precio_nuevo >> precio_anterior` (historial_precio_repuesto) son erratas de la extracción de texto y deberían leerse `cantidad <> 0` y `precio_nuevo <> precio_anterior`.
**Origen**: consigna p. 6; el resto del texto (RN-13, RN-20, casos C-11/C-18) es coherente con salidas negativas de stock y cambios de precio que pueden subir o bajar.
**Riesgo si es falso**: si el CHECK fuera `> 0` en movimiento_stock, las salidas de stock no podrían registrarse como negativas; si el de precio fuera `> precio_anterior`, los descuentos de precio no dejarían línea.
**Cómo validar**: confirmar contra el PDF original (o contra el corrector) el signo exacto de ambos CHECK.

### SU-03 — «8 puntos / 10 puntos / 14 puntos / 16 puntos / 20 puntos» son marcas de corrección
**Supuesto**: los números sueltos que aparecen entre párrafos (p. ej. «8 puntos», «14 puntos») son marcas de la planilla de corrección, no requisitos del dominio.
**Origen**: consigna pp. 10–14, distribuidos junto a los ejercicios; la tabla de criterios de evaluación (p. 22) usa porcentajes, no puntos absolutos.
**Riesgo si es falso**: podrían indicar un mínimo de implementaciones por ejercicio.
**Cómo validar**: preguntar al docente o mirar la planilla de corrección original.

### SU-04 — El servicio de terminar valida identidad antes que estado
**Supuesto**: para `POST /ordenes/{id}/terminar`, el orden de validación es 403 (no es el mecánico asignado ni ADMIN) y después 409 (estado no permite). La consigna lo explicita para **cancelar** (RN-12); se asume el mismo criterio para terminar por simetría.
**Origen**: RN-12 y el recuadro «La ruta de cancelar no lleva requiere_rol»; el endpoint de terminar tiene 403 y 409 en sus códigos.
**Riesgo si es falso**: un mecánico no asignado podría recibir 409 en vez de 403.
**Cómo validar**: ejecutar el caso de prueba análogo al C-13 para `terminar` y verificar el código.

### SU-05 — `size` por defecto 20 y mínimo 1 son los defaults del contrato
**Supuesto**: la paginación usa `page` desde 1, `size` por defecto 20 y rango 1–100; una página fuera de rango o inexistente da 422.
**Origen**: consigna p. 11 (Ejercicio 3) y ejemplo de listado p. 18.
**Riesgo si es falso**: mínimos detalles del contrato de query-param.
**Cómo validar**: contrastar con los `.http` de prueba cuando existan.

### SU-06 — El nombre de la variable de la clave de firma no está fijado
**Supuesto**: la consigna exige que la clave de firma salga del entorno sin default, pero no fija el nombre exacto de la variable (p. ej. `SECRET_KEY`, `JWT_SECRET`, …).
**Origen**: consigna pp. 3–4 (Requisitos técnicos) y 19 (Requisitos no funcionales).
**Riesgo si es falso**: los `.http` o la corrección podrían esperar un nombre específico.
**Cómo validar**: preguntar al docente o fijar uno y documentarlo en `env.example`.

### SU-07 — El módulo `health` no tiene modelos ni UoW
**Supuesto**: «El módulo health sólo tiene router.py» significa que no lleva `models.py`, `schemas.py`, `repository.py`, `unit_of_work.py` ni `service.py` — sus dos rutas no persisten estado propio (`ready` sólo ejecuta `SELECT 1`).
**Origen**: consigna p. 10 (estructura obligatoria).
**Riesgo si es falso**: la corrección podría esperar un `service.py` mínimo.
**Cómo validar**: contrastar con la planilla de corrección.
