# CHANGES — Secuencia de Implementación

> Índice canónico de todos los changes del proyecto **API Taller Mecánico (Programación III — TP Cap 1–6)**.
> Cada change es atómico: un agente puede implementarlo en una sesión (~4-6 horas).
> **Leer este archivo antes de ejecutar cualquier `/opsx:propose`.**

> **Nota de re-generación**: se incorpora el constraint de testing automatizado (addito sobre la consigna, que sólo pide `.http`). Nuevo change `C-05 test-infrastructure` (pytest + pytest-asyncio + httpx); los ex-C-05..C-12 pasan a C-06..C-13. Total: **13 changes**. El stack de la consigna sigue cerrado (sin Redis, sin Docker, sin ORM alternativo).

---

## Cómo usar este documento

1. Identificar el change a implementar (verificar que sus dependencias están en `openspec/changes/archive/`).
2. Leer los docs de la knowledge-base indicados en "Leer antes".
3. Ejecutar `/opsx:propose <nombre-del-change>`.
4. Al terminar el change, archivarlo con `/opsx:archive <nombre-del-change>`.
5. Marcar el checkbox `[x]` en este archivo.

---

## Árbol de dependencias

```
C-01 foundation-setup
  └── C-02 core-persistence
        └── C-03 domain-models
              └── C-04 migrations-and-seed
                    │
                    ├── C-05 test-infrastructure            [Agente C]  ← paralelo con C-06
                    └── C-06 contracts-and-errors           [Agente A]
                          │
                          └── C-07 auth                     ← exige C-05 ✓ + C-06 ✓
                                └── C-08 authorization-rbac
                                      │
                                      ├── C-09 clientes-vehiculos     [Agente A]
                                      └── C-10 repuestos-stock        [Agente B]   ← paralelo con C-09
                                            │
                                            └── C-11 ordenes-trabajo   [Agente A — si C-09 ✓ y C-10 ✓]
                                                  └── C-12 detalle-sin-n1
                                                        └── C-13 casos-de-prueba  [Agente C — si C-05 ✓]
```

### Paralelismo por fase

> Cada "gate" es un punto de sincronización. Los changes dentro de un grupo pueden ejecutarse en paralelo.

```
GATE 0: ninguna
  → C-01 foundation-setup                    [Agente A]

GATE 1: C-01 ✓
  → C-02 core-persistence                    [Agente A]

GATE 2: C-02 ✓
  → C-03 domain-models                       [Agente A]

GATE 3: C-03 ✓
  → C-04 migrations-and-seed                 [Agente A]

GATE 4: C-04 ✓                               ← PRIMER FORK (2 paralelos)
  → C-05 test-infrastructure                 [Agente C]
  → C-06 contracts-and-errors                [Agente A]

GATE 5: C-05 ✓ + C-06 ✓                      (cierre de ambas ramas)
  → C-07 auth                                [Agente A]

GATE 6: C-07 ✓
  → C-08 authorization-rbac                  [Agente A]

GATE 7: C-08 ✓                               ← FORK dominio (2 paralelos)
  → C-09 clientes-vehiculos                  [Agente A]
  → C-10 repuestos-stock                     [Agente B]

GATE 8: C-09 ✓ + C-10 ✓
  → C-11 ordenes-trabajo                     [Agente A — si C-09 ✓ y C-10 ✓]

GATE 9: C-11 ✓
  → C-12 detalle-sin-n1                      [Agente A]

GATE 10: C-12 ✓ (+ C-05 ✓ desde GATE 4)
  → C-13 casos-de-prueba                     [Agente C — si C-05 ✓]
```

### Camino crítico (11 changes — mínimo irreducible)

```
C-01 → C-02 → C-03 → C-04 → C-06 → C-07 → C-08 → C-09 → C-11 → C-12 → C-13*
```

\* C-13 es el último change indispensable para la entrega completa del TP (evidencia `.http` + suite automatizada). El fork C-09/C-10 tiene la misma longitud dentro del fork (depende de C-08 y alimenta a C-11); se anota C-09 en el camino por ser la rama que define el módulo base (`vehiculo` → `orden_trabajo`). C-05 corre en paralelo con C-06 desde GATE 4 y ambas ramas se cierran en GATE 5: si C-05 se retrasa más que C-06, entra a formar parte del camino crítico (queda como C-01 → C-04 → **C-05** → C-07 → …).

### Plan óptimo con 3 agentes

> No hay frontend: el sistema es una API. Agente C actúa como QA — levanta la infra de tests (C-05), mantiene la suite pytest incremental y cierra con la evidencia final; Agente B paraleliza la redacción de los `.http` de los changes ya completados.

