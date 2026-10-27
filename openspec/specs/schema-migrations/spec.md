# schema-migrations Specification

## Purpose
Defines how the database schema is created, versioned and reverted: only through Alembic migrations, in two reviewed steps, with the connection configured from the application settings.

## Requirements

### Requirement: The schema is created only by Alembic

The domain schema SHALL be created by running `alembic upgrade head` on an empty database; the application, the seed and any import SHALL NOT create tables.

#### Scenario: Empty database becomes the full schema

- **WHEN** `alembic upgrade head` runs against a database with no domain tables
- **THEN** the thirteen tables and their indexes exist and the migration version table records the latest revision

#### Scenario: Starting the application does not create tables

- **WHEN** the application starts against a database without the migrated schema
- **THEN** no table is created and the readiness check reports the database as unavailable

#### Scenario: Seeding does not create the schema

- **WHEN** the seed runs against a database without the migrated schema
- **THEN** it fails with a clear error instead of creating tables

### Requirement: Migrations are reversible

The migration chain SHALL survive the cycle `upgrade head → downgrade base → upgrade head` without manual intervention.

#### Scenario: Downgrade removes what upgrade created

- **WHEN** `alembic downgrade base` runs on a migrated database
- **THEN** the thirteen domain tables no longer exist

#### Scenario: Upgrade after downgrade works again

- **WHEN** `alembic upgrade head` runs again after a full downgrade
- **THEN** the schema is recreated with the same tables, constraints and triggers

### Requirement: The generated migration covers the model contract

The first migration SHALL be produced from the model metadata and SHALL include the tables, foreign keys, unique constraints, check constraints and the three partial unique indexes.

#### Scenario: Partial indexes reach the database

- **WHEN** the first migration has been applied
- **THEN** the partial unique indexes on `asignacion_rol`, `vehiculo` and `repuesto` exist with their `WHERE` clauses

#### Scenario: Constraints are enforced after migrating

- **WHEN** rows that violate a check or a unique constraint are inserted after the migration
- **THEN** the database rejects them exactly as it does on the model metadata

### Requirement: The connection is configured outside the repository

The migration configuration file SHALL NOT contain credentials; the database URL SHALL be resolved from the application settings, which read the environment.

#### Scenario: Credentials come from the environment

- **WHEN** Alembic runs with the environment variables set
- **THEN** it connects with that URL and the configuration file contains no user or password

#### Scenario: Missing credentials fail loudly

- **WHEN** the required environment variables are absent
- **THEN** the settings raise an error before any connection attempt
