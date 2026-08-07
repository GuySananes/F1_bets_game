# F1 Prediction League — Project Spec

## Overview
A mobile-installable web app (PWA) for a small friend group (<20 users) to bet on F1 qualifying, sprint, and race results each week, earning points based on prediction accuracy plus race bonuses. Users self-register and can join mid-season at 0 points.

---

## Tech Stack
- **Backend:** FastAPI (Python)
- **Frontend:** Jinja2 templates + HTMX (server-rendered, app-like feel without a separate JS build)
- **PWA:** manifest.json + service worker for home-screen install
- **Database:** PostgreSQL on Supabase (free tier, permanent — not a trial)
- **Hosting:** Render (free web service tier, permanent — not a trial; note: spins down after ~15 min inactivity, ~30s cold start on wake)
- **Auth:** Simple username/password with hashed passwords + sessions (no OAuth needed for this scale)

---

## Game Rules

### Sessions (each race weekend)
1. **Qualifying** — predict exact order of **top 10** drivers.
2. **Sprint** — predict exact order of **all drivers on the grid** (default 22, configurable per event). Not every weekend has a sprint.
3. **Race** — predict exact order of **all drivers on the grid**, plus bonus questions.

### Position Scoring (applies to qualifying, sprint, race)
For each position you predicted:
- Exact match → **3 points**
- Off by exactly 1 (actual is one position above or below your guess) → **1 point**
- Otherwise → 0 points

### DNF Handling (race only)
- DNF drivers are still assigned a final classification position, placed after all finishers.
- Among multiple DNFs, ordered by retirement time: the **first** driver to retire gets the **last** position, the second-to-retire gets second-to-last, etc.

### Race Bonuses (race only)
| Bonus | Type | Points |
|---|---|---|
| First driver to receive a penalty | Pick a driver | 5 |
| First driver to pit | Pick a driver | 5 |
| Red flag shown | True/False | 3 |
| Safety car deployed | True/False | 3 |
| Virtual safety car deployed | True/False | 3 |
| Number of classified finishers (non-DNF) | Number | 3 |
| MVP driver of the race | Pick a driver | 3 |
| Fastest lap driver | Pick a driver | 3 |

### Teams & Drivers
- Season-specific: 11 teams this season (10 last season) — team count and grid size vary by year, so nothing is hardcoded.
- 2 primary drivers per team, plus one or more reserve/spare drivers who may substitute in for a given race weekend.
- Default team/driver names are seeded at season start but must be editable by an admin at any time (renames, roster corrections).
- Each race weekend has its own actual "entry list" (who's really racing that week), separate from the season roster — this is what substitutions get recorded against, and what predictions/results are scored against, so a one-off substitute doesn't affect the permanent roster.

### Users
- Self-registration: username + password.
- Can join at any point in the season, starting at 0 points (points are always computed from logged history, never a manually-reset counter).
- Admin flag on at least one account for roster/name management.

---

## Database Schema (draft)

**seasons**
`id, year, name, default_grid_size`

**teams**
`id, season_id, name`

**drivers**
`id, season_id, team_id, name, is_reserve, car_number, active`

**events** (race weekends)
`id, season_id, round_number, name, has_sprint, grid_size`

**event_entries** (actual field for a given weekend — handles substitutions/missing drivers)
`id, event_id, driver_id, is_substitute, substituted_for_driver_id`

**users**
`id, username, password_hash, is_admin, created_at`

**predictions**
`id, user_id, event_id, session_type [qualifying|sprint|race], predicted_position, driver_id`
- Unique per (user, event, session_type, predicted_position)
- Unique per (user, event, session_type, driver_id)

**results**
`id, event_id, session_type, actual_position, driver_id, dnf`

**bonus_predictions**
`id, user_id, event_id, bonus_type, driver_id, bool_value, int_value`
(only the relevant value column populated per bonus_type)

**bonus_results**
`id, event_id, bonus_type, driver_id, bool_value, int_value`

**points_log**
`id, user_id, event_id, session_type, points, detail (JSON breakdown)`

---

## Open Decisions (defaults assumed — confirm or override before/at build time)
1. **MVP definition:** assumed this refers to F1's official "Driver of the Day" fan vote result (published after each race), entered by the admin like any other result. If you mean something else (e.g. your own group's subjective pick), let me know — it changes nothing structurally (still a driver pick, 3 pts) but affects how the admin sources the correct answer.
2. **Prediction lock time:** assumed each session has a deadline (e.g. session start time) after which predictions are locked and read-only. Confirm whether this should be enforced in-app or left trust-based among friends.
3. **Editing predictions:** assumed users can freely edit/resubmit predictions any number of times before the lock, with only the final version scored.

---

## Suggested Build Order
1. Data model + migrations (tables above) against local Postgres/SQLite.
2. Core scoring engine (position comparison, DNF ordering, bonus scoring) — test this in isolation first since it's the trickiest logic.
3. FastAPI routes: auth/registration, admin roster management, prediction submission, results entry (admin), leaderboard.
4. Jinja2 + HTMX templates for the above.
5. PWA manifest + service worker; test install-to-home-screen on phone.
6. Push to GitHub → connect Supabase → deploy to Render.
7. End-to-end walkthrough with real accounts.
