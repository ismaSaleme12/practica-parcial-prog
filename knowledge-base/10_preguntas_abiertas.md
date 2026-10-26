# Preguntas Abiertas

## Inconsistencias detectadas

### IN-01 — CHECK de `movimiento_stock.cantidad` impresos como `>>`
**Documento A dice** (consigna p. 6, tabla de restricciones): `CHECK cantidad >> 0` en `movimiento_stock`.
**Documento B dice** (RN-13 y caso C-11): terminar una orden **descuenta** stock y deja «un movimiento por cada salida»; el caso C-11 exige que un stock insuficiente no deje escrituras.
**Impacto**: si el CHECK fuera `cantidad > 0`, las salidas no podrían registrarse como negativas y el descuento no sería modelable como movimiento con signo. Se infiere que la intención es `cantidad <> 0` (entradas positivas, salidas negativas) — errata de extracción (`>>` por `<>`).
**Resolución propuesta**: escribir el CHECK como `cantidad <> 0` y confirmar contra el PDF original.

### IN-02 — CHECK de `historial_precio_repuesto` impresos como `precio_nuevo >> precio_anterior`
**Documento A dice** (consigna p. 6): `CHECK precio_nuevo >> precio_anterior`.
**Documento B dice** (RN-20 y caso C-18): cada cambio de precio deja línea con el precio anterior y el nuevo; un PATCH que no cambia el precio no deja línea. Nada dice que el precio sólo pueda subir.
**Impacto**: si el CHECK fuera `precio_nuevo > precio_anterior`, un descuento de precio sería imposible de registrar. Se infiere `precio_nuevo <> precio_anterior` (el cambio puede subir o bajar, pero debe ser un cambio).
**Resolución propuesta**: escribir el CHECK como `precio_nuevo <> precio_anterior` y confirmar contra el PDF original.

### IN-03 — La figura del diagrama de clases no está en el texto
**Documento A dice** (consigna p. 4): «Figura 1 · Diagrama de clases. El rombo lleno es composición y la flecha es asociación…».
**Documento B dice**: la figura es una imagen; el texto sólo describe la tabla de entidades y las notas.
**Impacto**: una relación que exista en la figura pero no en la tabla podría quedar sin modelar (p. ej. cardinalidades exactas de algunas asociaciones).
**Resolución propuesta**: el ERD de `04_modelo_de_datos.md` se construyó con la tabla + notas; validar contra la imagen del PDF original si hay dudas puntuales.

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

| Prioridad | Pregunta | Bloquea | Decisor |
|-----------|----------|---------|---------|
| **Alta** | ¿Los CHECK `>>` del PDF son `<>` (errata de extracción)? (IN-01, IN-02) | Ejercicio 2 (modelos/migraciones) — el esquema de la migración 1 | Docente / PDF original |
| **Alta** | ¿Existe algún requisito en la Figura 1 que no esté en la tabla de entidades? (IN-03) | Ejercicio 2 | Docente / PDF original |
| **Media** | ¿El CHECK de `movimiento_stock.cantidad` admite cero o exige `<> 0`? (IN-01) | Caso C-11 y la lógica de descuento | Docente |
| **Media** | ¿El nombre de la variable de la clave de firma está fijado (p. ej. `SECRET_KEY`)? (SU-06) | Ejercicio 1 (`env.example`, README) | Docente |
| **Media** | Para `terminar`, ¿el 403 (no asignado) se evalúa antes que el 409 (estado), como en cancelar? (SU-04) | Ejercicio 8 / casos de prueba | Docente |
| **Baja** | ¿Los «puntos» dispersos son marca de corrección o mínimo por ejercicio? (IN-04) | Nada funcional | Docente |
| **Baja** | ¿El módulo `health` lleva algún archivo besides `router.py`? (SU-07) | Estructura (Ejercicio 1) | Docente |

## Temas cubiertos por la consigna que NO están abiertos

- Tablas, columnas y restricciones: **completos** (tabla p. 5–6, con nombres obligatorios).
- Reglas RN-01 a RN-20: **completas** con su garante esperado.
- Endpoints de referencia con quién y códigos: **completos** (pp. 15–17).
- Seed data mínimo: **completo** (p. 19).
- Casos de prueba C-01 a C-19: **completos** con resultado esperado.
- Criterios de evaluación y formato de entrega: **completos** (p. 22).
- Fuera de alcance (concurrencia, Redis): **explícito**.
