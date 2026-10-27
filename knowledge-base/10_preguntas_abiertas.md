# Preguntas Abiertas

## Inconsistencias detectadas

### IN-01 — CHECK de `movimiento_stock.cantidad` impresos como `>>` — ✅ RESUELTO
**Documento A dice** (consigna p. 6, tabla de restricciones): `CHECK cantidad >> 0` en `movimiento_stock`.
**Documento B dice** (RN-13 y caso C-11): terminar una orden **descuenta** stock y deja «un movimiento por cada salida»; el caso C-11 exige que un stock insuficiente no deje escrituras.

**Verificación contra el PDF original** (2026-10-27, texto extraído con `pypdf`): la p. 6 imprime literalmente `CHECK cantidad >> 0`. Pero `>>` **no puede ser el operador del CHECK**:
- En PostgreSQL `>>` es el operador de **desplazamiento de bits** (`integer >> integer`), que devuelve un `integer`, no un `boolean`; `CHECK (cantidad >> 0)` falla al crear la tabla con *«argument of CHECK must be type boolean»*.
- Es decir: si el esquema se escribiera tal cual, la migración no aplicaría nunca.

**Resolución**: el CHECK se escribe como `cantidad <> 0` (errata de renderizado del PDF: `<>` se ve como `>>`). Convención de signo: **entradas positivas, salidas negativas** — es lo único que permite modelar el descuento de RN-13 como un movimiento con signo y deja el stock no negativo a cargo de `repuesto.stock >= 0` (p. 2: «sin que el stock llegue a ser negativo —el CHECK lo impediría—»).

### IN-02 — CHECK de `historial_precio_repuesto` impresos como `precio_nuevo >> precio_anterior` — ✅ RESUELTO
**Documento A dice** (consigna p. 6): `CHECK precio_nuevo >> precio_anterior`.
**Documento B dice** (RN-20 y caso C-18): cada cambio de precio deja línea con el precio anterior y el nuevo; un PATCH que no cambia el precio no deja línea. Nada dice que el precio sólo pueda subir.

**Verificación contra el PDF original** (2026-10-27): la p. 6 imprime `CHECK precio_nuevo >> precio_anterior`. Para tipos `NUMERIC` **no existe** el operador `>>` en PostgreSQL (el desplazamiento de bits sólo aplica a enteros y bit strings), así que el CHECK literal es SQL inválido y la migración no aplicaría.

**Resolución**: se escribe `precio_nuevo <> precio_anterior` — el precio puede subir o bajar, pero la fila sólo se crea si hubo cambio. El CHECK independiente `precio_nuevo > 0` de la misma tabla se mantiene tal cual.

### IN-03 — La figura del diagrama de clases no está en el texto — ✅ RESUELTO
**Documento A dice** (consigna p. 4): «Figura 1 · Diagrama de clases. El rombo lleno es composición y la flecha es asociación…».
**Documento B dice**: la figura es una imagen; el texto sólo describe la tabla de entidades y las notas.

**Verificación contra el PDF original** (2026-10-27): se extrajo la imagen de la p. 4 (`pypdf` + `pillow`) y se revisó el diagrama completo. Contiene exactamente estas asociaciones:

```
cliente 1 ── 0..* vehiculo
cliente 0..1 ── 1 usuario            (etiqueta «1 a 1»)
usuario 1 ── 0..* asignacion_rol     (etiqueta «roles»)
usuario 0..1 ── 0..* orden_trabajo   (etiqueta «mecánico»)
vehiculo 1 ── 0..* orden_trabajo
orden_trabajo 1 ── 1..* item_orden        (COMPOSICIÓN)
orden_trabajo 1 ── 1..* historial_estado_orden (COMPOSICIÓN)
orden_trabajo * ── 1 estado_orden    (etiqueta «catálogo»)
item_orden 0..* ── 1 repuesto
repuesto 1 ── 0..* movimiento_stock
repuesto 1 ── 0..* historial_precio
```

**Resultado**: no hay ninguna relación en la figura que falte en el ERD de `04_modelo_de_datos.md`; las relaciones adicionales que lista la KB (por ejemplo `usuario → movimiento_stock` y `usuario → historial_precio_repuesto`) provienen de columnas FK de la tabla de la p. 6, no de flechas del dibujo, y no contradicen la figura.

**Dos precisiones que quedan documentadas**:
1. La figura marca `item_orden` como **`1..*`**: una orden nace con **al menos un ítem**. La base no puede exigir «al menos un hijo» sin restricciones diferidas, así que la regla se valida en el servicio (`C-11`), no en el esquema.
2. La figura **no dibuja** columnas que la tabla sí exige —`usuario.password_cambiada_en`, `asignacion_rol.otorgada_por` y todas las FK—: es un diagrama de clases con asociaciones, no un DDL. Manda la tabla de la p. 5–6 para columnas y la figura para cardinalidades.

