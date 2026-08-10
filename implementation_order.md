# Implementation Order

Follow these phases **in order**. Each phase ends with a checkpoint — stop, show what you built, and wait for confirmation before starting the next phase. Do not jump ahead or build multiple phases in one shot, even if the task looks small.

Read `f1_prediction_league_spec.md` in full before starting Phase 0. It is the source of truth for the schema and rules — this file only sequences the work.

---

## Phase 0 — Project scaffold
- Initialize a Python project (`uv` or `venv` + `pip`, whichever you default to) with FastAPI, SQLAlchemy, Alembic, `passlib` (or similar for password hashing), `pytest`, and `python-dotenv`.
- Create the base folder structure: `app/`, `app/models/`, `app/routers/`, `app/templates/`, `app/static/`, `tests/`, `alembic/`.
- Set up `.env.example` (no real secrets) and `.gitignore` (must exclude `.env`, `__pycache__`, `*.db`).
- Get a bare FastAPI app running locally with a single `/health` route.

**Checkpoint:** app boots locally, `/health` returns 200.

---

## Phase 1 — Data model
- Implement all tables from the spec as SQLAlchemy models: `seasons`, `teams`, `drivers`, `events`, `event_entries`, `users`, `predictions`, `results`, `bonus_predictions`, `bonus_results`, `points_log`.
- Set up Alembic migrations against a local SQLite or local Postgres (your choice for dev; production will be Supabase Postgres — keep the code DB-agnostic via SQLAlchemy, don't rely on SQLite-only or Postgres-only features).
- Write a seed script for one season, its default teams/drivers, and one sample event — this becomes the fixture used in tests going forward.

**Checkpoint:** migrations run clean, seed script populates a working local DB, you can query it and see sensible data.

---

## Phase 2 — Scoring engine (build this in isolation, no routes/UI yet)
- Load and follow `.claude/skills/f1-scoring-rules/SKILL.md` for the exact rules.
- Implement pure functions (no DB, no FastAPI) that take predictions + results and return points:
  - `score_position_predictions(predictions, results) -> points breakdown`
  - `order_dnf_drivers(dnf_list_with_retirement_order) -> final positions`
  - `score_bonus_predictions(bonus_predictions, bonus_results) -> points breakdown`
- Write `tests/test_scoring.py` with real F1-flavored fixtures covering: exact match, off-by-one match, no match, multiple DNFs, all-bonus types, empty/partial predictions.
- This is the highest-risk part of the app to get subtly wrong — do not proceed until every rule from the spec has at least one test.

**Checkpoint:** `pytest tests/test_scoring.py` fully green, and you can walk through each rule from the spec pointing to the test that covers it.

---

## Phase 3 — Auth & users
- Registration (username + password, hashed), login, session handling.
- Admin flag on user model; at least one seeded admin account.
- Middleware/dependency to protect admin-only routes.

**Checkpoint:** can register, log in, log out, and hit an admin-only route only when logged in as admin.

---

## Phase 4 — Roster & event admin
- Admin routes/UI to: edit team names, edit driver names, mark a driver active/reserve, create an event, set its grid size and whether it has a sprint, and set the `event_entries` (who's actually racing that weekend, including substitutions).
- This is where the "flexible, admin-editable" requirement from the spec gets exercised — test that changing a name mid-season doesn't corrupt past events' data.

**Checkpoint:** admin can fully set up a new race weekend through the UI without touching the DB directly.

---

## Phase 5 — Predictions UI
- Routes/templates for a user to submit predictions for qualifying, sprint (if applicable), and race, plus the race bonus questions.
- Enforce the uniqueness rules (no duplicate position, no duplicate driver per session) at the form level and the DB level.
- Apply the lock-time / edit-until-lock behavior noted as an open decision in the spec — confirm the assumed default with the user if not already resolved.

**Checkpoint:** a non-admin user can log in and submit a full set of predictions for a seeded event.

---

## Phase 6 — Results entry & points calculation
- Admin route to enter actual results (positions + DNF flags) and bonus outcomes for an event.
- Wire the Phase 2 scoring engine to real predictions/results, writing to `points_log`.
- Build the leaderboard view (season total, and per-event breakdown using `points_log.detail`).

**Checkpoint:** enter a full set of fake results for the seeded event, confirm the leaderboard matches hand-calculated points.

---

## Phase 7 — PWA polish
- Add `manifest.json`, icons, and a minimal service worker for offline shell caching.
- Confirm install-to-home-screen works on an actual phone (Android Chrome and iOS Safari both, if possible — they behave differently).

**Checkpoint:** app installs to a phone home screen and opens without browser chrome.

---

## Phase 8 — Admin & UX fixes
- Roster admin: add "create" routes for teams and drivers (in addition to existing rename), and "delete" routes for teams, drivers, and events. Deletes must be blocked (with a clear error) when dependent predictions/results/points_log/bonus rows exist.
- Event creation: drop the manual round-number field from the create-event form. Auto-assign it from a new `Season.next_round_number` counter, incremented on each event creation. Add an admin control to edit `next_round_number` directly, so a season starting mid-year can set its first round number correctly.
- Nav cleanup: the top-nav "Leaderboard" link and bottom-nav "Standings" link both point at the same `/leaderboard` route — rename both to "Standings" for consistency.
- Add a self-service `/settings` page (any logged-in user, including admins) to change username and/or password, verified against the current password. Reuse the existing `hash_password`/`verify_password` helpers from `app/auth.py`.

**Checkpoint:** admin can add and delete a team/driver/event (and sees a clear block message when deletion isn't safe), a new event's round number is auto-filled correctly after adjusting the season's starting round, both nav links read "Standings", and a non-admin user can change their own password from `/settings`.

---

## Phase 9 — Deploy
- Push to GitHub.
- Create Supabase project, run migrations against it.
- Deploy to Render as a web service, environment variables set from `.env.example`.
- Full smoke test on the live URL from a phone.

**Checkpoint:** friends can register and use the real deployed app.
