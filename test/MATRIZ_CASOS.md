# Matriz de paridad — casos C-01 a C-19

> Entrega del TP (change `C-13 casos-de-prueba`). Cada caso de la consigna tiene
> su **evidencia ejecutable** (`.http` o `.sql`, que es lo que pide el PDF) y su
> **réplica automatizada** en pytest (adicional del proyecto). Esta matriz es el
> índice: dice dónde vive cada cosa y en qué estado está.
>
> - Evidencia HTTP: archivos `.http` de `test/` (bloques numerados con `###`).
> - Evidencia SQL: `test/solo_agregado.sql` (caso C-14, Flujo 13).
> - Suite: `python -m pytest test/ -q` desde la raíz (PostgreSQL real).

## 1. Cómo se corre la evidencia

```powershell
# 1. Base migrada y sembrada
alembic upgrade head
python seed.py

# 2. App levantada (otra terminal)
uvicorn main:app --reload

# 3. Bloques .http: abrir el archivo en el cliente HTTP del IDE (REST Client,
#    IntelliJ HTTP Client, etc.) y ejecutar de arriba hacia abajo. Los bloques 0
#    de login dejan la cookie `access_token` para el resto del archivo.

# 4. Caso C-14 (psql, no pasa por la API)
$env:PGPASSWORD="postgres"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost `
    -d taller_mecanico -f test/solo_agregado.sql