### IN-04 — Números de «puntos» dispersos entre los ejercicios
**Documento A dice**: sueltos en las pp. 10–14: «8 puntos», «14 puntos», «10 puntos», «16 puntos», «20 puntos» junto a los ejercicios.
**Documento B dice**: la tabla de criterios de evaluación (p. 22) usa **porcentajes** (8 %, 14 %, 10 %, 16 %, 14 %, 20 %, 10 %, 8 %).
**Impacto**: los «puntos» podrían ser marcas de la planilla de corrección (inofensivos) o un mínimo exigido por ejercicio.
**Resolución propuesta**: tratarlos como marca de corrección; preguntar al docente si importan.

## [DISCOVERY] Campos de discovery inferidos con incertidumbre

*(Regla low-confidence del Mode A: nunca inventar un valor seguro; se marca la incertidumbre y se registra acá.)*

- `system_type`: inferido como **`api`** (API REST asincrónica). Es un backend sin frontend propio en el repo; la «web» del taller es un cliente externo. Confianza: **alta** (la consigna habla sólo de API y endpoints).
- `domain`: inferido como **`automotive_repair / taller mecánico`**. Confianza: **alta** (dominio declarado).
- `scale`: inferido como **`team`** (un taller: personal + clientes; no es single-user ni multi-tenant). Confianza: **alta**.
- `stack`: inferido de la tabla de requisitos técnicos. Confianza: **alta**.
- `needs_infra`: inferido como **`true`** (PostgreSQL 16 obligatorio; sin colas ni caché). Confianza: **alta**.
- `problem`: inferido de la sección Contexto. Confianza: **alta**.

No hay campos de discovery con confianza baja que bloqueen; las dudas reales son de **implementación** (IN-01 a IN-04) y de **contrato** (SU-04 a SU-07 en `09_decisiones_y_supuestos.md`).

## Preguntas abiertas (priorizadas)

> **Estado 2026-10-27**: las tres preguntas de prioridad **Alta** que bloqueaban `C-03 domain-models` quedaron **resueltas** contra el PDF original (ver IN-01, IN-02 e IN-03 arriba). No queda ninguna pregunta que bloquee la implementación.

| Prioridad | Pregunta | Estado | Decisor |
|-----------|----------|--------|---------|
| ~~Alta~~ | ~~¿Los CHECK `>>` del PDF son `<>`?~~ (IN-01, IN-02) | ✅ **Resuelto**: sí, `<>`; el `>>` literal es SQL inválido | PDF original |
| ~~Alta~~ | ~~¿La Figura 1 tiene requisitos que no estén en la tabla?~~ (IN-03) | ✅ **Resuelto**: la figura no agrega relaciones faltantes; sólo fija `item_orden 1..*` | PDF original |
| ~~Media~~ | ~~¿`movimiento_stock.cantidad` admite cero?~~ (IN-01) | ✅ **Resuelto**: no, `<> 0` (entradas positivas, salidas negativas) | PDF original |
| Media | ¿El nombre de la variable de la clave de firma está fijado (p. ej. `SECRET_KEY`)? (SU-06) | Abierta — no bloquea: `C-01` adoptó `SECRET_KEY` y está documentado en `env.example` | Docente |
| Media | Para `terminar`, ¿el 403 (no asignado) se evalúa antes que el 409 (estado), como en cancelar? (SU-04) | Abierta — no bloquea: `C-11` adopta 403 antes que 409 (SU-04) | Docente |
| Baja | ¿Los «puntos» dispersos son marca de corrección o mínimo por ejercicio? (IN-04) | Abierta — sin impacto funcional: se tratan como marca de corrección | Docente |
| Baja | ¿El módulo `health` lleva algún archivo besides `router.py`? (SU-07) | Abierta — no bloquea: `C-01` dejó sólo `router.py` (coincide con `08_arquitectura_propuesta.md`) | Docente |

## Temas cubiertos por la consigna que NO están abiertos

- Tablas, columnas y restricciones: **completos** (tabla p. 5–6, con nombres obligatorios).
- Reglas RN-01 a RN-20: **completas** con su garante esperado.
- Endpoints de referencia con quién y códigos: **completos** (pp. 15–17).
- Seed data mínimo: **completo** (p. 19).
- Casos de prueba C-01 a C-19: **completos** con resultado esperado.
- Criterios de evaluación y formato de entrega: **completos** (p. 22).
- Fuera de alcance (concurrencia, Redis): **explícito**.
