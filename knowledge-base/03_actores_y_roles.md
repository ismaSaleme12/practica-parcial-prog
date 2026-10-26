# Actores y Roles

## Actores del sistema

| Actor | Descripción | Cómo interactúa |
|---|---|---|
| **Administrador (ADMIN)** | Dueño o encargado del taller. Mantiene el catálogo de repuestos, repone el stock y administra al personal y sus roles. | API protegida: alta de personal, gestión de roles (asignar/revocar con vigencia), CRUD de repuestos, reposición, historiales de movimientos y precios, eventos de seguridad, y puede terminar/cancelar cualquier orden |
| **Recepción (RECEPCION)** | Personal de recepción. Da de alta a los clientes y a sus vehículos, y abre una orden de trabajo por cada ingreso. | API protegida: crear clientes, ver fichas de clientes (con vehículos), registrar vehículos, dar de baja vehículos, crear y cancelar órdenes, ver repuestos y órdenes |
| **Mecánico (MECANICO)** | Técnico que repara. Toma la orden, la repara y la da por terminada: en ese momento se descuenta el stock. | API protegida: iniciar órdenes (`PENDIENTE → EN_REPARACION`, queda asignado), terminar sus órdenes asignadas, ver repuestos y órdenes |
| **Cliente (CLIENTE)** | Dueño de un vehículo. Se registra solo en la web y consulta el estado de sus vehículos. | Auto-registro (`POST /auth/registro`); luego rutas **lo propio**: `/mis-vehiculos`, `/mis-ordenes`, ver detalle de sus órdenes y cancelarlas si están pendientes |
| **Sistema** | Actor no-persona. Es un **texto**, no un usuario de la tabla `usuario`. | Registra eventos de seguridad con `actor = 'SISTEMA'`, p. ej. la «Carga de los datos iniciales» de `seed.py` |

## Nota sobre la identidad del cliente

- Un **cliente** (fila en `cliente`) puede tener o no un **usuario** (fila en `usuario`), y a lo sumo uno: `cliente.usuario_id` es UNIQUE y nulo permitido (uno a uno opcional).
- El auto-registro crea las tres filas: usuario + rol CLIENTE + ficha de cliente (RN-02).
- Un cliente sin usuario (p. ej. Jorge del seed) existe como ficha pero no ingresa al sistema; lo da de alta la recepción.

## RBAC — Matriz de permisos

Los roles viven en su propia tabla (`asignacion_rol`), no como columna de `usuario`. Un rol está **vigente** si la fila no está revocada (`revocada_en IS NULL`) y no venció (`vence_en` nulo o en el futuro). Los permisos se deciden con los roles vigentes **en la base, en cada petición** (RN-04); los roles del token son informativos.

