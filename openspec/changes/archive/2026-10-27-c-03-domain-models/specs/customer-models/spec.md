# Spec Delta

## Purpose

Defines the schema contract for customer records and their vehicles, including the optional link to a user account and logical deletion of vehicles.

## ADDED Requirements

### Requirement: Customer records

The `cliente` table SHALL store `id`, `usuario_id`, `nombre`, `documento` and `telefono`; `usuario_id` MUST be unique and nullable, and `documento` MUST be unique.

#### Scenario: Customer linked to a user account

- **WHEN** a `cliente` row is inserted with a `usuario_id` that exists
- **THEN** the link is stored and the same `usuario_id` cannot be used by another customer

#### Scenario: Customer without a user account

- **WHEN** a walk-in customer is inserted without `usuario_id`
- **THEN** the row is valid and several customers may have no account

#### Scenario: Duplicate document is rejected

- **WHEN** a `cliente` row is inserted with a `documento` already present
- **THEN** the database rejects the insert with a unique violation

### Requirement: Vehicles with logical deletion

The `vehiculo` table SHALL store `id`, `cliente_id`, `patente`, `marca`, `modelo`, `anio` and `borrado_en`; `patente` MUST be unique among rows with `borrado_en IS NULL`, `anio` MUST be between 1950 and 2100, and `cliente_id` MUST reference an existing customer.

#### Scenario: Duplicate plate among active vehicles is rejected

- **WHEN** a vehicle is inserted with a `patente` already used by a vehicle whose `borrado_en` is `NULL`
- **THEN** the database rejects the insert

#### Scenario: Plate of a deleted vehicle can be reused

- **WHEN** the previous vehicle with that `patente` has `borrado_en` set and a new active vehicle is inserted with the same plate
- **THEN** the insert succeeds

#### Scenario: Out-of-range year is rejected

- **WHEN** a vehicle is inserted with `anio` below 1950 or above 2100
- **THEN** the database rejects the insert

#### Scenario: Vehicle of a missing customer is rejected

- **WHEN** a vehicle is inserted with a `cliente_id` that does not exist
- **THEN** the database rejects the insert
