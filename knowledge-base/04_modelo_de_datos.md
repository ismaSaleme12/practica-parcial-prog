# Modelo de Datos

> Los nombres de tablas y columnas son **obligatorios**: los casos de prueba y la corrección los usan. Se pueden agregar columnas, pero no quitar ni renombrar las indicadas. Todas las fechas son `timestamptz`. El dinero es `NUMERIC` y en Python `Decimal`, nunca `float` (sección 2.7). Cada clave foránea lleva un índice, porque PostgreSQL no lo crea solo (sección 4.10).

## Dominios

| Dominio | Módulo | Tablas | Descripción |
|---|---|---|---|
| Identidad y accesos | `usuarios` | `usuario`, `asignacion_rol`, `intento_acceso`, `evento_seguridad` | Cuentas, roles con vigencia, intentos de login y auditoría |
| Cartera de clientes | `clientes` | `cliente`, `vehiculo` | Fichas de cliente (1:1 opcional con usuario) y vehículos con borrado lógico |
| Repuestos y stock | `repuestos` | `repuesto`, `movimiento_stock`, `historial_precio_repuesto` | Catálogo de repuestos con borrado lógico, movimientos de stock y precios (ambos de sólo agregado) |
| Órdenes de trabajo | `ordeneses` | `orden_trabajo`, `item_orden`, `estado_orden`, `historial_estado_orden` | Órdenes con sus ítems (composición), catálogo de estados e historial de transiciones |

## ERD (descripción textual)

La Figura 1 de la consigna es un diagrama de clases: el **rombo lleno** es composición y la **flecha** es asociación. «catalog» (verde) marca la tabla de referencia que carga `seed.py`, y «appendOnly» (ámbar), las tablas de sólo agregado que protege el disparador. `intento_acceso` y `evento_seguridad` **no aparecen**: no se relacionan con ninguna otra tabla.

Relaciones:

```
usuario 1 ──── 0..1 cliente            (uno a uno opcional; cliente.usuario_id UNIQUE, nulo)
usuario 1 ──── * asignacion_rol        (roles vigentes = filas no revocadas ni vencidas)
cliente 1 ──── * vehiculo              (asociación; vehiculo.cliente_id FK)
vehiculo 1 ──── * orden_trabajo        (asociación; orden_trabajo.vehiculo_id FK)
usuario 1 ──── * orden_trabajo         (opcional: orden_trabajo.mecanico_id FK, nulo)
repuesto 1 ──── * item_orden           (asociación; item_orden.repuesto_id FK)
orden_trabajo 1 ── * item_orden        (COMPOSICIÓN: un ítem no existe sin su orden)
estado_orden 1 ── * orden_trabajo      (catálogo; orden_trabajo.estado FK a estado_orden.codigo)
estado_orden 1 ── * historial_estado_orden (catálogo; desde_estado y hasta_estado FK)
orden_trabajo 1 ── * historial_estado_orden (asociación)
usuario 1 ──── * historial_estado_orden (asociación; quién produjo el cambio)
repuesto 1 ──── * movimiento_stock     (asociación)
orden_trabajo 0..1 ── * movimiento_stock (opcional; movimiento_stock.orden_id FK, nulo)
usuario 1 ──── * movimiento_stock      (asociación)
repuesto 1 ──── * historial_precio_repuesto (asociación)
usuario 1 ──── * historial_precio_repuesto (asociación)
```

`Usuario.cliente` devuelve **un objeto** y no una lista (navegación declarada en ambos extremos de cada relación que se lea).

## Entidades

### usuario

- **Atributos**: `id`, `email`, `nombre`, `password_hash`, `activo`, `debe_cambiar_password`, `password_cambiada_en` (con zona horaria, nulo permitido)
- **Restricciones**: `email` UNIQUE
- **Relaciones**: 1:1 opcional con `cliente`; 1:N con `asignacion_rol`, `orden_trabajo` (como mecánico), `historial_estado_orden`, `movimiento_stock`, `historial_precio_repuesto`

### asignacion_rol

- **Atributos**: `id`, `usuario_id`, `rol`, `desde`, `vence_en` (nulo), `revocada_en` (nulo), `otorgada_por` (nulo)
- **Restricciones**: CHECK de `rol` dentro de `ADMIN, RECEPCION, MECANICO, CLIENTE`; **índice único parcial** `(usuario_id, rol) WHERE revocada_en IS NULL` — un usuario tiene a lo sumo una asignación **abierta** por rol (RN-03)
- **Nota**: los roles viven en su propia tabla, no en una columna de `usuario`. Revocar escribe `revocada_en`; la fila no se borra nunca: así queda el historial de quién tuvo qué rol y hasta cuándo (sección 5.9). Reasignar un rol vencido cierra la fila anterior y abre una nueva.

