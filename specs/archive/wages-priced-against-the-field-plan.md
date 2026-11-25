# Wages priced against the field: plan

**Status:** implemented
**Spec:** `specs/archive/wages-priced-against-the-field.md`
**Issue:** [#166](https://github.com/mario595/cycling-manager/issues/166)

## Approach

Keep both price curves exactly as they are and change their input: a
rider's `strength()` is multiplied by a **field factor** before it reaches
`weekly_salary_for` or `market_value_for`. A factor of 1.0 is today's
price. At each season close the factor is solved from the rostered field
so that its average weekly salary is `FIELD_AVERAGE_SALARY` (1,200, the
flat wage the curve was calibrated to). As the world trains, strength
rises, the factor falls, and the average wage stays where it was.

Why a strength multiplier rather than a salary multiplier: a multiplier on
the salary itself would scale every wage by the same percentage, so the
weakest riders, already near the curve's floor, would fall below it. Moving
the input keeps the curve's shape, its floor and its ceiling, and how pay
splits between strong and weak riders.

## Design decisions

1. **Stored, append-only `FieldLevel(factor)` in `riders/`.** The newest row
   is the factor in force; no row means 1.0. Append-only keeps the history
   of the world's level for diagnosis and makes "frozen between closes"
   true by construction: nothing writes a row except the close.
2. **Solved by bisection** over 0.5-2.0 (`solve_field_factor`). The average
   salary is monotonic in the factor, so 40 halvings is exact far below a
   rounding step. Out of range, it returns the bound (the spec's *bounded*
   rule).
3. **The field is `team_id is not None` among the active riders `reprice_all`
   already lists.** Development squad youth have `team = NULL`, so they fall
   out with free agents, as the spec asks. Under 40 rostered riders
   (`FIELD_MIN_RIDERS`) nothing is recorded and the current factor is kept,
   so a test world or an empty one never swings the price.
4. **Pure functions default to `field_factor=1.0`.** Data migrations (riders
   0008's salary backfill) and existing tests keep today's prices. Live
   callers pass `current_field_factor()`: generation (free-agent and youth
   intake, a claim's top-up, `seed_teams`), squad promotion, every transfer
   fee, the AI market, the expiry pass and the API.
5. **The review line is computed in `world/`.** `world.services` reads the
   factor before and after `reprice_all()` and turns it into
   `field_change_percent = round((before / after - 1) × 100)`, stored on
   each `SalaryReviewReport` (nullable, so pre-#166 reports show nothing).
   `riders/` may not import `economy/`, so `world/` is the right seam.
6. **No data migration.** The first close after deploy measures the field
   and reprices everyone.

## Work items

1. `riders/`: `FieldLevel` and migration, `pricing.solve_field_factor` and
   the factor argument, `field_level.current_field_factor`,
   `services.measure_field_level` called by `reprice_all`.
2. Prices set during a season use the current factor: `generation`, intake,
   triage, `teams/`, `transfers/`, `world/ai_market.py`, `world/services.py`
   expiry, `api/`.
3. The review line: `SalaryReviewReport.field_change_percent` and migration,
   `write_salary_reviews(..., field_change_percent=)`, the season close in
   `world/services.py`, the serializer, `fieldChangeNote` on the roster.
4. Tests for each, then a four-season world-calendar measurement compared
   with the #166 baseline.
5. Docs: riders *Salary*, transfers *Value vs salary*, economy *Salary
   review* and *Balance targets*, world season close, api, frontend,
   AGENTS.md, `PLAYERS_GUIDE.md`.

## Verification

- `riders/tests/test_pricing.py`: a generated field solves to about 1.0; a
  strengthened field solves below 1.0 and averages 1,200; bounds; empty.
- `riders/tests/test_services.py`: `reprice_all` records a level from the
  rostered field, ignores free agents, keeps the level for a small field.
- Intake prices at the stored level; market value scales with the factor;
  the review stores and serves the percentage; the season close writes it.
- The measurement: on the world calendar, the average team should stay in
  the #125 band (+$10k to +$20k) every season instead of drifting down.
