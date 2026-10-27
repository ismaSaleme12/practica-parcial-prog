# inventory-models Specification

## Purpose
Defines the schema contract for the spare parts catalog, its stock movements and its price history, with money and quantities validated by the database.

## Requirements

### Requirement: Spare parts catalog

The `repuesto` table SHALL store `id`, `codigo`, `descripcion`, `precio`, `stock` and `borrado_en`; `precio` MUST be `NUMERIC(10,2)` greater than zero, `stock` MUST NOT be negative, and `codigo` MUST be unique among rows with `borrado_en IS NULL`.

#### Scenario: Duplicate code among active parts is rejected

- **WHEN** a part is inserted with a `codigo` already used by a part whose `borrado_en` is `NULL`
- **THEN** the database rejects the insert

#### Scenario: Code of a deleted part can be reused

- **WHEN** the previous part with that `codigo` has `borrado_en` set and a new active part is inserted with the same code
- **THEN** the insert succeeds

#### Scenario: Non-positive price is rejected

- **WHEN** a part is inserted with `precio` equal to zero or negative
- **THEN** the database rejects the insert

#### Scenario: Negative stock is rejected

- **WHEN** a part is updated to a `stock` below zero
- **THEN** the database rejects the update

### Requirement: Stock movements

The `movimiento_stock` table SHALL store `id`, `repuesto_id`, `orden_id`, `usuario_id`, `cantidad`, `motivo` and `cuando`; `cantidad` MUST be different from zero, `orden_id` MUST be nullable and every reference MUST point to an existing row.

#### Scenario: Inbound and outbound movements

- **WHEN** a restock is recorded with a positive `cantidad` and a delivery is recorded with a negative one
- **THEN** both rows are accepted and their sign is preserved

#### Scenario: Zero quantity is rejected

- **WHEN** a movement is inserted with `cantidad = 0`
- **THEN** the database rejects the insert

#### Scenario: Movement without an order

- **WHEN** a restock is recorded without `orden_id`
- **THEN** the row is valid and several movements may have no order

### Requirement: Price history

The `historial_precio_repuesto` table SHALL store `id`, `repuesto_id`, `usuario_id`, `precio_anterior`, `precio_nuevo` and `cuando`; both prices MUST be `NUMERIC(10,2)`, `precio_nuevo` MUST be greater than zero and MUST differ from `precio_anterior`.

#### Scenario: Price increase is recorded

- **WHEN** a part price changes from `8000.00` to `8500.00`
- **THEN** the row is accepted with both amounts stored exactly

#### Scenario: Price decrease is recorded

- **WHEN** a part price changes from `8500.00` to `8000.00`
- **THEN** the row is accepted, because the check forbids equality, not a lower value

#### Scenario: Unchanged price is rejected

- **WHEN** a row is inserted with `precio_nuevo` equal to `precio_anterior`
- **THEN** the database rejects the insert
