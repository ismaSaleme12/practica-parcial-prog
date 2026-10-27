# Spec Delta

## Purpose

Defines the known starting state of the database that every test and demo relies on, and the guarantee that it can be rebuilt as many times as needed.

## ADDED Requirements

### Requirement: The seed rebuilds the state deterministically

Running the seed SHALL empty the tables and load the initial data again; running it twice MUST leave the same rows and counts, with no duplicates and no manual cleanup.

#### Scenario: Second run leaves the same state

- **WHEN** the seed runs twice in a row
- **THEN** the row counts of every table are identical after both runs

#### Scenario: Reset does not trip the append-only triggers

- **WHEN** the seed empties the audit tables whose rows cannot be deleted one by one
- **THEN** the reset succeeds without violating the append-only protection

### Requirement: The state catalog is loaded first

The seed SHALL load `PENDIENTE` (1), `EN_REPARACION` (2), `TERMINADA` (3, final) and `CANCELADA` (4, final) before creating any order.

#### Scenario: Catalog contents

- **WHEN** the seed finishes
- **THEN** the four states exist with their positions, and only `TERMINADA` and `CANCELADA` are final

#### Scenario: No order without its state

- **WHEN** the seed creates the two test orders
- **THEN** each one references a state that already exists

### Requirement: Users and their roles are loaded

The seed SHALL create seven users (`admin@`, `admin2@`, `recepcion@`, `mecanico@`, `mecanico2@`, `cliente@` and `nuevo@example.com`) with one open role each, and `nuevo@example.com` MUST be flagged to change the password.

#### Scenario: Roles are open assignments

- **WHEN** the seed finishes
- **THEN** each user has exactly one assignment with no revocation date and the role the case expects

#### Scenario: Forced password change

- **WHEN** `nuevo@example.com` is loaded
- **THEN** `debe_cambiar_password` is true while the other users keep it false

### Requirement: Customers and vehicles are loaded

The seed SHALL create Laura with a user account and two vehicles, and Jorge without an account and one vehicle.

#### Scenario: Customer with account

- **WHEN** the seed finishes
- **THEN** Laura's record is linked to `cliente@example.com` and has two active vehicles

#### Scenario: Customer without account

- **WHEN** the seed finishes
- **THEN** Jorge's record has no user link and has one active vehicle

### Requirement: Spare parts start with a stock movement

The seed SHALL create four spare parts with stock 10, 4, 2 and 20, and one movement with motive `Stock inicial` for each one, so the stock never changes outside a movement.

#### Scenario: Initial stock is explained by a movement

- **WHEN** the seed finishes
- **THEN** each part has exactly one initial movement whose quantity equals its stock

### Requirement: Test orders exercise the stock rule

The seed SHALL create order 1 as `PENDIENTE` for Laura's first vehicle and order 2 as `EN_REPARACION` for Jorge's vehicle, assigned to `mecanico@example.com`, with four spark plugs while the stock is two.

#### Scenario: Order two exceeds the available stock

- **WHEN** the seed finishes
- **THEN** order 2 has one item with quantity four and its part has stock two

#### Scenario: Item price is copied from the part

- **WHEN** the seed creates an item
- **THEN** its unit price equals the part price at seed time

### Requirement: Price and security history are loaded

The seed SHALL record one price change of the oil filter from `8000.00` to `8500.00` and one security event whose actor is `SISTEMA`.

#### Scenario: Price history matches the current price

- **WHEN** the seed finishes
- **THEN** the filter's price is `8500.00` and its single history row starts at `8000.00`

#### Scenario: Initial load leaves an audit event

- **WHEN** the seed finishes
- **THEN** one security event records the initial data load with actor `SISTEMA`