| Rol →<br>Recurso ↓ | ADMIN | RECEPCION | MECANICO | CLIENTE | Autenticado (cualquier rol) |
|---|---|---|---|---|---|
| **Usuarios y roles** |
| `POST /usuarios` (alta de personal) | ✅ | ❌ | ❌ | ❌ | — |
| `GET /usuarios/{id}/roles` | ✅ | ❌ | ❌ | ❌ | — |
| `POST /usuarios/{id}/roles` (asignar) | ✅ | ❌ | ❌ | ❌ | — |
| `DELETE /usuarios/{id}/roles/{rol}` (revocar) | ✅ | ❌ | ❌ | ❌ | — |
| `GET /eventos` (historial de seguridad) | ✅ | ❌ | ❌ | ❌ | — |
| **Clientes y vehículos** |
| `POST /clientes` | ✅ | ✅ | ❌ | ❌ | — |
| `GET /clientes/{id}` (con vehículos) | ✅ | ✅ | ❌ | ❌ | — |
| `POST /clientes/{id}/vehiculos` | ✅ | ✅ | ❌ | ❌ | — |
| `DELETE /vehiculos/{id}` (baja lógica) | ✅ | ✅ | ❌ | ❌ | — |
| `GET /mis-vehiculos` | ✅ | ✅ | ✅ | ✅ | ✅ (lo propio) |
| **Repuestos** |
| `GET /repuestos` (con `q`, paginado) | ✅ | ✅ | ✅ | ❌ | — |
| `GET /repuestos/{id}` | ✅ | ✅ | ✅ | ❌ | — |
| `POST /repuestos` (con `stock_inicial`) | ✅ | ❌ | ❌ | ❌ | — |
| `PATCH /repuestos/{id}` (descripción y precio) | ✅ | ❌ | ❌ | ❌ | — |
| `DELETE /repuestos/{id}` (baja lógica) | ✅ | ❌ | ❌ | ❌ | — |
| `POST /repuestos/{id}/reponer` | ✅ | ❌ | ❌ | ❌ | — |
| `GET /repuestos/{id}/movimientos` | ✅ | ❌ | ❌ | ❌ | — |
| `GET /repuestos/{id}/precios` | ✅ | ❌ | ❌ | ❌ | — |
| **Órdenes de trabajo** |
| `POST /ordenes` (alta) | ✅ | ✅ | ❌ | ❌ | — |
| `GET /ordenes` (filtrado por estado, paginado) | ✅ | ✅ | ✅ | ❌ | — |
| `GET /ordenes/{id}` | ✅ | ✅ | ✅ | Sólo la de sus vehículos | — |
| `POST /ordenes/{id}/iniciar` | ❌* | ❌ | ✅ | ❌ | — |
| `POST /ordenes/{id}/terminar` | ✅ | ❌ | Sólo la asignada | ❌ | — |
| `POST /ordenes/{id}/cancelar` | ✅ | ✅ | ❌ | Sólo la de sus vehículos (PENDIENTE) | — |
| `GET /estados-orden` (catálogo) | ✅ | ✅ | ✅ | ✅ | ✅ |
| `GET /mis-ordenes` | ✅ | ✅ | ✅ | ✅ | ✅ (lo propio) |

\* La transición `PENDIENTE → EN_REPARACION` la inicia un **mecánico** (RN-11), que queda asignado.

### Reglas de permiso que cruzan la matriz

- **401 vs 403**: 401 = sin sesión o sesión inválida/vencida/inactiva/token anterior al último cambio de contraseña. 403 = tiene sesión pero el rol o la relación con el recurso no lo autorizan.
- **Lo propio (RN-17)**: `/mis-vehiculos` y `/mis-ordenes` sólo piden estar autenticados. Un cliente ve sus vehículos y las órdenes de sus vehículos, y ninguna otra.
- **Cancelar no usa `requiere_rol`** (RN-12): el permiso (¿es recepción/admin o el dueño del vehículo?) se evalúa **antes** que el estado (¿la orden es cancelable?) — 403 antes que 409.
- **Terminar** (RN-11): sólo el mecánico asignado o un ADMIN.
- **Autoprotección (RN-05)**: un administrador no puede revocarse su propio rol ADMIN, y el sistema nunca queda sin administradores vigentes (comprobación en el servicio; 409).
- **Cambio obligatorio (RN-06)**: mientras un usuario tenga `debe_cambiar_password`, sólo puede usar las rutas de `/auth` y las de salud; el resto del grupo protegido responde 403.

## Rutas públicas (grupo abierto — sin cookie)

| Ruta | Notas |
|---|---|
| `GET /health/live` | No toca la base |
| `GET /health/ready` | Ejecuta `SELECT 1`; 503 si la base no contesta |
| `POST /auth/registro` | Crea usuario + rol CLIENTE + ficha de cliente en un solo UoW (RN-02) |
| `POST /auth/login` | Emite la cookie; 429 tras 5 fallos en 60 s (RN-08); misma respuesta y duración exista o no el correo (RN-09) |
| `POST /auth/logout` | Borra la cookie |
| `GET /auth/yo` | Exige sesión (200/401): usuario, roles vigentes y los que dice el token |
| `POST /auth/cambiar-password` | Exige sesión (200/401/422); al cambiarla, las sesiones anteriores dejan de valer (RN-07) |

Todas las demás rutas están en el grupo protegido y responden además 401 sin sesión y 403 con el cambio de contraseña pendiente.
