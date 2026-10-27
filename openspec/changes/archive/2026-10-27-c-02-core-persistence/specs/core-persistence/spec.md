# Spec Delta

## Purpose

Defines the persistence building blocks shared by every module: repositories that only flush, a Unit of Work that owns the single commit of a request, and a session that is shared, never closed by them.

## ADDED Requirements

### Requirement: Repositories never commit

A repository SHALL persist changes with a flush that makes them visible inside the current transaction, and SHALL NOT commit, roll back, close the session or start a new transaction.

#### Scenario: Adding an entity

- **WHEN** a repository adds or updates an entity and the operation succeeds
- **THEN** the changes are flushed to the database inside the current transaction and remain pending until the Unit of Work decides.

#### Scenario: Caller decides the outcome

- **WHEN** the Unit of Work that wraps the repository exits without an exception
- **THEN** the changes are committed; when it exits with an exception, they are rolled back and none of them survive.

### Requirement: Repository contract

A base repository SHALL be constructed with a session and the model class it manages, and SHALL offer lookup by primary key, listing, counting, adding, updating, deleting and refreshing entities of that model.

#### Scenario: Lookup by identifier

- **WHEN** an entity exists and is looked up by its primary key
- **THEN** the repository returns the entity instance of the configured model class.

#### Scenario: Lookup of a missing identifier

- **WHEN** no row matches the requested primary key
- **THEN** the repository returns an empty result instead of raising.

#### Scenario: Deleting a missing entity

- **WHEN** a hard delete is requested for an identifier that does not exist
- **THEN** the repository reports that nothing was deleted.

### Requirement: Soft delete repositories

A soft-delete repository SHALL behave like the base repository for entities carrying a deletion timestamp, excluding rows with a deletion timestamp from normal reads and offering explicit access to them.

#### Scenario: Deleted row is invisible

- **WHEN** an entity has a deletion timestamp and is read through the normal lookup or listing
- **THEN** the repository does not return it.

#### Scenario: Deleted row is visible on request

- **WHEN** the same entity is requested through the lookup that includes deleted rows
- **THEN** the repository returns it with its deletion timestamp.

#### Scenario: Soft deleting twice

- **WHEN** an entity that already carries a deletion timestamp is soft deleted again
- **THEN** the repository rejects the operation and the original timestamp is preserved.

### Requirement: Unit of Work owns the transaction boundary

A Unit of Work SHALL be an asynchronous context manager that commits once on a clean exit, rolls back on an exception and never closes the session it received.

#### Scenario: Clean exit commits

- **WHEN** the block exits without raising
- **THEN** the transaction is committed and the session remains open and reusable.

#### Scenario: Exception rolls back

- **WHEN** the block exits because of an exception
- **THEN** every change made inside the block is rolled back and the exception propagates to the caller.

#### Scenario: Commit failure is not swallowed

- **WHEN** the commit fails
- **THEN** the transaction is rolled back and the failure propagates instead of being reported as success.

#### Scenario: Session ownership stays with the caller

- **WHEN** a request finishes and the session is closed by its owner
- **THEN** the Unit of Work does not interfere: every repository it composed shares that same session and no additional session is created.

### Requirement: Shared session across repositories

All repositories composed by the same Unit of Work SHALL receive one and the same session, so writes of different repositories participate in a single transaction.

#### Scenario: Two repositories in one transaction

- **WHEN** two repositories of the same Unit of Work write inside one block
- **THEN** both writes are committed or rolled back together, never independently.