```
Paso │ Agente A (Backend Core)    │ Agente B (Backend Aux)     │ Agente C (QA / Tests)
─────┼────────────────────────────┼────────────────────────────┼───────────────────────────
  1  │ C-01 foundation-setup      │            —               │            —
  2  │ C-02 core-persistence      │            —               │            —
  3  │ C-03 domain-models         │            —               │            —
  4  │ C-04 migrations-and-seed   │            —               │            —
  5  │ C-06 contracts-and-errors  │            —               │ C-05 test-infrastructure
  6  │ C-07 auth                  │ .http de C-01..C-06        │ pytest de C-06
  7  │ C-08 authorization-rbac    │ .http de C-07              │ pytest de C-07 (auth)
  8  │ C-09 clientes-vehiculos    │ C-10 repuestos-stock       │ pytest de C-08 (RBAC)
  9  │ C-11 ordenes-trabajo       │ .http de C-09 / C-10       │ pytest de C-09 / C-10
 10  │ C-12 detalle-sin-n1        │ .http de C-11              │ pytest de C-11
 11  │            —               │ .http de C-12 (restantes)  │ C-13 casos-de-prueba
```

---

## FASE 0 — Cimientos

> Sin paralelismo posible: cada change es prerrequisito del siguiente. Governance alto al inicio porque todo lo demás se apoya acá.

### [C-01] `foundation-setup`
- **Estado**: `[x]` completado
- **Scope**: Ejercicio 1 del TP (US-001 a US-004) — estructura obligatoria, configuración y ciclo de vida
  - Estructura de directorios exacta de la KB: `main.py`, `seed.py`, `alembic.ini`, `env.example`, `requirements.txt` en raíz; `app/core/` (7 archivos: `config.py`, `database.py`, `security.py`, `dependencies.py`, `repository.py`, `paginacion.py`, `unit_of_work.py`); `app/modules/` con `health`, `usuarios`, `clientes`, `repuestos`, `ordenes` (cada módulo con las 6 capas; `health` sólo `router.py`); `migrations/versions/`; `test/`
  - `Settings` con pydantic-settings: `POSTGRES_USER/PASSWORD/DB/HOST/PORT` + `@computed_field` que arma la URL con driver asincrónico; `SECRET_KEY` y `POSTGRES_PASSWORD` **sin default** (la app no arranca si faltan); `BCRYPT_ROUNDS`, duración del token, `COOKIE_SECURE`, `SQL_ECHO`, tamaño del pool
  - `env.example` completo sin secretos; `.env` no versionado; `requirements.txt` con el stack exacto de la consigna (Python 3.12, FastAPI 0.111, SQLModel 0.0.24, SQLAlchemy 2.0 async, asyncpg 0.30, Alembic 1.13, pydantic-settings 2.0, bcrypt 4.0, PyJWT 2.8, uvicorn) — **sin agregados al stack de la consigna** (sin Redis, sin Docker, sin ORM alternativo); las herramientas de testing (pytest + pytest-asyncio + httpx) se agregan como bloque aparte en `C-05 test-infrastructure`
  - `main.py` mínimo: app FastAPI con lifespan (motor + fábrica en `app.state`, hash ficticio del lifespan, `dispose()` al apagar) y los **dos grupos de rutas** (abierto/prototipo protegido) montando sólo `health`
  - `GET /health/live` (no toca la base) y `GET /health/ready` (`SELECT 1`, 503 si no contesta)
  - `app/core/database.py`: `get_session` desde `app.state`, `expire_on_commit=False`, cierra al terminar
- **Dependencias**: ninguna
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios, §Variables de entorno
  - `knowledge-base/02_descripcion_general.md` §Stack tecnológico, §Arquitectura general
  - `knowledge-base/06_funcionalidades.md` Épica 1 (US-001 a US-004)
  - `knowledge-base/01_vision_y_objetivos.md` §Alcance v1.0 (condición dura de arranque)

---

### [C-02] `core-persistence`
- **Estado**: `[x]` completado
- **Scope**: Ejercicio 6 (repositorios y UoW) — capa base, previa a cualquier modelo o endpoint
  - `app/core/repository.py`: `BaseRepository[T]` (recibe sesión y **clase del modelo** en el constructor; `add`/`update` con `flush()` **nunca** `commit()`) y `SoftDeleteRepository[T]` (hereda, filtra `borrado_en`, `get_by_id_including_deleted`, `soft_delete`)
  - `app/core/unit_of_work.py`: `UnitOfWork` base como gestor de contexto asincrónico — confirma al salir sin excepción, revierte con excepción, **no cierra la sesión** (no la creó); expone la misma sesión a todos sus repositorios
  - `app/core/paginacion.py`: envoltorio `{items, total, page, size, pages}`; `page` ≥ 1, `size` 1–100 default 20; página fuera de rango → error 422 con mensaje propio; `total` con los mismos filtros que la página
  - `app/core/security.py`: primitivas bcrypt (`hash_password`/`verify_password` con `asyncio.to_thread` + semáforo configurable, costo desde `Settings`) y JWT (`crear_token`/`verificar_token` con `sub`, `iat` **sin truncar**, `exp`, roles vigentes) — sin endpoints todavía
  - Comentario explícito de la regla: ningún repositorio confirma; ningún servicio construye su UoW
