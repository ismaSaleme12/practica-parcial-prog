# Skill Registry

**Delegator use only.** Any agent that launches sub-agents reads this registry to resolve compact rules, then injects them directly into sub-agent prompts. Sub-agents do NOT read this registry or individual SKILL.md files.

## Local Project Skills (`.agents/skills/`)

| Trigger | Skill | Path |
|---|---|---|
| FastAPI best practices and conventions | fastapi | .agents/skills/fastapi/SKILL.md |
| FastAPI patterns (auth, async handlers, DB) | fastapi-patterns | .agents/skills/fastapi-patterns/SKILL.md |
| Postgres best practices by Supabase | supabase-postgres-best-practices | .agents/skills/supabase-postgres-best-practices/SKILL.md |

## Compact Rules

### fastapi
- Use FastAPI 0.111+ with Pydantic v2 schemas
- All handlers must be `async def`
- Use dependency injection for DB sessions and UoW

### fastapi-patterns
- Async handlers and transactional service layers
- JWT access token in HttpOnly SameSite=Lax cookie
- Repository pattern with `flush()` only; UoW handles commit/rollback

### supabase-postgres-best-practices
- Decimal for money (`NUMERIC(10,2)`), timestamptz for dates
- Partial unique indexes for soft delete (`WHERE borrado_en IS NULL`)
- Explicit indexes on all foreign keys

## Project Conventions

| File | Path | Notes |
|---|---|---|
| AGENTS.md | AGENTS.md | Project instructions & hard rules |
| CLAUDE.md | CLAUDE.md | Orchestrator and project rules |
| CHANGES.md | CHANGES.md | Implementation roadmap & changes |
| knowledge-base/ | knowledge-base/ | Domain source of truth (01..10) |
