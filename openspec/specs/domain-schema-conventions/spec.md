# domain-schema-conventions Specification

## Purpose
Defines the cross-cutting conventions that every domain table must honour: mandatory names, exact money, time-zone-aware dates, an index for every foreign key and navigation from both ends of each relation.

## Requirements

### Requirement: Table and column names are a contract

The thirteen domain tables SHALL be named `usuario`, `asignacion_rol`, `intento_acceso`, `evento_seguridad`, `cliente`, `vehiculo`, `repuesto`, `movimiento_stock`, `historial_precio_repuesto`, `estado_orden`, `orden_trabajo`, `item_orden` and `historial_estado_orden`, with the column names listed for each one.

#### Scenario: Required tables exist

- **WHEN** the schema metadata is inspected
- **THEN** the thirteen tables are present with exactly those names

#### Scenario: Required columns exist

- **WHEN** a table is inspected
- **THEN** every column named in its contract is present with that exact name; extra columns may exist but required ones are never renamed or removed

### Requirement: Money is exact

Every monetary column SHALL be `NUMERIC` with two decimals and SHALL be exposed in Python as `Decimal`, never as `float`.

#### Scenario: Amounts keep their cents

- **WHEN** `8000.10` is stored in `repuesto.precio` and read back
- **THEN** the value is exactly `Decimal("8000.10")`

#### Scenario: Order totals have room for large amounts

- **WHEN** `orden_trabajo.total` is inspected
- **THEN** its type is `NUMERIC(12,2)`

### Requirement: Timestamps carry their time zone

Every date and time column SHALL be `timestamp with time zone`.

#### Scenario: Aware writes keep the instant

- **WHEN** a time-zone-aware moment is stored and read back
- **THEN** the same instant is returned with its offset resolved by PostgreSQL

### Requirement: Every foreign key is indexed

Each column that references another table SHALL have an index of its own, because PostgreSQL does not create one for a foreign key.

#### Scenario: Foreign key columns are indexed

- **WHEN** the indexes of a table with foreign keys are inspected
- **THEN** each foreign key column appears as the leading column of an index

### Requirement: Relations are navigable from both ends

Every relation that is read SHALL be declared on both ends, and the one-to-one relation between `usuario` and `cliente` SHALL expose a single object or nothing, never a list.

#### Scenario: Navigating from a user

- **WHEN** a user is loaded and its relations are traversed
- **THEN** its role assignments, mechanic orders, state history, stock movements and price history are reachable as collections, and its customer record is a single object or empty

#### Scenario: Navigating from an order

- **WHEN** an order is loaded and its relations are traversed
- **THEN** its vehicle, assigned mechanic, state, items, state history and stock movements are reachable