- **Dependencias**: `C-01`
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/08_arquitectura_propuesta.md` §Patrones aplicados, §Requisitos no funcionales
  - `knowledge-base/02_descripcion_general.md` §Arquitectura general (flujo Router→Service→UoW→Repository)
  - `knowledge-base/06_funcionalidades.md` Épica 6 criterios de aceptación transversales (US-025 CA-2)
  - `knowledge-base/09_decisiones_y_supuestos.md` DD-08, DD-09

---

## FASE 1 — Modelo y esquema (Ejercicio 2)

### [C-03] `domain-models`
- **Estado**: `[ ]` pendiente
- **Scope**: Ejercicio 2 (US-005) — los 13 modelos SQLModel con todas las restricciones, **nombres de tablas y columnas obligatorios**
  - Módulo `usuarios`: `usuario`, `asignacion_rol` (CHECK rol en `ADMIN, RECEPCION, MECANICO, CLIENTE`; **índice único parcial** `(usuario_id, rol) WHERE revocada_en IS NULL`), `intento_acceso` (índice `(email, ip, cuando)`), `evento_seguridad`
  - Módulo `clientes`: `cliente` (`usuario_id` UNIQUE nulo, `documento` UNIQUE), `vehiculo` (**índice único parcial** `(patente) WHERE borrado_en IS NULL`; CHECK `anio BETWEEN 1950 AND 2100`)
  - Módulo `repuestos`: `repuesto` (**índice único parcial** `(codigo) WHERE borrado_en IS NULL`; CHECK `precio > 0`, `stock >= 0`; `NUMERIC(10,2)`), `movimiento_stock` (CHECK `cantidad <> 0` — ver IN-01), `historial_precio_repuesto` (CHECK `precio_nuevo > 0` y `precio_nuevo <> precio_anterior` — ver IN-02)
  - Módulo `ordenes`: `estado_orden` (PK `codigo`, `posicion` UNIQUE, `es_final`), `orden_trabajo` (FK estado→`estado_orden.codigo`, CHECK `total >= 0`), `item_orden` (UNIQUE `(orden_id, repuesto_id)`, CHECK cantidad/precio > 0; composición), `historial_estado_orden` (FKs a catálogo)
  - Navegación declarada en **ambos extremos** de cada relación leída; `Usuario.cliente` devuelve **objeto**, no lista; `Decimal` para dinero (nunca `float`); `timestamptz` en todas las fechas
  - FKs: toda clave foránea lleva índice explícito (PostgreSQL no lo crea solo)
- **Dependencias**: `C-02`
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` (completo — nombres obligatorios)
  - `knowledge-base/05_reglas_de_negocio.md` RN-01, RN-03, RN-19; §Excepciones generales (Dinero/Fechas)
  - `knowledge-base/10_preguntas_abiertas.md` IN-01, IN-02 — **resueltas**: los CHECK se escriben `cantidad <> 0` y `precio_nuevo <> precio_anterior` (verificado contra el PDF original)
  - `knowledge-base/09_decisiones_y_supuestos.md` DD-01, DD-02, DD-03

---

### [C-04] `migrations-and-seed`
- **Estado**: `[ ]` pendiente
- **Scope**: Ejercicio 2 (US-006) — esquema versionado sólo con Alembic + datos iniciales
  - Alembic con **plantilla asincrónica**; `create_all` prohibido
  - **Migración 1** generada con `--autogenerate`: las 13 tablas, índices, UNIQUEs, CHECKs e índices únicos parciales (`postgresql_where`); el catálogo `estado_orden` queda **vacío**
  - **Migración 2 escrita a mano**: función + disparador de **sólo agregado** que rechaza UPDATE y DELETE sobre `historial_estado_orden`, `movimiento_stock` e `historial_precio_repuesto` (RN-15); con comentario de que debe leerse antes de aplicarse (DD-14)
  - Ciclo verificado: `alembic upgrade head` sobre base vacía → `downgrade base` → `upgrade head`
  - `seed.py` en raíz: **vacía las tablas** y carga el catálogo (PENDIENTE 1, EN_REPARACION 2, TERMINADA 3 final, CANCELADA 4 final), los 7 usuarios del seed (incl. `nuevo@example.com` con `debe_cambiar_password`), clientes Laura (con usuario) y Jorge (sin usuario) + 3 vehículos, 4 repuestos con «Stock inicial» como movimiento, 2 órdenes (la 2 con 4 bujías cuando hay 2 — caso C-11), historial de precios del filtro y evento de seguridad `actor='SISTEMA'`
