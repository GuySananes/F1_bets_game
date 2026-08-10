# F1 Bets Game

A prediction league PWA for a small group of friends. Bet on F1 qualifying, sprint, and race results each week, earn points for accuracy, and track a season-long leaderboard.

Installs to your phone's home screen like a native app — no app store required.

---

## Rules

### Sessions (each race weekend)
- **Qualifying** — predict the exact order of the **top 10** drivers.
- **Sprint** — predict the exact order of the **full grid** (default 22 drivers, varies by season/event). Only on weekends that have a sprint.
- **Race** — predict the exact order of the **full grid**, plus bonus questions.

### Position scoring (qualifying, sprint, race)
Per position predicted:
- Exact match → **3 points**
- Off by exactly one position (actual is one above or below your guess) → **1 point**
- Otherwise → 0 points

Each position is scored independently.

### DNF handling (race only)
Drivers who don't finish still occupy a final position, placed after all classified finishers. With multiple DNFs, they're ordered by retirement time: whoever retired **first** takes the **last** position, whoever retired second takes second-to-last, and so on.

### Race bonuses
| Bonus | Type | Points |
|---|---|---|
| First driver to receive a penalty | Pick a driver | 5 |
| First driver to pit | Pick a driver | 5 |
| Red flag shown | True/False | 3 |
| Safety car deployed | True/False | 3 |
| Virtual safety car deployed | True/False | 3 |
| Number of classified finishers (non-DNF) | Exact number | 3 |
| MVP driver of the race | Pick a driver | 3 |
| Fastest lap driver | Pick a driver | 3 |

### Teams, drivers, and users
- Team count and grid size are season-specific (not hardcoded) — e.g. 11 teams this season, 10 last season.
- Each team has 2 primary drivers plus one or more reserves, who may substitute in for a given race weekend. Substitutions are tracked per event, so they don't affect the permanent season roster.
- Team and driver names are seeded with real-world defaults but fully editable by an admin at any time.
- Anyone can self-register (username + password). Joining mid-season starts you at 0 points — no penalty for joining late.

### Season reset
An admin can wipe the season's race data (`/admin/season/reset`) to start over: this permanently deletes every event and its entries, predictions, results, and points, and resets the next round number back to 1. Teams and drivers are left exactly as they are. This is a hard delete, not an archive — there's no way to recover the deleted data afterward.

### Prediction lock time
Each session (qualifying, sprint, race) has its own start time, set by the admin per event. Predictions lock automatically, server-side, once that time passes — editable freely (any number of times) before then, read-only after. Race bonus predictions share the race session's lock time.

### Setting your predicted order
Drag driver cards into place (mouse or touch) to set your predicted finishing order, or use the ▲/▼ buttons if you'd rather not drag. When a session predicts fewer positions than there are entered drivers (e.g. qualifying's top-10 cap on a bigger grid), extra drivers sit in a pool below the ranked list until you add them in. Each card shows the driver's name, car number, and a team-color accent.

---

## Architecture

**Backend:** FastAPI (Python)
**Frontend:** Jinja2 templates + HTMX — server-rendered, no separate JS framework or build step (plus SortableJS via CDN for the drag-and-drop driver ranking)
**Database:** PostgreSQL via SQLAlchemy + Alembic migrations (Supabase in production, SQLite/Postgres locally in dev)
**PWA:** manifest.json + service worker for home-screen install
**Hosting:** Render (free tier)
**Auth:** username/password, hashed, server-side sessions — no OAuth

### Data model (high level)
- `seasons` → `teams` → `drivers` (season-scoped, since rosters change year to year)
- `events` (race weekends, with a start time per session for automatic prediction locking) → `event_entries` (the actual field racing that weekend, handling substitutions/missing drivers)
- `users` (self-registered, admin flag for roster/event management) and `sessions` (server-side login sessions — an opaque token cookie maps to a row here, deleted on logout)
- `predictions` (position picks per user/event/session) and `results` (actual outcomes) — scored by comparing the two
- `bonus_predictions` / `bonus_results` — race-only bonus questions
- `points_log` — computed points per user per event per session, with a breakdown, so the leaderboard has full history rather than just a running total

Full schema details live in [`f1_prediction_league_spec.md`](./f1_prediction_league_spec.md).

---

## Running the app

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000 in your browser.

---

## Project docs

- [`f1_prediction_league_spec.md`](./f1_prediction_league_spec.md) — full rules, schema, and open decisions
- [`implementation_order.md`](./implementation_order.md) — phased build plan for Claude Code
- [`CLAUDE.md`](./CLAUDE.md) — conventions and guardrails for Claude Code
- [`.claude/skills/`](./.claude/skills/) — scoring rules reference and documentation-maintenance skill

## Status

🚧 In development. See `implementation_order.md` for current build phase.
