---
name: f1-scoring-rules
description: Use this skill whenever writing, reviewing, or debugging scoring/points logic for the F1 prediction league — qualifying, sprint, race, DNF ordering, or race bonuses. Load before touching app/scoring.py or tests/test_scoring.py.
---

# F1 Prediction League — Scoring Rules

This is the authoritative reference for point calculation. If code and this file disagree, this file is right — fix the code.

## Position scoring (qualifying, sprint, race)

Applies per predicted position, independently:

- Predicted driver's actual finishing/qualifying position **exactly matches** the predicted position → **3 points**
- Predicted driver's actual position is **exactly one away** (either direction) from the predicted position → **1 point**
- Otherwise → **0 points**

Example: user predicts Driver X for P3.
- Driver X actually finished P3 → 3 points
- Driver X actually finished P2 or P4 → 1 point
- Driver X actually finished P1, P5, or anywhere else → 0 points

This is evaluated per position slot independently — there is no bonus or penalty for getting multiple positions right/wrong in combination, and no requirement that predictions be internally consistent as a permutation (though the UI should still prevent picking the same driver twice or leaving a position unfilled).

## Session scope

| Session | Positions predicted |
|---|---|
| Qualifying | Top 10 only |
| Sprint | Full grid (event's `grid_size`, default 22) — only on events where `has_sprint` is true |
| Race | Full grid (event's `grid_size`, default 22) |

Grid size is per-event, not hardcoded — read from `events.grid_size`.

## DNF ordering (race only)

DNF'd drivers still occupy final classification positions, placed after all classified finishers.

Among multiple DNFs, order by **retirement time**: the driver who retired **first** gets the **last** overall position; the driver who retired **second** gets second-to-last; and so on, working backwards.

Example: grid size 20, 3 drivers finish, 2 DNF (Driver A retires lap 10, Driver B retires lap 30).
- Finishers occupy positions 1–17 (in their finishing order — adjust count for actual number of finishers)
- Driver B (retired later, lap 30) occupies position 19 (second-to-last)
- Driver A (retired first, lap 10) occupies position 20 (last)

This final position is what position-scoring above compares predictions against — DNF drivers are not excluded from scoring, they're just ranked last by retirement order.

## Race bonuses (race only, each independent, no partial credit)

| Bonus | Prediction type | Points if correct |
|---|---|---|
| First driver to receive a penalty | Pick a driver | 5 |
| First driver to pit | Pick a driver | 5 |
| Red flag shown during race | True/False | 3 |
| Safety car deployed | True/False | 3 |
| Virtual safety car deployed | True/False | 3 |
| Number of classified finishers (non-DNF) | Exact number | 3 |
| MVP driver of the race | Pick a driver | 3 |
| Fastest lap driver | Pick a driver | 3 |

Each bonus is all-or-nothing — no partial credit for being close on the finisher count.

## Implementation notes

- Keep the scoring functions pure (plain data in, points out) so they're trivially unit-testable without a DB or FastAPI app context.
- Every rule above should have at least one corresponding test case in `tests/test_scoring.py` before a scoring change is considered complete.