- **Dependencias**: `C-03`
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/04_modelo_de_datos.md` §Seed data inicial, §Índices únicos parciales
  - `knowledge-base/05_reglas_de_negocio.md` RN-15, RN-19
  - `knowledge-base/09_decisiones_y_supuestos.md` DD-10, DD-14
  - `knowledge-base/07_flujos_principales.md` Flujo 13

---

## FASE 2 — Andén de pruebas automatizadas (adicional a la consigna)

> **Addito sobre la consigna**: el PDF sólo pide `.http` y `solo_agregado.sql` en `test/`. Este change instala el framework que los changes siguientes usan para **automatizar/replicar** esa misma cobertura. Corre en paralelo con `C-06` desde GATE 4 (C-06 no depende de C-05 en su código; sí en sus tests pytest).

### [C-05] `test-infrastructure`
- **Estado**: `[ ]` pendiente
- **Scope**: Framework de tests automatizados para el stack asincrónico — pytest + pytest-asyncio + httpx (decisión delegada por el usuario; el trío es el estándar del ecosistema FastAPI asincrónico)
  - `requirements.txt`: bloque `# --- testing (adicional a la consigna) ---` con `pytest>=8`, `pytest-asyncio>=0.24`, `httpx>=0.27` — **única** adición al stack cerrado del PDF (sigue sin Redis, sin Docker, sin ORM alternativo, sin mocks ni DB-fakes; la suite corre contra **PostgreSQL 16 real** porque la consigna quiere probar la base de verdad)
  - `test/pytest.ini` — todo vive dentro de `test/`, la estructura obligatoria de la raíz **no cambia**: `asyncio_mode = auto`, `pythonpath = .` (nativo de pytest ≥7, sin plugins extra), `testpaths`; corrida estándar `python -m pytest test/` desde la raíz
  - `test/conftest.py`: variables de test cargadas **antes** de importar la app (`SECRET_KEY` de prueba, `COOKIE_SECURE=false`, `POSTGRES_DB` → `<db>_test`); fixture session-scoped que crea la DB de test si no existe y aplica `alembic upgrade head` una vez; fixture function-scoped que restaura el estado base re-corriendo `seed.py` (vacía y recarga) por test — sin transacciones trucadas ni dobles sesiones
  - Cliente ASGI: fixture `client` con `httpx.AsyncClient` + `ASGITransport(app)` (reemplaza al `TestClient` síncrono: ejercita los handlers `async` de verdad); el lifespan de la app se maneja con `app.router.lifespan_context(app)` — evita la dependencia `asgi-lifespan`
  - Helper `login(email, password)` que devuelve la cookie `access_token` por usuario/rol (fixtures de roles ADMIN/RECEPCION/MECANICO/CLIENTE listas; se ejercitan desde `C-07`)
  - Smoke tests: `GET /health/live` → 200 y `GET /health/ready` → 200/503 (caso C-01 automatizado) — único endpoint existente en este punto
  - Excluido por diseño: factory-boy, respx/mocks de red (no hay APIs externas), sqlite o repos falsos, testcontainers/Docker — nada de eso cabe en el stack ni aporta contra una consigna que exige PostgreSQL real
  - Convención: de aquí en más cada change agrega su `test/test_<change>.py` réplica de sus `.http`; la suite automatiza la cobertura, los `.http` siguen siendo la **evidencia pedida** por la consigna
- **Dependencias**: `C-04`
- **Governance**: BAJO
- **Leer antes**:
  - `knowledge-base/08_arquitectura_propuesta.md` §Estructura de directorios (`test/`), §Requisitos no funcionales (Asincronía)
  - `knowledge-base/01_vision_y_objetivos.md` §Alcance v1.0 (`.http` obligatorios), §Métricas de éxito
  - `knowledge-base/02_descripcion_general.md` §Stack tecnológico (base del stack cerrado al que se agrega el bloque de testing)
  - `knowledge-base/10_preguntas_abiertas.md` (Casos de prueba C-01 a C-19)
  - `knowledge-base/07_flujos_principales.md` Flujo 13 (ensayo final)

---

## FASE 3 — Contratos y Autenticación (Ejercicios 3 y 4)

> GATE 4: `C-06` y `C-05` se ejecutan en paralelo; `C-07` exige ambas ramas (código de contratos + andén de tests).

