# Design

## Context

Establishing FASE 0 Cimientos for the FastAPI workshop API (Exercise 1, US-001 to US-004) as outlined in `CHANGES.md` and the project knowledge base.

## Goals / Non-Goals

**Goals:**
- Implement exact directory structure for core and modules.
- Configure `pydantic-settings` with strict required validation.
- Implement asynchronous SQLAlchemy 2.0 engine and session dependency using `app.state`.
- Implement lifespan management and health check endpoints (`/health/live`, `/health/ready`).

**Non-Goals:**
- Domain models or business logic tables (deferred to C-03 and C-09+).
- Authentication endpoints or tokens (deferred to C-07).

## Decisions

- **Decision: Configuration Management**: Use `pydantic-settings` `Settings` class with `@computed_field` to construct the async connection URL (`postgresql+asyncpg://...`).
- **Decision: Lifespan State**: Store the async engine and session factory in `app.state` to avoid global state import issues.
- **Decision: Health Checks**: `/health/live` checks process vitality; `/health/ready` executes `SELECT 1` against the database.

## Risks / Trade-offs

- **Risk**: Database unreachable on startup.
- **Mitigation**: Lifespan initialization can log connection failures; `/health/ready` accurately reports 503 if DB is down.
