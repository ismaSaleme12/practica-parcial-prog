# Tasks

## 1. Configuración y sesión

- [x] 1.1 Agregar `BCRYPT_MAX_CONCURRENT_HASHES: int = 4` a `Settings` y documentarla en `env.example`. Verificación: `python -c "from app.core.config import settings; print(settings.BCRYPT_MAX_CONCURRENT_HASHES)"` con `SECRET_KEY` y `POSTGRES_PASSWORD` en el entorno devuelve `4`, y `env.example` lista la variable.
- [x] 1.2 Cambiar la fábrica de sesiones de `main.py` a `sqlmodel.ext.asyncio.session.AsyncSession` y tipar `get_session` con la misma clase. Verificación: `python -c "import main; print(main.app.state)"` importa sin error y `app/core/database.py` no menciona la sesión de SQLAlchemy en su firma.
- [x] 1.3 Corregir `requirements.txt` a `sqlalchemy[asyncio]>=2.0.0`: desde SQLAlchemy 2.1 `greenlet` ya no se instala por defecto y el modo asíncrono lo requiere (`ModuleNotFoundError: greenlet` al importar `app.core.database`). No es una dependencia nueva del stack: es el extra oficial de SQLAlchemy para async. Verificación: en un `.venv` limpio, `pip install -r requirements.txt` seguido de `python -c "import app.core.database"` funciona sin el `ModuleNotFoundError`.

## 2. Repositorios

- [x] 2.1 Reescribir `BaseRepository[T]` con `get_by_id`, `get_all`, `count`, `list_page`, `add`, `update`, `delete` y `refresh`, donde las escrituras hacen solo `flush()`. Verificación: `python -m py_compile app/core/repository.py` y un script de humo con una sesión falsa que registra llamadas comprueba que `add`/`update`/`delete` hacen `flush()` y **nunca** `commit()`, que `delete` de un id inexistente devuelve `False` y que `get_by_id` delega en la sesión. La comprobación contra PostgreSQL real queda para la suite de `C-05`/`C-13` (no hay credenciales de base en `C-02`).
- [x] 2.2 Reescribir `SoftDeleteRepository[T]`: filtra `borrado_en IS NULL` en lecturas, agrega `get_by_id_including_deleted` y `soft_delete` idempotente. Verificación: script de humo que dé de baja lógica una fila, compruebe que la lectura normal devuelve `None`, que la lectura con borrados la devuelve con `borrado_en` y que una segunda baja devuelve `None`.
- [x] 2.3 Dejar el comentario de la regla dura en `repository.py` (ningún repositorio confirma; el UoW es el único punto de confirmación). Verificación: `grep -n "nunca" app/core/repository.py` muestra la nota en el docstring del módulo.

## 3. Unit of Work

- [x] 3.1 Reescribir `UnitOfWork` como gestor de contexto asincrónico: confirma sin excepción, revierte con excepción, revierte y relanza si falla el `commit`, y nunca cierra la sesión; expone `session` y `repositorio(cls, model)`. Verificación: script de humo con sesión falsa que comprueba (a) salida limpia → un solo `commit` y cero `rollback`, (b) excepción → `rollback` sin `commit` y la excepción se propaga, (c) `commit` fallido → `rollback` y relanza, y (d) en los tres casos la sesión nunca se cierra y `repositorio()` devuelve un repositorio con la misma sesión.
- [x] 3.2 Dejar el comentario de la regla dura en `unit_of_work.py` (ningún servicio construye su UoW; el UoW no cierra la sesión). Verificación: `grep -n "nunca" app/core/unit_of_work.py` muestra la nota.

## 4. Paginación

- [x] 4.1 Reescribir `PageParams` (`page` ≥ 1, `size` 1–100 default 20, 422 con mensaje propio) y `Page[T]` (`items`, `total`, `page`, `size`, `pages`) con `Page.create` calculando `pages` y el 422 de página fuera de rango. Verificación: script de humo que compruebe `page=0` → 422, `size=101` → 422, `total=4, size=2` → `pages=2`, `page=3` → 422 con el mensaje «La página 3 no existe: hay 2» y `total=0` → `pages=0` con `items` vacío.
- [x] 4.2 Conectar `BaseRepository.list_page` con `Page.create` para que `total` use los mismos filtros que la página. Verificación: script de humo que captura las dos sentencias de `list_page`, las compila contra el dialecto PostgreSQL y comprueba que el `count` y la página llevan **el mismo** `WHERE` (`nombre = :param`), que la página aplica `LIMIT`/`OFFSET` y que el repositorio de borrado lógico agrega `borrado_en IS NULL` a ambas consultas.

## 5. Primitivas de seguridad

- [x] 5.1 Reescribir `hash_password`/`verify_password` con `asyncio.to_thread` bajo semáforo configurable y costo desde `Settings`; la verificación devuelve `False` ante un hash malformado. Verificación: script de humo que hashee y verifique una contraseña, compruebe `False` con otra distinta y compruebe `False` con `"no-es-un-hash"`.
- [x] 5.2 Reescribir `crear_token(sub, roles, expires_delta=None)` y `verificar_token` con `sub`/`iat`/`exp`, `iat` sin truncar y `require` de claims; devuelve `None` ante token vencido, firma inválida o claim faltante. Verificación: script de humo que emita un token, lo verifique y obtenga `sub`; luego compruebe `None` con un token vencido (`expires_delta=-1 min`), con otro firmado con otra clave y con un payload sin `sub`.

## 6. Integración y documentación del change

- [x] 6.1 Verificar que la app importa y que `/health/live` responde con `TestClient` sin base de datos, y que `/health/ready` no rompe por el tipo de sesión (responde 503 cuando la base no está disponible). Verificación: `python -c "from fastapi.testclient import TestClient; ..."` con `SECRET_KEY`/`POSTGRES_PASSWORD` en el entorno; `GET /health/live` → 200.
- [x] 6.2 Marcar `C-02` como completado en `CHANGES.md`. Verificación: la línea de `C-02` dice `[x] completado`.

## Workflow follow-up

- Revisar los artefactos del change y archivarlo con `/opsx:archive c-02-core-persistence` cuando el usuario lo pida.
- Después del archivo, `C-03 domain-models` queda habilitado (sus dependencias `C-01` y `C-02` estarán archivadas).