### intento_acceso

- **Atributos**: `id`, `cuando`, `email`, `ip`, `exito`
- **Índice**: `(email, ip, cuando)` — alimenta el límite de intentos de login (RN-08)
- **Relación**: ninguna con otras tablas
- **Nota**: cada intento (correcto o fallido) se anota desde **una sesión y una transacción propias**, que se confirman siempre: es la única escritura del sistema que no comparte la transacción de su petición, porque el fallo que se quiere contar es el mismo que la revierte (sección 6.8.1)

### evento_seguridad

- **Atributos**: `id`, `cuando`, `actor` (texto — incluye `'SISTEMA'`, que no es un usuario), `accion`
- **Restricciones**: ninguna extra
- **Relación**: ninguna con otras tablas
- **Nota**: registra altas, cambios de rol y de contraseña, y los datos iniciales (sección 5.8)

### cliente

- **Atributos**: `id`, `usuario_id` (nulo permitido), `nombre`, `documento`, `telefono`
- **Restricciones**: `usuario_id` UNIQUE (uno a uno opcional con usuario); `documento` UNIQUE
- **Relaciones**: 1:1 con `usuario` (opcional); 1:N con `vehiculo`

### vehiculo

- **Atributos**: `id`, `cliente_id`, `patente`, `marca`, `modelo`, `anio`, `borrado_en` (nulo)
- **Restricciones**: **índice único parcial** `(patente) WHERE borrado_en IS NULL`; CHECK `anio BETWEEN 1950 AND 2100`
- **Relaciones**: N:1 con `cliente`; 1:N con `orden_trabajo`
- **Borrado lógico**: `SoftDeleteRepository`; un vehículo dado de baja deja de aparecer y no se usa en órdenes nuevas (RN-16). Un vehículo con órdenes **abiertas** (estado no final según `es_final`) no se da de baja (409).

### repuesto

- **Atributos**: `id`, `codigo`, `descripcion`, `precio` (NUMERIC 10,2), `stock`, `borrado_en` (nulo)
- **Restricciones**: **índice único parcial** `(codigo) WHERE borrado_en IS NULL`; CHECK `precio > 0`; CHECK `stock >= 0`
- **Relaciones**: 1:N con `item_orden`, `movimiento_stock`, `historial_precio_repuesto`
- **Borrado lógico**: igual que `vehiculo`
- **Nota**: el stock **sólo** cambia a través de `movimiento_stock` — alta con stock inicial, reposición y terminación de órdenes. No se edita por PATCH (RN-14).

### estado_orden (catálogo)

- **Atributos**: `codigo` (clave primaria — es el código y no un `id`, para que `orden_trabajo.estado` se lea igual en psql que en la API), `descripcion`, `posicion`, `es_final`
- **Restricciones**: `posicion` UNIQUE
- **Filas** (cargadas por `seed.py`, no por migración): `PENDIENTE` (posición 1), `EN_REPARACION` (2), `TERMINADA` (3, final), `CANCELADA` (4, final)
- **Nota**: la migración crea la tabla **vacía**; sus filas son datos y las carga `seed.py`. La clave foránea rechaza un estado que no exista (RN-19). El catálogo se consulta desde la API (`GET /estados-orden`) y no se edita desde ella.

### orden_trabajo

- **Atributos**: `id`, `vehiculo_id`, `mecanico_id` (nulo), `estado`, `falla`, `creada_en`, `total` (NUMERIC 12,2)
- **Restricciones**: `estado` es clave foránea a `estado_orden.codigo`; CHECK `total >= 0`
- **Relaciones**: N:1 con `vehiculo`; N:1 opcional con `usuario` (mecánico asignado); 1:N con `item_orden` (composición) e `historial_estado_orden`; 1:N opcional con `movimiento_stock`

### item_orden

- **Atributos**: `id`, `orden_id`, `repuesto_id`, `cantidad`, `precio_unitario` (NUMERIC 10,2)
- **Restricciones**: CHECK `cantidad > 0`; CHECK `precio_unitario > 0`; **UNIQUE `(orden_id, repuesto_id)`** — sin repuestos repetidos en una orden
- **Relaciones**: N:1 con `orden_trabajo` (composición) y con `repuesto`
- **Nota**: el `precio_unitario` se **copia** del repuesto al crear la orden (RN-10); el precio y el total nunca viajan en el cuerpo del request

