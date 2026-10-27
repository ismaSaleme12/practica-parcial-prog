# practica-parcial-prog — Instrucciones para Agentes

> Este archivo (y su copia `CLAUDE.md`) es lo PRIMERO que todo agente lee al entrar al repo.
> Generado a partir de `knowledge-base/` y `CHANGES.md`. No editar a mano sin re-sincronizar ambos archivos.

---

## Stack Tecnológico

| Capa | Tecnologías | Versión mínima |
|---|---|---|
| Lenguaje | Python | 3.12 |
| Framework web | FastAPI (todos los handlers con `async def`) | 0.111 |
| Modelos de tabla | SQLModel | 0.0.24 |
| Motor / sesión / carga anticipada | SQLAlchemy 2.0, **asincrónico** | 2.0 |
| Controlador de BD | asyncpg (asincrónico). Se acepta psycopg 3 asincrónico | 0.30 |
| Base de datos | PostgreSQL | 16 |
| Migraciones | Alembic, **plantilla asincrónica** | 1.13 |
| Configuración | pydantic-settings (clase `Settings` desde el entorno o `.env`) | 2.0 |
| Hash de contraseñas | bcrypt | 4.0 |
| Token firmado | PyJWT | 2.8 |
| Servidor ASGI | uvicorn (lo instala `fastapi[standard]`) | el que instala |

**Stack CERRADO**: sin Redis, sin Docker, sin ORM alternativo, sin frontend. La única adición permitida es el bloque de testing (`pytest`, `pytest-asyncio`, `httpx`) definido en `C-05 test-infrastructure`.

Detalle completo: [knowledge-base/02_descripcion_general.md](knowledge-base/02_descripcion_general.md)

---

## Base de Conocimiento

La fuente de verdad del dominio vive en `knowledge-base/`. **Leé el archivo relevante ANTES de implementar.**

| Archivo | Cuándo leerlo |
|---------|---------------|
| [01_vision_y_objetivos.md](knowledge-base/01_vision_y_objetivos.md) | Entender propósito y alcance |
| [02_descripcion_general.md](knowledge-base/02_descripcion_general.md) | Stack, arquitectura en capas, contratos de referencia |
| [03_actores_y_roles.md](knowledge-base/03_actores_y_roles.md) | Auth, RBAC, permisos |
| [04_modelo_de_datos.md](knowledge-base/04_modelo_de_datos.md) | Entidades, ERD, migraciones (nombres obligatorios) |
| [05_reglas_de_negocio.md](knowledge-base/05_reglas_de_negocio.md) | Reglas codificadas (RN-01 a RN-20) |
| [06_funcionalidades.md](knowledge-base/06_funcionalidades.md) | Historias de usuario por épica (US-001 a US-026) |
| [07_flujos_principales.md](knowledge-base/07_flujos_principales.md) | Flujos E2E (13 flujos) |
| [08_arquitectura_propuesta.md](knowledge-base/08_arquitectura_propuesta.md) | Patrones, estructura de directorios, env vars |
| [09_decisiones_y_supuestos.md](knowledge-base/09_decisiones_y_supuestos.md) | Decisiones DD-01..DD-14, supuestos SU-01..SU-07 |
| [10_preguntas_abiertas.md](knowledge-base/10_preguntas_abiertas.md) | ⚠️ Inconsistencias a resolver ANTES de codear |

> ⚠️ Resolver las preguntas de prioridad **Alta** de `10_preguntas_abiertas.md` (IN-01/IN-02: CHECK `>>` → `<>`; IN-03: Figura 1) antes de arrancar `C-03 domain-models`.

---

## Skills Disponibles

| Agente | Rol | Skills que carga |
|--------|-----|------------------|
| **Backend Core** | FastAPI / SQLModel / UoW / modelos / migraciones | `python-fastapi-development`, `supabase-postgres-best-practices`, `auth-implementation-patterns` |
| **Backend Aux** | Contratos, errores, evidencia `.http` | `python-fastapi-development`, `auth-implementation-patterns`, `code-review` |
| **QA / Tests** | Infra pytest, suite incremental, casos C-01..C-19 | `tdd`, `code-review`, `supabase-postgres-best-practices` |
| **Orquestación** | SDD / OPSX / docs | `kb-creator`, `roadmap-generator`, `agents-md-generator`, `discovery-research`, `web-scraper`, `skill-creator` |

> **Instaladas localmente en `.agents/skills/`**: `fastapi`, `fastapi-patterns`, `supabase-postgres-best-practices`. (Otras pendientes de requerir).

Cargá la skill correspondiente al contexto ANTES de escribir código.

> Los compact rules de cada skill los resuelve el orquestador desde `.agents/skill-registry.md` (generado por `skill-registry`, versionado en el repo). Esta tabla solo mapea skill→rol.

---

## Roadmap de Changes

