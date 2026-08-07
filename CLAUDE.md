# CLAUDE.md

## Project
F1 prediction league PWA for a small friend group (<20 users). Full rules and schema live in `f1_prediction_league_spec.md` — read it before making changes to models or scoring logic. Build order lives in `implementation_order.md` — follow it phase by phase, and stop at each checkpoint rather than continuing unprompted.

## Stack
- Backend: FastAPI (Python)
- DB: SQLAlchemy + Alembic migrations. Dev: local SQLite or Postgres. Prod: Supabase Postgres.
- Frontend: Jinja2 templates + HTMX. No separate JS framework/build step.
- PWA: manifest.json + service worker for home-screen install.
- Hosting: Render (free tier).
- Auth: username/password with hashed passwords + server sessions. No OAuth.

## Conventions
- Keep the scoring engine (`app/scoring.py` or similar) pure — no DB or FastAPI imports in it. It should be fully testable with plain Python objects/dicts. See `.claude/skills/f1-scoring-rules/` for the exact rules it must implement.
- Never hardcode team count, driver count, or grid size — these vary by season and even by event (see `events.grid_size`, `event_entries`). Always derive from the DB.
- Team/driver names are admin-editable at any time. Do not assume names are stable — reference by ID everywhere except display.
- `.env` holds real secrets and is never committed. `.env.example` documents required variables with placeholder values.
- Every new feature that touches scoring, points, or roster/event admin needs a test before being considered done.
- Migrations are the only way schema changes happen — never hand-edit a deployed DB.

## Workflow
- Work one phase of `implementation_order.md` at a time. At each checkpoint, summarize what was built and wait for confirmation before continuing.
- If a rule in the spec seems ambiguous or you're about to guess at behavior not explicitly stated, stop and ask rather than assuming.
- Run `pytest` before considering any scoring-related task done.

## Do not
- Do not introduce a second frontend framework (React/Vue/etc.) — the HTMX approach was chosen deliberately to keep this a small, single-language project.
- Do not add paid services or paid tiers of Render/Supabase without flagging it first — free-forever hosting was a hard requirement.
- Do not skip writing `event_entries` when creating an event — this is what makes substitutions and missing drivers work correctly.
