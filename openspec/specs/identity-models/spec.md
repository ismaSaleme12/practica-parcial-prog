# identity-models Specification

## Purpose
Defines the schema contract for user accounts, role assignments with validity, login attempts and the security audit trail.

## Requirements

### Requirement: User accounts

The `usuario` table SHALL store `id`, `email`, `nombre`, `password_hash`, `activo`, `debe_cambiar_password` and `password_cambiada_en`; `email` MUST be unique and `password_cambiada_en` MUST be a nullable timestamp with time zone.

#### Scenario: Duplicate email is rejected

- **WHEN** a second `usuario` row is inserted with an `email` already present
- **THEN** the database rejects the insert with a unique violation and no row is added

#### Scenario: Account without a recorded password change

- **WHEN** a `usuario` row is inserted without `password_cambiada_en`
- **THEN** the column is stored as `NULL` and the row is valid

### Requirement: Role assignments with validity

The `asignacion_rol` table SHALL store `id`, `usuario_id`, `rol`, `desde`, `vence_en`, `revocada_en` and `otorgada_por`, SHALL restrict `rol` to `ADMIN`, `RECEPCION`, `MECANICO` or `CLIENTE`, and MUST enforce at most one open assignment per `(usuario_id, rol)`.

#### Scenario: Second open assignment for the same role is rejected

- **WHEN** a `usuario` already has an assignment with `revocada_en IS NULL` for `MECANICO` and another open row for `MECANICO` is inserted
- **THEN** the database rejects the insert and the original assignment survives

#### Scenario: Reassigning a revoked role is allowed

- **WHEN** the previous `MECANICO` assignment has `revocada_en` set and a new open `MECANICO` row is inserted
- **THEN** the insert succeeds and both rows are kept as history

#### Scenario: Unknown role is rejected

- **WHEN** an assignment is inserted with a `rol` outside the four allowed values
- **THEN** the database rejects the insert

### Requirement: Login attempts are recorded for rate limiting

The `intento_acceso` table SHALL store `id`, `cuando`, `email`, `ip` and `exito`, and SHALL support filtering by `email`, `ip` and `cuando` through a composite index.

#### Scenario: Attempts of one email and address are counted

- **WHEN** several attempts are recorded for the same `email` and `ip` at different times
- **THEN** they are retrievable ordered by `cuando` using the composite index

#### Scenario: Successful and failed attempts are distinguishable

- **WHEN** an attempt is recorded as successful and another as failed
- **THEN** `exito` stores `true` and `false` respectively

### Requirement: Security events keep their actor as text

The `evento_seguridad` table SHALL store `id`, `cuando`, `actor` and `accion`, where `actor` is text so that the value `SISTEMA` is representable without a user account.

#### Scenario: Event raised by the system

- **WHEN** an audit event is recorded with `actor = 'SISTEMA'`
- **THEN** the row is stored without requiring a matching `usuario`
