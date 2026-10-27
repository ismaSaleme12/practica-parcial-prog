# foundation-setup Specification

## Purpose
Establishes the application foundation, configuration loading with Pydantic settings, asynchronous database connectivity via SQLAlchemy and asyncpg, lifespan management, and health check endpoints.

## Requirements

### Requirement: Environment Configuration
The system SHALL load configuration settings using `pydantic-settings`, validating required variables such as `SECRET_KEY` and `POSTGRES_PASSWORD` without defaults, and computing the asynchronous database connection URL.

#### Scenario: Missing required environment variables
- **WHEN** application starts without `SECRET_KEY` or `POSTGRES_PASSWORD`
- **THEN** initialization fails with a validation error preventing startup.

### Requirement: Asynchronous Database Connection
The system SHALL establish an asynchronous SQLAlchemy engine and session factory configured with `expire_on_commit=False` and supply sessions via dependency injection from application state.

#### Scenario: Requesting a database session
- **WHEN** a request requires database access
- **THEN** an active asynchronous session is provided and properly closed upon request completion.

### Requirement: Application Lifespan
The system SHALL manage database engine initialization and disposal within a FastAPI lifespan handler stored in `app.state`.

#### Scenario: Application startup and shutdown
- **WHEN** the application starts up and shuts down
- **THEN** the database engine and session factory are initialized during startup and cleanly disposed during shutdown.

### Requirement: Health Check Endpoints
The system SHALL expose liveness and readiness health check endpoints.

#### Scenario: Liveness check
- **WHEN** `GET /health/live` is requested
- **THEN** the system responds with status 200 without querying the database.

#### Scenario: Readiness check with healthy database
- **WHEN** `GET /health/ready` is requested and PostgreSQL is reachable
- **THEN** the system responds with status 200.

#### Scenario: Readiness check with unreachable database
- **WHEN** `GET /health/ready` is requested and PostgreSQL is unreachable
- **THEN** the system responds with status 503.