### [C-06] `contracts-and-errors`
- **Estado**: `[ ]` pendiente
- **Scope**: Ejercicio 3 (US-007, US-008) — patrones de contratos y manejo de errores, aplicados a los contratos base de `usuarios` y `repuestos`
  - `app/modules/usuarios/schemas.py` y `app/modules/repuestos/schemas.py`: contratos de entrada con `extra="forbid"`; ninguna respuesta incluye `password_hash`; campos de dinero como string Decimal; contraseñas con límite **≤ 72 bytes** validado en contrato (422, no 500)
  - Convención de PATCH: `exclude_unset` — sólo cambia lo enviado
  - Manejo de errores central: traducción de `IntegrityError` a **409 con mensaje propio** (nunca el texto de la base ni traza — RN-18); 404 si el recurso de la ruta no existe; 422 de Pydantic; ninguna entrada inválida termina en 500
  - Listados con el envoltorio de `C-02` aplicado al menos a un caso de prueba (`GET /repuestos` stub o evento futuro); página fuera de rango → 422
  - Búsqueda `q` con **parámetros ligados** (nunca concatenación)
  - `Tests .http`: 422 de `extra="forbid"`, contraseña > 72 bytes, página fuera de rango
  - `Tests pytest` (requiere `C-05` ✓ — corre en paralelo): réplica automatizada de los `.http` anteriores sobre `test/test_contracts.py`
- **Dependencias**: `C-04` (los tests pytest de este change requieren `C-05` ✓)
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` Épica 3 (US-007, US-008)
  - `knowledge-base/02_descripcion_general.md` §Ejemplos de contrato
  - `knowledge-base/08_arquitectura_propuesta.md` §Validación de input, §Errores
  - `knowledge-base/05_reglas_de_negocio.md` RN-18

---

### [C-07] `auth`
- **Estado**: `[ ]` pendiente
- **Scope**: Ejercicio 4 (US-009 a US-012) — autenticación completa en el módulo `usuarios`
  - `POST /auth/registro` (abierto): crea usuario + `asignacion_rol` CLIENTE + ficha `cliente` en **un solo UoW** (RN-02); hash **antes** de abrir la transacción y fuera del bucle; documento/email repetido → 409 sin apropiarse de la ficha; 201
  - `POST /auth/login` (abierto): **orden** — primero límite de intentos (RN-08): ≥ 5 fallos con mismo `(email, ip)` en 60 s → 429 con `Retry-After` **sin calcular hash**; luego verificación contra el hash del usuario o contra el **hash ficticio** del lifespan si el correo no existe (RN-09 — misma respuesta y duración); cada intento se anota en `intento_acceso` **en sesión y transacciones propias siempre confirmadas** (DD-09, con comentario declarándolo); login correcto emite JWT (`sub`, `iat` sin truncar, `exp`, roles vigentes) en cookie `access_token` HttpOnly, SameSite=Lax, Max-Age = duración, Secure configurable; cuerpo 200 **sin token**: `{mensaje, debe_cambiar_password, expira_en_segundos}`
  - `POST /auth/logout`: borra la cookie (200)
  - `GET /auth/yo`: usuario, roles vigentes y roles del token (200/401)
  - `POST /auth/cambiar-password`: verifica actual; nueva ≤ 8 y ≤ 72 bytes según contrato; anota `password_cambiada_en` con hora completa (timezone); emite token **nuevo después** del cambio (RN-07)
  - Bearer/Authorization **no** sirve — sólo cookie (caso C-03 de la consigna)
  - `Tests .http`: registro OK/repetido, login OK/mal/429, hash ficticio, cookie vs Bearer, cambio invalida tokens previos
  - `Tests pytest` (`test/test_auth.py`, réplica de los `.http`): registro documento repetido → 409 (caso C-02), cookie vs Bearer → 401 (caso C-03), cambio de contraseña invalida el token previo (caso C-04), 429 con `Retry-After` (caso C-05), hash ficticio idéntico en respuesta y duración (RN-09) — primer uso real de los fixtures `client`/`login` de `C-05`
- **Dependencias**: `C-05, C-06`
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` Épica 4 (US-009 a US-012)
  - `knowledge-base/07_flujos_principales.md` Flujos 2, 3, 4
  - `knowledge-base/05_reglas_de_negocio.md` RN-02, RN-07, RN-08, RN-09
  - `knowledge-base/09_decisiones_y_supuestos.md` DD-04, DD-08, DD-09

---

## FASE 4 — Autorización (Ejercicio 5)

