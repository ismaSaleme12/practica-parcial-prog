# append-only-enforcement Specification

## Purpose
Guarantees that the audit tables are append-only: rows can be added, never changed or removed, whatever the client or the psql session.

## Requirements

### Requirement: Append-only tables reject updates

`historial_estado_orden`, `movimiento_stock` and `historial_precio_repuesto` SHALL reject `UPDATE` at the database level.

#### Scenario: Updating a history row is rejected

- **WHEN** an `UPDATE` is attempted on a row of `historial_estado_orden`, `movimiento_stock` or `historial_precio_repuesto`
- **THEN** the database raises an error and the stored row keeps its original values

### Requirement: Append-only tables reject deletes

The same three tables SHALL reject `DELETE` at the database level.

#### Scenario: Deleting a history row is rejected

- **WHEN** a `DELETE` is attempted on a row of `historial_estado_orden`, `movimiento_stock` or `historial_precio_repuesto`
- **THEN** the database raises an error and the row is still present

### Requirement: Append-only tables accept inserts

The protection SHALL only cover modification and deletion; new rows MUST be insertable.

#### Scenario: A new movement is recorded

- **WHEN** a new `movimiento_stock` row is inserted after the schema is migrated
- **THEN** the insert succeeds and the row is stored

### Requirement: The protection lives in the manual migration

The triggers and their function SHALL be created by the hand-written migration and removed by its `downgrade`, independently of the generated migration.

#### Scenario: Downgrading the manual migration removes the protection

- **WHEN** the manual migration is downgraded while the tables still exist
- **THEN** the triggers and the function no longer exist and an `UPDATE` on those tables is accepted again
