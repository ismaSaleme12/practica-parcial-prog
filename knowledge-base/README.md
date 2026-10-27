# practica-parcial-prog — Base de Conocimiento

Base de conocimiento generada a partir de la consigna del TP integrador de **Programación III** (unidades 1 a 6 — «del objeto a la transacción»): `docs/TP_Cap1a6_Consigna.pdf` (22 páginas), extraída y estructurada con `kb-creator` en modo **ingest**.

## Índice de Archivos

| Archivo | Contenido |
|---------|-----------|
| [01_vision_y_objetivos.md](01_vision_y_objetivos.md) | Propósito (API de taller mecánico), objetivos por actor (recepción, mecánico, admin, cliente, sistema), alcance v1.0, fuera de alcance (concurrencia/Redis), métricas = criterios de evaluación |
| [02_descripcion_general.md](02_descripcion_general.md) | Stack tecnológico (Python 3.12, FastAPI, SQLModel, SQLAlchemy async, asyncpg, PostgreSQL 16, Alembic, bcrypt, PyJWT), arquitectura en capas, ciclo de vida/lifespan, API REST completa con los 2 grupos y ejemplos de contrato |
| [03_actores_y_roles.md](03_actores_y_roles.md) | 5 actores, RBAC matriz completa rol×recurso, reglas 401/403, lo propio, cancelar sin `requiere_rol`, rutas públicas |
| [04_modelo_de_datos.md](04_modelo_de_datos.md) | 13 entidades con atributos/restricciones/relaciones, ERD textual, los 3 índices únicos parciales, catálogo `estado_orden`, tablas de sólo agregado, seed data |
| [05_reglas_de_negocio.md](05_reglas_de_negocio.md) | RN-01 a RN-20 codificadas por dominio, con su garante esperado |
| [06_funcionalidades.md](06_funcionalidades.md) | 26 historias de usuario (US-001 a US-026) en 8 épicas = los 8 ejercicios, con criterios de aceptación y reglas relacionadas |
| [07_flujos_principales.md](07_flujos_principales.md) | 13 flujos extremo a extremo: arranque, registro, login, cambio obligatorio, autorización, roles, alta/iniciar/terminar/cancelar orden, reposición/precio, salud, sólo agregado en psql |
| [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md) | Patrones (UoW, repository, soft delete, catálogo, append-only, DTO), estructura de directorios obligatoria, seguridad, variables de entorno, requisitos no funcionales |
| [09_decisiones_y_supuestos.md](09_decisiones_y_supuestos.md) | 14 decisiones documentadas (DD-01 a DD-14) y 7 supuestos inferidos (SU-01 a SU-07) |
| [10_preguntas_abiertas.md](10_preguntas_abiertas.md) | Inconsistencias detectadas (IN-01 a IN-04): **IN-01 a IN-03 resueltas contra el PDF**; quedan 4 preguntas abiertas de prioridad media/baja que no bloquean |

## Quick Start para Desarrolladores

1. **Entender el dominio** → [01](01_vision_y_objetivos.md), [03](03_actores_y_roles.md)
2. **Entender los datos** → [04](04_modelo_de_datos.md)
3. **Entender las reglas** → [05](05_reglas_de_negocio.md)
4. **Entender la arquitectura** → [02](02_descripcion_general.md), [08](08_arquitectura_propuesta.md)
5. **Implementar** → [07](07_flujos_principales.md), [06](06_funcionalidades.md)
6. **Antes de codificar** → [10](10_preguntas_abiertas.md)

## Resumen Ejecutivo

Se construye una **API REST asincrónica** (FastAPI + PostgreSQL 16) para un taller mecánico, como TP integrador de las unidades 1 a 6 de Programación III. El sistema gestiona clientes, vehículos, repuestos con stock y órdenes de trabajo, con **autenticación** (bcrypt + JWT en cookie HttpOnly, límite de intentos, hash ficticio) y **autorización** por cuatro roles decidida **en la base, en cada petición**. La integridad se delega a PostgreSQL: claves foráneas, CHECK, tres **índices únicos parciales** (borrado lógico y roles vigentes), un **catálogo** de estados y un **disparador de sólo agregado** sobre tres tablas de auditoría (migración escrita a mano). Las operaciones de negocio multi-escritura (registro, terminar orden, cambio de precio) se agrupan en **un solo Unit of Work**; ningún repositorio confirma. Fuera de alcance: concurrencia (capítulo 7) y colas con Redis (capítulo 8).