### [C-08] `authorization-rbac`
- **Estado**: `[ ]` pendiente
- **Scope**: Ejercicio 5 (US-013 a US-016) — RBAC decidido en la base y administración de personal
  - `app/core/dependencies.py`: `get_usuario_actual` (lee cookie; 401 si sin cookie/token inválido/vencido/usuario inactivo/`iat` anterior a `password_cambiada_en` **sin truncar**); `requiere_rol(...)` consulta `asignacion_rol` **en cada petición** (roles vigentes: no revocada y sin vencer — RN-04); control de `debe_cambiar_password` (403)
  - `main.py`: **dos grupos de rutas** con el control del cambio obligatorio montado **una sola vez** en el protegido (DD-05); re-montar `auth` y `health` en el grupo abierto
  - `POST /usuarios` (ADMIN): alta de personal con contraseña provisoria → `debe_cambiar_password=True`; evento de seguridad
  - `GET/POST /usuarios/{id}/roles` y `DELETE /usuarios/{id}/roles/{rol}` (ADMIN): asignar con `desde`/`vence_en` opcional (**con zona horaria y en el futuro**; sin zona o pasado → 422); asignación abierta repetida → 409 (índice parcial); reasignar rol vencido cierra y abre fila nueva; revocar escribe `revocada_en` **sin borrar**; autoprotección RN-05 (no revocarse el propio ADMIN ni dejar 0 ADMINs vigentes) → 409
  - `GET /eventos` (ADMIN, paginado)
  - Registro de `evento_seguridad` en altas, cambios de rol y de contraseña (actor texto, incluye `'SISTEMA'`)
  - `Tests .http`: 401 vs 403, revocación efecto inmediato, 422 de vence_en, autoprotección
  - `Tests pytest` (`test/test_rbac.py`): 401 vs 403, revocación con efecto inmediato (caso C-07), autoprotección → 409 (caso C-08), `vence_en` sin zona o pasado → 422
- **Dependencias**: `C-07`
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/03_actores_y_roles.md` (matriz completa, §Reglas que cruzan la matriz)
  - `knowledge-base/06_funcionalidades.md` Épica 5 (US-013 a US-016)
  - `knowledge-base/07_flujos_principales.md` Flujos 5, 6
  - `knowledge-base/05_reglas_de_negocio.md` RN-03 a RN-06

---

## FASE 5 — Dominio del taller (Ejercicio 6 aplicado)

> GATE 7 — los dos módulos de soporte se implementan en paralelo; C-11 espera a ambos.

### [C-09] `clientes-vehiculos`
- **Estado**: `[ ]` pendiente
- **Scope**: Épica 6 (US-017 a US-019) — módulo `clientes` completo (6 capas)
  - `POST /clientes` (RECEPCION, ADMIN): 201/409 (documento único)/422
  - `GET /clientes/{id}` (RECEPCION, ADMIN): ficha **con vehículos** por carga anticipada en el repositorio (sin lazy loading)
  - `POST /clientes/{id}/vehiculos`: 201/404/409 (patente vigente duplicada)/422 (año)
  - `DELETE /vehiculos/{id}` (RECEPCION, ADMIN): baja lógica `borrado_en` → 204; con órdenes **abiertas** (`es_final=false`) → 409
  - `GET /mis-vehiculos` (autenticado): sólo los del cliente dueño de la sesión (RN-17)
  - `SoftDeleteRepository` en uso; unicidad entre vigentes garantizada por el índice parcial (sin consulta previa)
  - `Tests .http`: alta cliente/vehículo, patente repetida tras baja (C-19), baja con orden abierta
  - `Tests pytest` (`test/test_clientes.py`): réplica de los `.http` — patente repetida tras baja (caso C-19), baja con orden abierta → 409, aislamiento de `/mis-vehiculos`
- **Dependencias**: `C-08`
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` Épica 6 (US-017, US-018, US-019)
  - `knowledge-base/07_flujos_principales.md` (patrón de módulo; sin flujo propio dedicado)
  - `knowledge-base/04_modelo_de_datos.md` §cliente, §vehiculo
  - `knowledge-base/05_reglas_de_negocio.md` RN-01, RN-16, RN-17

---

### [C-10] `repuestos-stock`
- **Estado**: `[ ]` pendiente
- **Scope**: Épica 7 (US-020 a US-022) — módulo `repuestos` completo con auditoría de stock y precios
  - `GET /repuestos` (`q`, `page`, `size`) para ADMIN/RECEPCION/MECANICO: búsqueda con parámetros ligados; `' OR '1'='1` → lista vacía `total: 0` (C-16)
  - `GET /repuestos/{id}`: 200/404
  - `POST /repuestos` (ADMIN) con `stock_inicial`: 201; deja un `movimiento_stock` «Stock inicial» en el mismo UoW
  - `PATCH /repuestos/{id}` (ADMIN): **sólo** `descripcion` y `precio`; `exclude_unset`; si `stock` viene en el cuerpo → **422**; si el precio cambió, en el **mismo UoW** inserta línea en `historial_precio_repuesto` (anterior/nuevo/usuario/cuando); PATCH sin cambio de precio **no** deja línea (C-18, RN-20)
  - `DELETE /repuestos/{id}` (ADMIN): borrado lógico → 204
  - `POST /repuestos/{id}/reponer` (ADMIN): 200; incrementa stock y deja movimiento (punto único de escritura — RN-14)
  - `GET /repuestos/{id}/movimientos` y `GET /repuestos/{id}/precios` (sólo ADMIN): 200/404
  - `Tests .http`: B-01 a B-04 del enunciado (stock no editable, precio historiado, recepción 403 en admin)
  - `Tests pytest` (`test/test_repuestos.py`): B-01 a B-04 automatizados — `stock` en PATCH → 422 (caso C-16), precio historiado y PATCH sin cambio sin línea (caso C-18), `q` con inyección → `total: 0`, `reponer` deja movimiento
