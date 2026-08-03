# BOARD

Kanban for PARITY work. One line per item, referencing its PRD identifier
(§/P-/F-). See `.claude/rules/task-tracker.md`.

> Note: `docs/prd-parity.md` referenced by the rules does not exist yet — identifiers
> below point at `.claude/rules/product-principles.md` (§2.3 anti-reqs, P-1…P-9) until it lands.

## Todo

- §2.3 date resolver off-by-one — `last_Nd` spans N+1 days (`today-N..today`); make it exactly N (`today-(N-1)..today`). Shared resolver → shifts read + write together.

## In Progress

## Done

- 2026-08-03 §2.3 / P-7 — Meta workers resolve `date_preset`→`time_range` in account tz (one resolver, read==write). Test: `backend/tests/test_date_range_parity.py`.
