# Spec Delta

## Purpose

Define cómo se decide el permiso por rol: consultando `asignacion_rol` en la base **en cada petición**, con una definición única de vigencia, y sin confiar en los roles que trae el token. El objetivo es que revocar un rol tenga efecto inmediato sobre una sesión ya abierta.

## ADDED Requirements

### Requirement: El permiso se consulta en la base en cada petición

`requiere_rol(*roles)` SHALL responder 403 cuando el usuario autenticado no tiene ninguno de los roles indicados, y SHALL decidirlo consultando `asignacion_rol` **en esa petición**. MUST NOT autorizar a partir del claim `roles` del token ni de ningún valor enviado por el cliente.

#### Scenario: Token con un rol que la base no reconoce

- **WHEN** se presenta un token válido cuyo `sub` es un usuario sin ADMIN vigente pero cuyo claim `roles` incluye `"ADMIN"`
- **THEN** una ruta que exige ADMIN responde 403

#### Scenario: Token emitido antes de obtener el rol

- **WHEN** un usuario obtiene un rol nuevo después de iniciar sesión y usa el mismo token anterior
- **THEN** la ruta que exige ese rol responde 200 sin necesidad de volver a loguearse

### Requirement: Rol vigente significa no revocado y no vencido

La API SHALL considerar vigente una asignación con `revocada_en IS NULL` y con `vence_en` nulo o posterior al momento de la petición. La misma definición MUST aplicarse en la autorización, en el conteo de administradores y en el campo `vigente` del contrato de roles.

#### Scenario: Rol vencido

- **WHEN** la única asignación del rol tiene `vence_en` en el pasado y no está revocada
- **THEN** la ruta que exige ese rol responde 403

#### Scenario: Rol revocado

- **WHEN** la asignación del rol tiene `revocada_en` escrito
- **THEN** la ruta que exige ese rol responde 403 y el historial sigue mostrando la fila

### Requirement: Revocar un rol afecta a la sesión abierta en la petición siguiente

La API SHALL rechazar con 403 la petición siguiente de una sesión ya abierta cuyo rol fue revocado, sin esperar a que el token venza y sin exigir un nuevo login.

#### Scenario: Revocación con el token anterior

- **WHEN** un usuario inicia sesión con un rol, un ADMIN lo revoca y el usuario repite la petición con el mismo token
- **THEN** la respuesta es 403

#### Scenario: Reasignación con el mismo token

- **WHEN** el rol se vuelve a asignar y el usuario repite la petición con el token original
- **THEN** la respuesta es 200, porque la decisión se toma en la base y no en el token

### Requirement: La matriz de roles se aplica por ruta

Las rutas SHALL declarar los roles que aceptan según la matriz de `03_actores_y_roles.md`. Las rutas de administración de personal, roles y eventos MUST exigir ADMIN. Los listados y el detalle de repuestos MUST aceptar ADMIN, RECEPCION y MECANICO; el alta de repuestos MUST exigir ADMIN.

#### Scenario: Cliente en el grupo protegido

- **WHEN** un usuario con rol CLIENTE pide `GET /repuestos`
- **THEN** la respuesta es 403

#### Scenario: Recepción intenta crear un repuesto

- **WHEN** un usuario con rol RECEPCION pide `POST /repuestos`
- **THEN** la respuesta es 403

#### Scenario: Administrador crea un repuesto

- **WHEN** un usuario con rol ADMIN vigente pide `POST /repuestos` con un cuerpo válido
- **THEN** la respuesta es 201