El plan de implementación completo está en [CHANGES.md](CHANGES.md). Resumen:

- **Total**: 13 changes en 7 fases (FASE 0 a FASE 6).
- **Camino crítico** (11): `C-01 → C-02 → C-03 → C-04 → C-06 → C-07 → C-08 → C-09 → C-11 → C-12 → C-13`.
- **Paralelismo**: `C-05` ∥ `C-06` desde GATE 4; `C-09` ∥ `C-10` desde GATE 7 (Agente A / Agente B); Agente C es QA.
- **Primer change**: `C-01` (`foundation-setup`) — no depende de nada.

**Antes de cualquier `/opsx:propose`**: leé [CHANGES.md](CHANGES.md), identificá las dependencias del change y los archivos de "Leer antes".

---

## Reglas Duras

> Reglas **globales** ya definidas en `~/.claude/CLAUDE.md` (orquestador OPSX, delegación, governance por dominio, engram, Strict TDD, workflow): el proyecto las **hereda**, no se repiten acá.

Son contrato; romperlas es un defecto. Formato `NUNCA X → hacer Y`:

**Dinero, fechas y datos**
- NUNCA usar `float` para dinero → `Decimal` en Python y `NUMERIC(10,2)` en la base; en los contratos de respuesta el dinero viaja como **string** Decimal.
- NUNCA fechas naive → `timestamptz` en todas las columnas de fecha; `password_cambiada_en` con hora completa timezone.

**Persistencia y arquitectura**
- NUNCA `create_all` ni migraciones manuales → esquema **solo** con Alembic (plantilla asincrónica); verificar ciclo `upgrade head → downgrade base → upgrade head`.
- NUNCA `commit()` en un repositorio → `add`/`update` hacen `flush()` únicamente; **el Unit of Work confirma** (o revierte) y nunca cierra la sesión.
- NUNCA construir el UoW dentro del servicio → el router lo arma con una dependencia y se lo pasa abierto; el servicio lo abre con `async with`.
- NUNCA crear el motor o la fábrica de sesiones al importar un módulo → van en el **lifespan**, en `app.state`; `get_session` entrega sesión con `expire_on_commit=False`.
- NUNCA lazy loading en lecturas → carga anticipada (`selectinload`/`joinload`) con número **fijo** de consultas (verificar con `SQL_ECHO`, caso C-15).
- NUNCA `float`/entrega de unicidad por consulta previa → la unicidad entre vigentes se garantiza con los **índices únicos parciales** (`WHERE borrado_en IS NULL`, roles vigentes).

**Autenticación y autorización**
- NUNCA token en header Bearer ni en localStorage → el JWT viaja **solo** en cookie `access_token` HttpOnly, SameSite=Lax, Secure configurable (caso C-03).
- NUNCA confiar el rol en el cliente → `requiere_rol` consulta `asignacion_rol` **en cada petición** (vigente: no revocada y sin vencer).
- NUNCA exponer `password_hash` en ninguna respuesta → y ninguna entrada inválida termina en 500 (422 de contrato, 409 de integridad).
- NUNCA devolver el texto crudo de `IntegrityError` → traducir a **409 con mensaje propio** (RN-18).
- NUNCA calcular el hash del login si el límite de intentos ya se alcanzó → primero RN-08 (429 con `Retry-After`), después la verificación; login con correo inexistente responde **igual** que con hash correcto (hash ficticio, RN-09).

**SQL e índice**
- NUNCA concatenar SQL → parámetros ligados en todos los filtros y la búsqueda `q` (caso C-16: `' OR '1'='1` debe devolver lista vacía).
- NUNCA CHECK con signo ambiguo → `movimiento_stock.cantidad <> 0` e `historial_precio_repuesto.precio_nuevo <> precio_anterior` (IN-01/IN-02, confirmar contra el PDF).

**Proceso**
- NUNCA commitear ni pushear sin pedido explícito del usuario; los commits usan convención **Conventional Commits** (`feat:`, `fix:`, `test:`, `chore:`) **sin trailers de co-autoría IA**.
- NUNCA agregar dependencias fuera del stack cerrado de la consigna → cualquier adición (hoy solo el bloque de testing de `C-05`) se propone y espera confirmación.
- NUNCA arrancar un change respetando el orden de CHANGES.md → verificar siempre que sus dependencias estén archivadas en `openspec/changes/archive/`.

---

## Flujo de Trabajo

```
1. Leer la KB relevante (knowledge-base/)        → entender el dominio
2. Identificar el change en CHANGES.md           → respetar dependencias
3. /opsx:propose C-NN-nombre                     → proposal + design + specs + tasks
4. Implementar las tasks (cargando skills)       → respetando las reglas duras
5. /opsx:archive C-NN-nombre + marcar [x]        → cerrar el change
```

Aplicar TODAS las reglas duras en cada paso. Ante conflicto entre la KB y este archivo, las reglas duras prevalecen.
