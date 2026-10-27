# Spec Delta

## Purpose

Defines the schema contract for work orders: their state catalog, the order itself, its composed items and the history of state transitions.

## ADDED Requirements

### Requirement: Order states are a catalog

The `estado_orden` table SHALL use `codigo` as its primary key and store `descripcion`, `posicion` and `es_final`; `posicion` MUST be unique.

#### Scenario: Repeated position is rejected

- **WHEN** a state is inserted with a `posicion` already used by another state
- **THEN** the database rejects the insert

#### Scenario: States are identified by their code

- **WHEN** the states `PENDIENTE`, `EN_REPARACION`, `TERMINADA` and `CANCELADA` are stored
- **THEN** each row is retrievable by its `codigo` and `TERMINADA` and `CANCELADA` carry `es_final = true`

### Requirement: Work orders reference a catalog state

The `orden_trabajo` table SHALL store `id`, `vehiculo_id`, `mecanico_id`, `estado`, `falla`, `creada_en` and `total`; `estado` MUST reference `estado_orden.codigo`, `mecanico_id` MUST be nullable, `total` MUST be `NUMERIC(12,2)` and MUST NOT be negative.

#### Scenario: Unknown state is rejected

- **WHEN** an order is inserted with an `estado` that does not exist in `estado_orden`
- **THEN** the database rejects the insert through the foreign key

#### Scenario: Order without an assigned mechanic

- **WHEN** an order is created with `mecanico_id` empty
- **THEN** the row is valid and several orders may have no mechanic

#### Scenario: Negative total is rejected

- **WHEN** an order is updated to a `total` below zero
- **THEN** the database rejects the update

### Requirement: Order items compose the order

The `item_orden` table SHALL store `id`, `orden_id`, `repuesto_id`, `cantidad` and `precio_unitario`; `cantidad` and `precio_unitario` MUST be greater than zero and the pair `(orden_id, repuesto_id)` MUST be unique.

#### Scenario: Same part twice in one order is rejected

- **WHEN** a second item with the same `orden_id` and `repuesto_id` is inserted
- **THEN** the database rejects the insert

#### Scenario: Non-positive quantity or unit price is rejected

- **WHEN** an item is inserted with `cantidad` or `precio_unitario` equal to zero or negative
- **THEN** the database rejects the insert

#### Scenario: Item of a missing order is rejected

- **WHEN** an item is inserted with an `orden_id` that does not exist
- **THEN** the database rejects the insert

### Requirement: State transitions keep their history

The `historial_estado_orden` table SHALL store `id`, `orden_id`, `desde_estado`, `hasta_estado`, `usuario_id` and `cuando`; `desde_estado` MUST be nullable and both state columns MUST reference `estado_orden.codigo`.

#### Scenario: First transition has no previous state

- **WHEN** an order moves from nothing to `PENDIENTE`
- **THEN** the row is stored with `desde_estado` empty and `hasta_estado = 'PENDIENTE'`

#### Scenario: Unknown target state is rejected

- **WHEN** a transition is inserted with a `hasta_estado` that does not exist in the catalog
- **THEN** the database rejects the insert