### historial_estado_orden (sólo agregado)

- **Atributos**: `id`, `orden_id`, `desde_estado` (nulo), `hasta_estado`, `usuario_id`, `cuando`
- **Restricciones**: `desde_estado` y `hasta_estado` son claves foráneas a `estado_orden.codigo`; **sólo agregado** (disparador de la migración 2)
- **Relaciones**: N:1 con `orden_trabajo`, `estado_orden` (×2) y `usuario`

### movimiento_stock (sólo agregado)

- **Atributos**: `id`, `repuesto_id`, `orden_id` (nulo), `usuario_id`, `cantidad`, `motivo`, `cuando`
- **Restricciones**: CHECK `cantidad <> 0` (**resuelto en IN-01**: la consigna lo imprime como `cantidad >> 0`, pero ese operador es un desplazamiento de bits que devuelve un entero y PostgreSQL rechaza el CHECK; la reposición entra positiva y la salida de una orden sale negativa); **sólo agregado**
- **Relaciones**: N:1 con `repuesto`, opcional con `orden_trabajo`, y con `usuario`
- **Nota**: punto único de escritura de stock (RN-14); la terminación de una orden deja **un movimiento por cada salida**

### historial_precio_repuesto (sólo agregado)

- **Atributos**: `id`, `repuesto_id`, `usuario_id`, `precio_anterior` (NUMERIC 10,2), `precio_nuevo` (NUMERIC 10,2), `cuando`
- **Restricciones**: CHECK `precio_nuevo > 0`; CHECK `precio_nuevo <> precio_anterior` (**resuelto en IN-02**: la consigna lo imprime como `precio_nuevo >> precio_anterior`, pero `>>` no existe para `NUMERIC` en PostgreSQL; el precio puede subir o bajar, y un PATCH que no cambia el precio no deja línea); **sólo agregado**
- **Relaciones**: N:1 con `repuesto` y `usuario`
- **Nota**: cada cambio de precio deja una línea en la **misma transacción** que el cambio (RN-20); un PATCH que no cambia el precio no deja línea

## Índices únicos parciales (resumen — los tres)

| Tabla | Índice | `WHERE` | Propósito |
|---|---|---|---|
| `asignacion_rol` | `(usuario_id, rol)` | `revocada_en IS NULL` | A lo sumo una asignación abierta por rol |
| `vehiculo` | `(patente)` | `borrado_en IS NULL` | Un comprador puede registrar un auto vendido con la misma patente |
| `repuesto` | `(codigo)` | `borrado_en IS NULL` | El código se reutiliza entre los vigentes |

Con un UNIQUE común, el comprador de un auto vendido no podría registrarlo, y la base respondería «ya existe» de un vehículo que la aplicación no muestra en ningún listado (sección 4.9).

## Seed data inicial

`seed.py` **vacía las tablas** y carga, como mínimo, estos datos (los casos de prueba los usan). Las contraseñas son de mentira y viven sólo en ese archivo. El catálogo se carga **primero**, porque todo lo que tiene un estado apunta a él y sin sus filas no se puede crear ninguna orden: `seed.py` es parte de la puesta en marcha, no un extra.

| Qué | Datos |
|---|---|
| Catálogo de estados | `PENDIENTE` (1), `EN_REPARACION` (2), `TERMINADA` (3, final), `CANCELADA` (4, final), cada uno con su descripción |
| Usuarios | `admin@example.com` y `admin2@example.com` (ADMIN), `recepcion@example.com` (RECEPCION), `mecanico@example.com` y `mecanico2@example.com` (MECANICO), `cliente@example.com` (CLIENTE) y `nuevo@example.com` (MECANICO, con el cambio de contraseña obligatorio) |
| Clientes | Laura, con usuario (`cliente@example.com`) y dos vehículos; Jorge, sin usuario, con un vehículo |
| Repuestos | Filtro de aceite (stock 10), pastillas de freno (4), bujía (2) y aceite por litro (20); cada stock cargado como un movimiento «Stock inicial» |
| Órdenes | La 1, PENDIENTE, del primer vehículo de Laura; la 2, EN_REPARACION, del vehículo de Jorge, asignada a `mecanico@example.com`, con 4 bujías cuando hay 2 (sirve para el caso C-11) |
| Historial de precios | Una línea del filtro de aceite: de 8000 a 8500 |
| Historial de seguridad | Una línea con el actor `SISTEMA`: «Carga de los datos iniciales» |
