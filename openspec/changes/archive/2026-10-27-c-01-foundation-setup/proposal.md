# Proposal

## Why

To establish the foundational architecture, configuration management, asynchronous database connectivity, application lifespan management, and health check endpoints required for the FastAPI workshop API (Exercise 1, US-001 to US-004).

## What Changes

- **New Capabilities**:
  - `foundation-setup`: Baseline project structure, Pydantic settings configuration, asynchronous database connection with SQLAlchemy 2.0 / asyncpg, application lifespan management, and health check endpoints (`/health/live`, `/health/ready`).
- **Modified Capabilities**: None.
- **Impact**: Sets up the core project layout, environment configuration template (`env.example`), requirements specification (`requirements.txt`), core utility modules under `app/core/`, and entrypoint `main.py`.

## Capabilities

### New Capabilities
- `foundation-setup`: Baseline project skeleton, configuration management, async database session management, and health check endpoints.

### Modified Capabilities
- None.

## Impact

- Creates the root structure, `app/core/` modules, `app/modules/health/` router, and configuration files.
