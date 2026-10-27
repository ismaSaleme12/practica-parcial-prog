# Proposal

## Why

`C-04` dejó el esquema migrado y sembrado, pero la API todavía no tiene **contratos**: los módulos `usuarios`, `clientes`, `repuestos` y `ordenes` sólo tienen `models.py`, el único endpoint montado es `health` y no existe ninguna traducción de errores. Si el primer endpoint de negocio se escribiera sin esta capa, cada módulo repetiría el mismo defecto: campos que el cliente no debería poder enviar (`rol`, `stock`, `password_hash`, `precio`, `total`), dinero serializado como número (o peor, como `float`), `password_hash` filtrándose en una respuesta, contraseñas de más de 72 bytes llegando a bcrypt (500 en lugar de 422) y el texto crudo de PostgreSQL viajando al cliente en un `IntegrityError` (RN-18).

Este change implementa el **Ejercicio 3** de la consigna (US-007, US-008) y fija los patrones que `C-07` a `C-13` van a heredar: contratos separados de los modelos de tabla, dinero como `Decimal` que viaja como **string**, `extra="forbid"` en toda entrada, `exclude_unset` en PATCH, traducción central de `IntegrityError` a **409** y un listado paginado real que demuestra el envoltorio de `C-02` y la búsqueda con parámetros ligados.

## What Changes

- **`app/core/schemas.py`** (nuevo): piezas compartidas por los contratos — `ContratoEntrada` (`extra="forbid"`, `str_strip_whitespace`), el tipo `Dinero` (`Decimal` que se serializa como **string** con dos decimales, nunca `float`) y el helper `cambios_enviados()` que aplica la convención de PATCH (`exclude_unset`, sin `None`).
- **`app/core/errors.py`** (nuevo): manejo central de errores registrado desde `main.py` — `IntegrityError` → **409 con mensaje propio** (nunca el texto de la base ni una traza), `DataError` → 422, `RequestValidationError` → 422 con mensaje propio y lista de campos, `HTTPException`/`StarletteHTTPException` con `detail` uniforme y 404 de ruta traducido. Además las excepciones propias `Conflicto` (409) y `RecursoNoEncontrado` (404) para que los servicios declaren la regla que conocen.
- **`app/modules/usuarios/schemas.py`** (nuevo): `UsuarioCrear` con `extra="forbid"`, email/nombre acotados a las longitudes del esquema y **contraseña ≤ 72 bytes UTF-8** validada en el contrato; `UsuarioLeer` **sin `password_hash`**.
- **`app/modules/repuestos/schemas.py`** (nuevo): `RepuestoCrear` (el `stock` **no** se declara: enviarlo es 422), `RepuestoLeer` con `precio` como string Decimal, `RepuestoPatch` (sólo `descripcion` y `precio`) como contrato de referencia de la convención PATCH.
- **`app/modules/usuarios/{repository,unit_of_work,service,router}.py`** y **`app/modules/repuestos/{repository,unit_of_work,service,router}.py`** (nuevos): el patrón de seis capas que heredan los módulos de dominio, con dos endpoints de prototipo por módulo — `POST /usuarios` (201, hash calculado **antes** de abrir la transacción) y `GET /repuestos`, `GET /repuestos/{id}`, `POST /repuestos`.
- **`GET /repuestos`**: listado **real** con el envoltorio `{items, total, page, size, pages}` de `app/core/paginacion.py`, orden determinista por `id` (dos páginas consecutivas no repiten filas), búsqueda `q` con **parámetros ligados** (`ILIKE $1`, nunca concatenación) y página fuera de rango → 422 con mensaje propio.
- **`app/core/repository.py`**: `BaseRepository` gana `_orden_por` (tupla vacía por defecto, sin cambio para quien no la declara) para que `list_page` aplique un `ORDER BY` estable; `RepuestoRepository` lo declara.
- **`main.py`**: se registran los manejadores de error y se montan los routers de `usuarios` y `repuestos`. Los endpoints son de **prototipo**: `C-08` los re-monta en el grupo protegido y agrega `requiere_rol`; `C-10` completa el ABM de repuestos con `stock_inicial`, historial de precio y baja lógica.
- **Evidencia**: `test/contracts.http` con la respuesta esperada en cada bloque (422 de `extra="forbid"`, contraseña > 72 bytes, página fuera de rango, `IntegrityError` → 409, 404) y `test/test_contracts.py` como réplica automatizada.

## Capabilities

### New Capabilities
- `request-contracts`: contratos de entrada/salida separados de los modelos, `extra="forbid"`, dinero como string Decimal, contraseña ≤ 72 bytes y convención `exclude_unset` para PATCH.
- `error-handling`: traducción central de errores con mensajes propios y códigos consistentes (201/204/404/409/422), sin texto interno de la base y sin que una entrada inválida termine en 500.
- `list-pagination-stub`: primer listado real que aplica el envoltorio de paginación con búsqueda `q` parametrizada y 422 para página fuera de rango.

### Modified Capabilities
- Ninguna. `list-pagination` (de `C-02`) no cambia: este change la **usa** por primera vez.

## Impact

- **Código**: `main.py`, `app/core/repository.py` (sólo `_orden_por`), `app/core/schemas.py` (nuevo), `app/core/errors.py` (nuevo), `app/modules/usuarios/{schemas,repository,unit_of_work,service,router}.py` (nuevos), `app/modules/repuestos/{schemas,repository,unit_of_work,service,router}.py` (nuevos).
- **Base de datos**: sin migraciones. Sólo se leen/escriben `usuario` y `repuesto` con el esquema de `C-04` (se ejercitan el UNIQUE de `usuario.email` y el índice único parcial de `repuesto.codigo`).
- **Dependencias**: ninguna nueva. No se agrega `email-validator` (no está en el stack cerrado): el email se valida con un patrón en el contrato.
- **Habilitado**: `C-07 auth` (reutiliza `UsuarioCrear`, el repositorio y la traducción de 409), `C-08 authorization-rbac` (re-monta los routers en el grupo protegido) y `C-10 repuestos-stock` (extiende los contratos y el listado).