- **Dependencias**: `C-08`
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` Épica 7 (US-020, US-021, US-022)
  - `knowledge-base/07_flujos_principales.md` Flujo 11
  - `knowledge-base/04_modelo_de_datos.md` §repuesto, §movimiento_stock, §historial_precio_repuesto
  - `knowledge-base/05_reglas_de_negocio.md` RN-14, RN-15, RN-20

---

### [C-11] `ordenes-trabajo`
- **Estado**: `[ ]` pendiente
- **Scope**: Épica 8 (US-023, US-024, US-026) — módulo `ordenes` con la transacción multi-escritura del TP
  - `POST /ordenes` (RECEPCION, ADMIN): contrato `{vehiculo_id, falla, items:[{repuesto_id, cantidad}]}` con `extra="forbid"` — **no** acepta precio/total/estado/fecha; nace PENDIENTE; ≥ 1 ítem; sin repuestos repetidos; precio copiado del repuesto; total calculado con `Decimal` en el servidor; catálogo vacío → 409; vehículo baja o repuesto inexistente/baja → 409 **sin dejar la orden** (C-10); 201 con precio, total y primera línea de historial
  - `POST /ordenes/{id}/iniciar` (MECANICO): PENDIENTE→EN_REPARACION, asigna `mecanico_id` = usuario actual, línea de historial, 200
  - `POST /ordenes/{id}/terminar` (mecánico asignado o ADMIN): **403 (identidad) antes que 409 (estado)** (SU-04); EN_REPARACION→TERMINADA; en **un solo UoW**: descuenta cada `item_orden`, un `movimiento_stock` por salida, línea de historial; stock insuficiente → error antes de escribir más, rollback total, 409 (C-11, RN-13)
  - `POST /ordenes/{id}/cancelar` (RECEPCION, ADMIN o dueño — **sin** `requiere_rol`, DD-06): servicio evalúa identidad (403) **antes** que estado PENDIENTE (409), historial, 200
  - `GET /ordenes` (`estado` filtrado contra enum del contrato → estado no declarado = 422, C-17), paginado, para ADMIN/RECEPCION/MECANICO
  - `GET /ordenes/{id}`: personal o dueño del vehículo (dueño ajeno → 403, C-06)
  - `GET /estados-orden`: catálogo por posición, con finales marcados (repositorio de sólo lectura sin `BaseRepository` — DD-07)
  - `GET /mis-ordenes` (autenticado): órdenes de los vehículos del cliente (RN-17)
  - `BackgroundTasks` en `terminar`: aviso simulado `await asyncio.sleep(0.5)` + log, **después** de la respuesta y **sólo si** se confirmó (C-12, DD-13); todos los handlers `async def`, sin llamadas bloqueantes
  - `Tests .http`: A-01 a A-04, C-10, C-11, C-13
  - `Tests pytest` (`test/test_ordenes.py`): catálogo vacío → 409 (caso C-09), repuesto inexistente no deja la orden (caso C-10), rollback total por stock insuficiente (caso C-11), 403 por identidad antes que 409 por estado (SU-04), `estado` no declarado → 422 (caso C-17), cancelar TERMINADA → 409 (caso C-13)
- **Dependencias**: `C-09, C-10`
- **Governance**: CRITICO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` Épica 8 (US-023, US-024, US-026)
  - `knowledge-base/07_flujos_principales.md` Flujos 7, 8, 9, 10
  - `knowledge-base/05_reglas_de_negocio.md` RN-10 a RN-13, RN-19
  - `knowledge-base/09_decisiones_y_supuestos.md` DD-01, DD-06, DD-07, DD-13, SU-04

---

## FASE 6 — Calidad de lectura y entrega (Ejercicio 8 + ensayo final)

### [C-12] `detalle-sin-n1`
- **Estado**: `[ ]` pendiente
- **Scope**: Ejercicio 8 (US-025) — lecturas con número fijo de consultas y asincronía
  - `GET /ordenes/{id}`: vehículo + cliente + ítems + repuesto de cada ítem + historial resueltos con número **fijo** de consultas (selectinload/joinload en el repositorio); verificar con `SQL_ECHO=true` que 2 y 4 ítems dan las **mismas** consultas (C-15)
  - `GET /clientes/{id}` y `/mis-vehiculos` / `/mis-ordenes`: mismas precargas — ninguna lectura depende de carga perezosa
  - Auditoría asincrónica: ningún handler ejecuta IO bloqueante (bcrypt ya va con `to_thread`; no introducir llamadas síncronas)
  - Aviso `BackgroundTasks` revisado: corre post-respuesta y sólo si la operación se confirmó
  - Registro en consola de consultas habilitable (`SQL_ECHO`)
  - `Tests pytest` (`test/test_detalle.py`): conteo de consultas con contador `before_cursor_execute` sobre `engine.sync_engine` (sin dependencias extra) — 2 y 4 ítems dan el **mismo** conteo (caso C-15); `BackgroundTasks` corre post-respuesta y sólo si se confirmó (caso C-12)
