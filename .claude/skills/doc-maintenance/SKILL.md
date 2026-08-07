---
name: doc-maintenance
description: Use this skill whenever a change is made to game rules, scoring logic, the database schema, the tech stack, or the project's architecture — and before considering that change complete. Also use when explicitly asked to update documentation. Keeps README.md, CLAUDE.md, f1_prediction_league_spec.md, and implementation_order.md in sync with the actual codebase.
---

# Documentation Maintenance

Documentation drifting from the real codebase is worse than no documentation — it actively misleads. This project has four docs that must stay consistent with each other and with the code. Check all of them, not just the one that seems most obviously related.

## The docs and what each owns

| File | Owns |
|---|---|
| `f1_prediction_league_spec.md` | Full rules, full schema, open decisions — the source of truth for *what* the app does |
| `README.md` | User-facing summary of rules + high-level architecture — a shorter, friendlier version of the spec |
| `CLAUDE.md` | Conventions, guardrails, stack choices — the source of truth for *how* code should be written |
| `implementation_order.md` | Build sequencing — only changes if the plan itself changes, not for every feature |
| `.claude/skills/f1-scoring-rules/SKILL.md` | Exact scoring algorithm — must match the rules described above 1:1 |

## When to trigger this skill

- A game rule changes (new bonus type, changed point value, changed session structure, etc.)
- The database schema changes (new table, new column, renamed field, changed relationship)
- The tech stack or a major architectural decision changes (new library, changed hosting, changed auth approach)
- Any time you're about to say a task is "done" and that task touched rules, schema, or architecture

## What to do

1. Identify every doc file whose content is now stale (use the ownership table above — a rule change likely touches at least `f1_prediction_league_spec.md`, `README.md`, and possibly `.claude/skills/f1-scoring-rules/SKILL.md`).
2. Update each one to match the actual current rules/schema/code. Don't just add a note — edit the relevant section directly so the doc reads as if it were always correct.
3. Keep wording and structure consistent with the rest of each file (same table formats, same heading levels) rather than appending a mismatched-style addendum.
4. If the change affects `implementation_order.md`'s remaining phases (e.g. a new table means a data-model phase needs a new bullet), update that too — but don't touch phases already marked complete.
5. Report which files you updated and what changed in each, so it's easy to verify.

## What not to do

- Don't update docs speculatively for changes that haven't actually been made yet.
- Don't let `README.md` and `f1_prediction_league_spec.md` say different things about the same rule — if there's a discrepancy, the spec is authoritative; fix the README to match it.
- Don't remove the "Open Decisions" section from the spec until those decisions are actually resolved in code.