# 5. Suite completa
python -m pytest test/ -q
```

**Cada archivo `.http` asume el estado del seed.** Los bloques escriben (altas,
bajas, precios, órdenes) y algunos son destructivos; para repetir un archivo hay
que volver a sembrar:

| Orden sugerido | Archivo | Por qué en ese orden |
|---|---|---|
| 1 | `test/health.http` | No toca datos; sirve para confirmar que la app y la base están de pie. |
| 2 | `test/contracts.http` | Contratos y errores; crea un repuesto `ZZ-999` y un usuario `nuevo-staff@example.com`. |
| 3 | `test/auth.http` | Registro, login, 429, Bearer vs cookie, cambio de contraseña. Consume intentos de login. |
| 4 | `test/rbac.http` | Revoca y reasigna roles; espera los ids 1..7 del seed. |
| 5 | `test/clientes.http` | Da de baja `AAB222` y la vuelve a registrar (C-19). |
| 6 | `test/repuestos.http` | Cambia precios, repone stock y da de baja `FA-001`. |
| 7 | `test/ordenes.http` | Último: crea y termina órdenes y el bloque 22 vacía el catálogo (`TRUNCATE estado_orden CASCADE`). |

Después de `test/ordenes.http` (bloque 22) la base queda sin catálogo: **siempre**
`python seed.py` antes de volver a empezar.

## 2. Casos C-01 a C-19

| Caso | Qué verifica | Evidencia `.http` (archivo + bloque) | Prueba pytest | Estado |
|---|---|---|---|---|
| **C-01** | `GET /health/live` no toca la base (200) y `GET /health/ready` ejecuta `SELECT 1` (200; 503 si la base no contesta). Además: la app no arranca sin `SECRET_KEY`/`POSTGRES_PASSWORD`. | `test/health.http` — bloques 0 (arranque sin secretos), 1 (live), 2 (ready), 3 (ready 503) | `test_health.py::test_live_responde_200_sin_tocar_la_base`<br>`test_health.py::test_ready_responde_200_contra_postgres_real`<br>`test_health.py::test_ready_responde_503_si_la_base_no_contesta` | Completo. El 503 del bloque 3 requiere detener el servicio de PostgreSQL; el test lo simula con un doble de `get_session`. |
| **C-02** | Registro con un documento ya usado → 409 y **no se apropia** de la ficha existente (Jorge sigue sin usuario; no quedan usuario ni rol sueltos). | `test/auth.http` — bloque 2 | `test_auth.py::test_registro_documento_repetido_responde_409_y_no_se_apropia` | Completo. |
| **C-03** | `Authorization: Bearer` **no** autentica: el JWT sólo se lee de la cookie `access_token` → 401 sin cookie. | `test/auth.http` — bloque 8 (Bearer) y bloque 9 (misma ruta con cookie → 200) | `test_auth.py::test_authorization_bearer_no_autentica_solo_sirve_la_cookie` | Completo. El bloque 8 exige borrar la cookie antes de enviarlo (documentado en el propio bloque). |
| **C-04** | Cambiar la contraseña emite un token nuevo e **invalida el anterior** sin esperar el vencimiento (`iat` vs `password_cambiada_en`, sin truncar). | `test/auth.http` — bloques 11 (cambio) y 12 (token viejo → 401) | `test_auth.py::test_cambio_de_password_invalida_el_token_anterior_sin_esperar`<br>`test_auth.py::test_token_del_mismo_instante_que_el_cambio_no_vale` | Completo. |
| **C-05** | Cinco fallos con el mismo `(email, ip)` en 60 s → el sexto es **429 con `Retry-After`**, evaluado **antes** de calcular/verificar el hash. Un login correcto reinicia la cuenta. | `test/auth.http` — bloque 7 (repetir 5 veces; el sexto es 429) | `test_auth.py::test_cinco_fallos_activan_429_con_retry_after_sin_calcular_hash`<br>`test_auth.py::test_un_login_correcto_reinicia_la_cuenta_de_fallos` | Completo. |
| **C-06** | Un cliente ve **su** orden (200) y la **ajena** no (403); el personal ve cualquiera. | `test/ordenes.http` — bloques 13.1 (propia 200) y 13.2 (ajena 403) | `test_ordenes.py::test_c06_cliente_ve_su_orden_y_no_la_ajena` | Completo. |
| **C-07** | Revocar un rol tiene efecto **inmediato** sobre una sesión ya abierta: `requiere_rol` consulta `asignacion_rol` en cada petición. Reasignarlo habilita el **mismo** token. | `test/rbac.http` — bloque 5 (token A → 403, reasignar, token A → 200) | `test_rbac.py::test_revocacion_tiene_efecto_inmediato_sobre_la_sesion_abierta` | Completo. |
| **C-08** | Autoprotección: un ADMIN no puede revocarse su propio `ADMIN` (409) y el sistema no puede quedar con 0 ADMIN vigentes (409). | `test/rbac.http` — bloques 12 (propio ADMIN) y 13 (último ADMIN) | `test_rbac.py::test_admin_no_puede_revocarse_su_propio_rol_admin`<br>`test_rbac.py::test_el_sistema_no_queda_sin_administradores_vigentes` | Completo. |
| **C-09** | Con el catálogo `estado_orden` vacío, crear una orden → 409 y **no se escribe nada** (RN-19). | `test/ordenes.http` — bloque 22 (trae el paso previo `TRUNCATE estado_orden CASCADE` en psql y el `python seed.py` para restaurar) | `test_ordenes.py::test_c09_catalogo_vacio_al_crear_responde_409` | Completo con paso previo. El `.http` no puede vaciar el catálogo por API (no hay endpoint que escriba el catálogo: DD-07); por eso el bloque incluye el comando y su salida esperada. |
| **C-10** | Repuesto inexistente (o dado de baja) → 409 y la orden **no queda creada** (ni fila ni ítems). Igual para vehículo inexistente/dado de baja. | `test/ordenes.http` — bloque 9 (repuesto 999999) y bloque 10 (vehículo 999999) | `test_ordenes.py::test_c10_repuesto_inexistente_responde_409_y_no_crea_la_orden`<br>`test_ordenes.py::test_repuesto_dado_de_baja_responde_409_y_no_crea_la_orden`<br>`test_ordenes.py::test_vehiculo_inexistente_responde_409` | Completo. |
| **C-11** | Terminar con stock insuficiente (orden 2: 4 bujías, stock 2) → 409 y **rollback total**: estado, stock, movimientos e historial intactos (RN-13). | `test/ordenes.http` — bloque 11 | `test_ordenes.py::test_c11_terminar_con_stock_insuficiente_no_escribe_nada` | Completo. |
| **C-12** | El aviso al cliente corre **después** de responder y **sólo si** la transición se confirmó (`BackgroundTasks` post-commit, log simulado). | `test/ordenes.http` — bloque 14 (línea de log esperada; bloque 11 muestra el caso sin aviso porque la orden no se terminó) | `test_detalle.py::test_c12_el_aviso_corre_despues_del_commit`<br>`test_ordenes.py::test_terminar_agenda_el_aviso_simulado`<br>`test_ordenes.py::test_terminar_rechazado_no_agenda_el_aviso` | Completo. El `.http` muestra el log (evidencia visible); el test prueba **cuándo** corre abriendo una sesión nueva: ve `TERMINADA`, no `EN_REPARACION`. |
| **C-13** | Una orden TERMINADA no se cancela → 409; una ajena → 403 (identidad antes que estado). | `test/ordenes.http` — bloque 17 (TERMINADA → 409) y 13.5 (ajena → 403) | `test_ordenes.py::test_cancelar_terminada_como_recepcion_responde_409`<br>`test_ordenes.py::test_cancelar_terminada_ajena_como_cliente_responde_403` | Completo. |
| **C-14** | Las tres tablas de auditoría rechazan `UPDATE` y `DELETE` (disparador de la migración 0002); un `estado` fuera del catálogo lo rechaza la FK. Las filas quedan intactas y `TRUNCATE` **no** dispara el disparador. | **No es HTTP**: `test/solo_agregado.sql` — bloques 1/6 a 6/6 (seis rechazos) + INSERT con `INVENTADO` (FK) + conteos finales | `test_solo_agregado.py::test_update_rechazado_por_el_disparador` (×3)<br>`test_solo_agregado.py::test_delete_rechazado_por_el_disparador` (×3)<br>`test_solo_agregado.py::test_insert_con_estado_fuera_del_catalogo_viola_la_fk`<br>`test_solo_agregado.py::test_los_intentos_fallidos_no_escriben_nada`<br>`test_solo_agregado.py::test_truncate_no_dispara_el_disparador_y_el_seed_puede_reiniciar`<br>`test_solo_agregado.py::test_insert_sigue_permitido` | Completo. Es el único caso sin `.http`, por diseño del Flujo 13: el disparador se demuestra en psql (no hay endpoint que intente corregir una fila de auditoría). |
| **C-15** | El detalle se resuelve con un número **fijo** de consultas: 2 y 4 ítems dan las mismas 5 sentencias (sin N+1), y la precarga se declara en el repositorio. | `test/ordenes.http` — bloque 21 (paso previo `SQL_ECHO=true` + crear orden de 2 y de 4 ítems + conteo esperado en la consola) | `test_detalle.py::test_c15_detalle_mantiene_el_conteo_con_2_y_4_items`<br>`test_detalle.py::test_detalle_no_crece_con_las_lineas_de_historial` | Completo con paso previo. El `.http` no puede contar consultas por sí solo: el bloque documenta el comando y la salida esperada; el test mide con `before_cursor_execute` y asserta igualdad, techo y una sola consulta a `item_orden`. |
| **C-16** | El stock **no** se edita por PATCH (422) y la búsqueda `q` usa parámetros ligados: `' OR '1'='1` devuelve `total: 0`, no la lista entera. | `test/repuestos.http` — bloque 5 (PATCH con `stock` → 422) y bloque 2 (inyección → lista vacía); `test/contracts.http` — bloque 5 | `test_repuestos.py::test_patch_con_stock_responde_422`<br>`test_repuestos.py::test_el_stock_no_cambia_cuando_el_patch_falla`<br>`test_repuestos.py::test_busqueda_con_inyeccion_devuelve_lista_vacia`<br>`test_contracts.py::test_busqueda_con_comilla_no_inyecta_sql` | Completo. |
| **C-17** | `GET /ordenes?estado=INVENTADO` → 422 (el filtro se valida contra el enum antes de la base) y `GET /estados-orden` devuelve el catálogo por posición con TERMINADA/CANCELADA finales. | `test/ordenes.http` — bloque 4 (estado no declarado) y bloque 1 (catálogo) | `test_ordenes.py::test_c17_estado_no_declarado_responde_422`<br>`test_ordenes.py::test_estados_orden_por_posicion_y_finales` | Completo. |
| **C-18** | Un cambio de precio deja **una** línea con anterior/nuevo en el mismo UoW; un PATCH posterior con el **mismo** precio no agrega línea (RN-20). | `test/repuestos.http` — bloque 7 (cambio → línea nueva) y bloque 8 (mismo precio → sin línea) | `test_repuestos.py::test_patch_con_precio_nuevo_deja_una_linea_con_el_anterior_y_el_nuevo`<br>`test_repuestos.py::test_patch_con_el_mismo_precio_no_deja_linea`<br>`test_repuestos.py::test_patch_solo_descripcion_no_deja_linea_de_precio` | Completo. |
| **C-19** | Después de la baja lógica de un vehículo, la **misma patente** se puede volver a registrar (201): el índice único parcial sólo mira los vigentes; mientras haya una vigente igual, es 409. | `test/clientes.http` — bloque 9 (baja de `AAB222` → 204, alta de la misma patente → 201, segunda alta → 409) | `test_clientes.py::test_baja_logica_permite_reusar_la_patente_caso_c19` | Completo. |

### Casos que no son 100 % HTTP (y por qué)

| Caso | Qué parte no puede hacer el `.http` | Dónde está esa parte |
|---|---|---|
| C-09 | Vaciar el catálogo: la API es de sólo lectura sobre `estado_orden` (DD-07). | Paso previo `TRUNCATE estado_orden CASCADE` en psql + `python seed.py` para restaurar, comentados en `ordenes.http` bloque 22. |
| C-12 | Ver **cuándo** corre la tarea de fondo (post-commit) no se distingue en el log. | `test_detalle.py::test_c12_el_aviso_corre_despues_del_commit` (sesión nueva: ve `TERMINADA`). |
| C-14 | No hay endpoint que intente corregir una fila de auditoría: el disparador es de base. | `test/solo_agregado.sql` (el `.http` no aplica) + `test/test_solo_agregado.py`. |
| C-15 | Contar consultas no es una aserción HTTP; `SQL_ECHO` imprime, no compara. | Bloque 21 documenta el comando y la salida esperada; `test_detalle.py` mide y asserta. |
| C-01 (503) | Detener PostgreSQL no es parte del protocolo HTTP. | Bloque 3 documenta `Stop-Service`/`Start-Service`; el test usa un doble de `get_session`. |

## 3. Checklist de los 8 criterios de evaluación

`knowledge-base/01_vision_y_objetivos.md` §Métricas de éxito. La condición dura
—el proyecto levanta, crea el esquema con `alembic upgrade head` sobre una base
vacía y no contiene credenciales reales— se verifica en el criterio 1.

| # | Criterio (peso) | Dónde se cumple | Cómo se verificó |
|---|---|---|---|
| 1 | **Proyecto, configuración y ciclo de vida** (8 %) | `main.py` (lifespan con motor y fábrica en `app.state`, `dispose()`), `app/core/config.py` (`Settings` de pydantic-settings, `SECRET_KEY` y `POSTGRES_PASSWORD` sin default), `app/core/database.py` (`get_session`), `app/modules/health/router.py`, `env.example` sin secretos, `.env` fuera de git | `test_health.py` (3), `test_entorno.py` (3), `test_aislamiento.py` (2). Ciclo Alembic sobre base vacía + `git ls-files` sin `.env` (ver `design.md` del change). `python -c "from app.core.config import Settings; print(Settings.model_fields['SECRET_KEY'].is_required(), Settings.model_fields['POSTGRES_PASSWORD'].is_required())"` → `True True`. |
| 2 | **Modelos, relaciones y migraciones** (14 %) | `app/modules/*/models.py` (13 tablas, CHECK, UNIQUE, índices únicos parciales, `lazy="raise_on_sql"`), `migrations/versions/0001_*.py` (esquema) y `0002_solo_agregado.py` (disparador escrito a mano), `alembic.ini` con plantilla asincrónica | `test/test_entorno.py::test_el_esquema_de_test_esta_migrado`; `test_solo_agregado.py` (disparador y FK); `alembic upgrade head → downgrade base → upgrade head` sobre `taller_mecanico_verif` (salida en el resumen del change). |
| 3 | **Contratos y CRUD** (10 %) | `app/modules/*/schemas.py` (`extra="forbid"`, dinero como string Decimal, PATCH con `exclude_unset`), `app/core/errors.py` (IntegrityError → 409, validación → 422, sin trazas), `app/core/paginacion.py` | `test_contracts.py` (19), `test_clientes.py` (14), `test_repuestos.py` (46), `test_ordenes.py` (65). Casos citados: `test_entradas_invalidas_nunca_terminan_en_500`, `test_listado_devuelve_el_envoltorio_uniforme`, `test_patch_aplica_solo_los_campos_enviados`. |
| 4 | **Autenticación** (16 %) | `app/modules/usuarios/auth_service.py` (orden del login: límite → hash; hash ficticio del lifespan; bcrypt en `asyncio.to_thread` con semáforo; cookie HttpOnly/SameSite=Lax), `app/core/security.py`, `app/modules/usuarios/auth_router.py` | `test_auth.py` (19). Casos: `test_login_exitoso_responde_sin_token_y_deja_cookie_httponly`, `test_cinco_fallos_activan_429_con_retry_after_sin_calcular_hash`, `test_correo_inexistente_responde_igual_que_password_mala`, `test_cambio_de_password_invalida_el_token_anterior_sin_esperar`. |
| 5 | **Autorización** (14 %) | `app/core/dependencies.py` (`get_usuario_actual`, `requiere_rol` contra la base en cada petición, `iat` vs `password_cambiada_en`), `main.py` (dos grupos de rutas, control de cambio obligatorio montado una vez), autoprotección RN-05 | `test_rbac.py` (18). Casos: `test_sin_cookie_el_grupo_protegido_responde_401`, `test_cookie_con_rol_insuficiente_responde_403`, `test_requiere_rol_no_confia_en_los_roles_del_token`, `test_revocacion_tiene_efecto_inmediato_sobre_la_sesion_abierta`, `test_admin_no_puede_revocarse_su_propio_rol_admin`. |
| 6 | **Repositorios y Unit of Work** (20 %) | `app/core/repository.py` (dos jerarquías, clase del modelo en el constructor, `flush()` sin `commit()`, precarga en el repositorio), `app/core/unit_of_work.py` (confirma/revierte y no cierra la sesión; lo abre el servicio con `async with`), routers que arman el UoW | `test_ordenes.py` (65, incluye rollback total de C-11 y la transacción multi-escritura de `terminar`), `test_repuestos.py` (precio + historial en el mismo UoW), `test_auth.py` (registro en un solo UoW). `test_aislamiento.py` prueba que el seed deja el estado base a cada test. |
| 7 | **Integridad** (10 %) | `migrations/versions/0002_solo_agregado.py` (disparador en las tres tablas), `historial_precio_repuesto` en el mismo UoW del PATCH, `intento_acceso` en sesión y transacción propias (DD-09) | `test/test_solo_agregado.py` (10) y `test/solo_agregado.sql` (evidencia psql); `test_repuestos.py::test_patch_con_precio_nuevo_deja_una_linea_con_el_anterior_y_el_nuevo`; `test_auth.py::test_cinco_fallos_activan_429_con_retry_after_sin_calcular_hash` (los intentos sobreviven al fallo). |
| 8 | **Lecturas sin N+1 y asincronía** (8 %) | `app/modules/ordenes/repository.py` y `app/modules/clientes/repository.py` (`joinedload`/`selectinload`), relaciones `lazy="raise_on_sql"`, `BackgroundTasks` post-commit en `ordenes/router.py`, `SQL_ECHO` del lifespan | `test_detalle.py` (8): `test_c15_detalle_mantiene_el_conteo_con_2_y_4_items`, `test_detalle_no_crece_con_las_lineas_de_historial`, ficha 1 vs 3 vehículos, `/mis-vehiculos` 2 vs 3, `/mis-ordenes` 1 vs 2, `test_c12_el_aviso_corre_despues_del_commit`, `test_todos_los_handlers_son_coroutines`. |