- **Dependencias**: `C-11`
- **Governance**: MEDIO
- **Leer antes**:
  - `knowledge-base/06_funcionalidades.md` US-025
  - `knowledge-base/08_arquitectura_propuesta.md` §Requisitos no funcionales (Carga perezosa, Asincronía)
  - `knowledge-base/04_modelo_de_datos.md` (nota de navegación en ambos extremos)
  - `knowledge-base/07_flujos_principales.md` Flujo 9 paso 5

---

### [C-13] `casos-de-prueba`
- **Estado**: `[ ]` pendiente
- **Scope**: Entrega del TP — cobertura de los casos C-01 a C-19 (evidencia `.http` exigida) + suite automatizada y verificación integral
  - `test/*.http` con **todos** los casos de la consigna y la respuesta esperada en comentarios: C-01 (health), C-02 (registro documento repetido), C-03 (cookie vs Bearer), C-04 (cambio de contraseña), C-05 (429 login), C-06 (orden ajena 403), C-07 (revocación inmediata), C-08 (autoprotección), C-09 (catálogo vacío), C-10 (repuesto inexistente no deja orden), C-11 (stock insuficiente rollback), C-12 (aviso post-confirmación), C-13 (cancelar terminada), C-15 (N+1 fijo), C-16 (stock por PATCH / SQL injection), C-17 (estado no declarado 422 / catálogo), C-18 (PATCH sin cambio de precio), C-19 (patente tras baja)
  - `test/solo_agregado.sql` (caso C-14): UPDATE y DELETE sobre las tres tablas de auditoría rechazados por el disparador; INSERT de orden con estado fuera del catálogo rechazado por FK — con captura/comentario de psql
  - **Matriz de paridad** `casos C-01..C-19`: cada caso mapeado a su `.http` (evidencia pedida por la consigna) y a su prueba pytest equivalente; los no automatizables quedan justificados (p. ej. C-14 se ejercita con psql — réplica opcional con SQL crudo vía el motor de SQLAlchemy, sin dependencias nuevas)
  - Corrida final de la suite: `python -m pytest test/` en verde contra PostgreSQL real; consolidación de los `.http` que el Agente B adelantó por change
  - Verificación final: ciclo Alembic upgrade/downgrade/upgrade sobre base vacía; `seed.py` reproducible; app arranca sin secretos por defecto; ningún archivo del repo con credenciales reales
  - Checklist de los 8 criterios de evaluación de `01_vision_y_objetivos.md` §Métricas de éxito
- **Dependencias**: `C-12`
- **Governance**: ALTO
- **Leer antes**:
  - `knowledge-base/01_vision_y_objetivos.md` §Métricas de éxito (tabla de evaluación)
  - `knowledge-base/07_flujos_principales.md` Flujo 13
  - `knowledge-base/10_preguntas_abiertas.md` (casos C-01 a C-19 completos)
  - `knowledge-base/03_actores_y_roles.md` (matriz para diseñar los 403)

---

## Resumen

| ID | Change | Fase | Deps | Governance |
|---|---|---|---|---|
| C-01 | foundation-setup | 0 | — | ALTO |
| C-02 | core-persistence | 0 | C-01 | CRITICO |
| C-03 | domain-models | 1 | C-02 | CRITICO |
| C-04 | migrations-and-seed | 1 | C-03 | CRITICO |
| C-05 | test-infrastructure | 2 | C-04 | BAJO |
| C-06 | contracts-and-errors | 3 | C-04 (+ C-05 para tests) | MEDIO |
| C-07 | auth | 3 | C-05, C-06 | CRITICO |
| C-08 | authorization-rbac | 4 | C-07 | ALTO |
| C-09 | clientes-vehiculos | 5 | C-08 | MEDIO |
| C-10 | repuestos-stock | 5 | C-08 | MEDIO |
| C-11 | ordenes-trabajo | 5 | C-09, C-10 | CRITICO |
| C-12 | detalle-sin-n1 | 6 | C-11 | MEDIO |
| C-13 | casos-de-prueba | 6 | C-12 | ALTO |

**Primer change recomendado**: `C-01` (`foundation-setup`) — no depende de nada y habilita toda la cadena.

Para arrancar: `/opsx:propose C-01-foundation-setup`
