# F1 Prediction League — Project Spec

## Overview
A mobile-installable web app (PWA) for a small friend group (<20 users) to bet on F1 qualifying, sprint, and race results each week, earning points based on prediction accuracy plus race bonuses. Users self-register and can join mid-season at 0 points.

---

## Tech Stack
- **Backend:** FastAPI (Python)
- **Frontend:** Jinja2 templates + HTMX (server-rendered, app-like feel without a separate JS build), plus SortableJS (via CDN) for the drag-and-drop driver-ranking control on the prediction forms
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
- Admins can also add and delete teams, drivers, and events from the admin UI. A delete is blocked (with an explanation) if the row has dependent data — a team with drivers, a driver with predictions/results/entries, or an event with predictions/results/bonus data/points — to avoid orphaning or silently destroying scored history.
- Each race weekend has its own actual "entry list" (who's really racing that week), separate from the season roster — this is what substitutions get recorded against, and what predictions/results are scored against, so a one-off substitute doesn't affect the permanent roster.

### Users
- Self-registration: username + password.
- Can join at any point in the season, starting at 0 points (points are always computed from logged history, never a manually-reset counter).
- Admin flag on at least one account for roster/name management.
- Self-service settings page (`/settings`) lets any user, including admins, change their own username and/or password after confirming their current password. Admins can still force-reset another user's password to a default value for account-recovery cases.

### Prediction Lock Time
- Each session (qualifying, sprint, race) has its own start time, set by the admin when creating the event.
- Predictions for a session lock automatically, server-side, once that session's start time passes — enforced on both the submission route and the UI (a locked session renders read-only instead of an editable form).
- Before the lock, users can freely edit/resubmit predictions any number of times; only the latest version at lock time is scored.
- Race bonus predictions share the race session's lock time.

### Predicted-Order Input
- Users set their predicted finishing order by dragging driver cards into place (mouse or touch), or via ▲/▼ buttons for keyboard/non-drag use — both produce the same ordered list.
- When a session predicts fewer positions than there are entered drivers (qualifying's top-10 cap with a larger grid), unranked drivers sit in a separate pool below the ranked list; drivers move between the pool and the ranked list via drag or a +/− button. All positions must be filled before saving.
- Driver cards show name, car number, team, and a team-color accent stripe; the locked/read-only view renders the same information without any editable controls.

---

## Database Schema (draft)

**seasons**
`id, year, name, default_grid_size, next_round_number`
`next_round_number` is the round number the next created event will be auto-assigned; it increments on event creation and is directly editable by an admin, so a season that starts mid-year can set its first event to the correct round instead of always starting at 1.

**Season reset**: an admin action (`/admin/season/reset`) deletes all events for the current season (and their entries, predictions, results, bonus predictions/results, and points log rows) and resets `next_round_number` back to 1, so the season can start over with a clean schedule. Teams and drivers are left untouched. This is a hard, unrecoverable delete — not an archive.

**teams**
`id, season_id, name, color`
`color` is an optional hex string (e.g. `#3671C6`), admin-editable, used as the accent color on driver cards in the prediction UI.

**drivers**
`id, season_id, team_id, name, is_reserve, car_number, active`

**events** (race weekends)
`id, season_id, round_number, name, has_sprint, grid_size, qualifying_start_time, sprint_start_time, race_start_time`
`sprint_start_time` is only set when `has_sprint` is true. Each session's predictions lock automatically once its start time passes — see Prediction Lock Time below.

**event_entries** (actual field for a given weekend — handles substitutions/missing drivers)
`id, event_id, driver_id, is_substitute, substituted_for_driver_id`

**users**
`id, username, password_hash, is_admin, created_at`

**sessions**
`token (PK), user_id, created_at, expires_at`
Server-side login sessions: the client holds only an opaque, randomly generated token (in an HttpOnly cookie); each row here is the server-side record it maps to. A session is valid only while a matching, unexpired row exists — logging out deletes the row.

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
- Unique per (user, event, session_type)
- Race bonus points are folded into the `race` row (there's no separate `session_type` for bonuses): `points` is position points + bonus points combined, and `detail` carries both breakdowns (`{"position": [...], "bonus": [...]}`) so they can still be shown separately.
- Recomputed (upserted) automatically whenever an admin enters or edits results for that session, or bonus results for a race.

---

## Open Decisions (defaults assumed — confirm or override before/at build time)
1. **MVP definition:** assumed this refers to F1's official "Driver of the Day" fan vote result (published after each race), entered by the admin like any other result. If you mean something else (e.g. your own group's subjective pick), let me know — it changes nothing structurally (still a driver pick, 3 pts) but affects how the admin sources the correct answer.

---

## Suggested Build Order
1. Data model + migrations (tables above) against local Postgres/SQLite.
2. Core scoring engine (position comparison, DNF ordering, bonus scoring) — test this in isolation first since it's the trickiest logic.
3. FastAPI routes: auth/registration, admin roster management, prediction submission, results entry (admin), leaderboard.
4. Jinja2 + HTMX templates for the above.
5. PWA manifest + service worker; test install-to-home-screen on phone.
6. Push to GitHub → connect Supabase → deploy to Render.
7. End-to-end walkthrough with real accounts.
