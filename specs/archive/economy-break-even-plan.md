# Economy: the average team breaks even — Implementation Plan

**Spec:** `specs/archive/economy-break-even.md` · **Issue:** #125 · **Status:** implemented
**Apps touched:** `economy/`, `competitions/`, `world/` (docs only), `scripts/`

## Context you need

All of the game's money is append-only `LedgerEntry` rows (`economy/README.md`).
The flows that matter here:

- **Wages.** Each rider has their own `weekly_salary` (`riders/pricing.py`),
  charged weekly. Out of scope: not touched.
- **Sponsorship.** `economy/sponsors.py`'s `offer_terms` sizes an offer as
  `(fanbase // SPONSOR_FANBASE_PER_CREDIT) × profile.base_multiplier`.
  The constant lives in `economy/models.py` and is passed in
  by `economy.services.ensure_offer_round`. A contract **copies** its terms at
  signing (`economy/README.md`, *Sponsorship*), so changing the constant never
  reprices a signed contract. Spec rule: "signed contracts keep their terms",
  which comes for free.
- **Prize money.** Three tables in `competitions/scoring.py`:
  `PRIZE_BY_POSITION` (one-day races), `STAGE_PRIZE_BY_POSITION` (each stage,
  half the one-day table) and `GC_PRIZE_BY_POSITION` (double the one-day
  table). `competitions/tests/test_scoring.py` pins both ratios, and the new
  numbers must keep them. Paid prizes are ledger rows, so new values affect
  only races settled after the change. Spec rule: "no retroactive top-up",
  which also comes for free.
- **The measurement.** `world/README.md`, *Balances, measured*, records a
  seeded two-season run. It was done by hand. This ticket adds
  `scripts/measure_economy.py`, so it can be repeated.

The figure `world/README.md` quotes (season 2 net ≈ −$40k) came from a run
with one claimed team taking a share of the prizes. Re-measured with
`scripts/measure_economy.py` on master (16 unmanaged teams, season 2, the
steady state, average per team, 12 weeks): prizes ≈ +$92.6k (one-day $78.1k,
GC $14.5k), sponsorship ≈ +$48.9k, merchandise ≈ +$4.3k, trainer salary
≈ −$34.5k, wages ≈ −$179.9k, **net ≈ −$68.5k**. The bottom quarter averaged
−$135.5k, the median −$92.2k and the top quarter +$47.3k. The spec's target is
**+$10k to +$20k**, so about **+$83k a season** has to be found.

## Goal

Change two constants so the average team in a settled season ends $10–20k
up, with most of the increase coming from sponsorship. Prove it with a
repeatable measurement, and write the targets down.

## Design decisions

1. **Sponsorship grows ×2.2.** The divisor `SPONSOR_FANBASE_PER_CREDIT = 2`
   becomes a rate, `SPONSOR_CREDITS_PER_THOUSAND_FANS = 1_100` (the old divisor
   is 500 on this scale), and `offer_terms` computes
   `fanbase × rate // 1000 × multiplier`, so the result stays whole credits.
   At the starting fanbase a steady offer goes from $4,250 to $9,350 a week,
   about +$61k a season, most of the gap. (First set at 1,250, ×2.5; see
   *Verification* for why it came down.) A divisor can only express
   ×2 (divisor 1) or ×1, and ×2 (+$49k) would have pushed about $34k, a 37%
   rise, onto prizes, against the spec's "most from sponsorship". The
   profiles' relative shape (0.85 / 1.0 / 1.25 base, their floors and
   ceilings) is unchanged, so spec item 4 holds by construction. *Rejected:*
   rescaling the three profile multipliers instead. That would break
   "balanced = 1.0 = the baseline", which the docs and the Sponsors screen's
   copy lean on.
2. **Prize money goes up 10%, across all three tables.** About +$9k a season
   for the average team, more for the top teams. One-day: 22,000 / 16,500 /
   13,200 / 11,000 / 8,800 / 6,600 / 4,400 / 3,300 / 2,200 / 1,100. Stage: half
   of that. GC: double it. This keeps both ratios the tests enforce.
3. **Projected result** (at the first rate, 1,250): −68.5k + 73k + 9k ≈ **+$14k**, mid-band. It measured +$28k; see *Verification*, *Outcome*. The bottom
   quarter comes in near −$60k a season, about eight seasons of a starting
   balance (spec item 3), and the top quarter near +$140k (item 2). Merchandise and the AI's trainer choice add noise of a few thousand,
   so the measurement decides. If it lands above +$20k, lower the rate (1,200 is about −$5k a season). If it lands below +$10k, report back rather than inventing a third lever.
4. **The measurement is a script, not a management command.** It drops and
   recreates the dev database, which no management command in this repo does,
   and it exists for whoever tunes the economy, not for running the game. It lives
   in `scripts/` beside `dev_db.py`. It reports by ledger kind and season
   (attributing by `occurred_at` inside the season's range, because merchandise
   and fee rows carry no week), excludes transfer fees from the net (AI market
   churn, not a structural flow), and prints the bottom-quarter, median and
   top-quarter season-2 net (spec items 2 and 3).
5. **The targets live in `economy/README.md`**, in a new *Balance targets*
   section beside the measured table. They are the standing record a future
   tuning change is checked against. `world/README.md`'s *Balances, measured*
   gets the new numbers and points there.

## Work items

**W1 — The measurement script.** `scripts/measure_economy.py`. Run it on master
first and record the baseline output in the PR.

**W2 — Retune the constants.** `economy/models.py`: replace
`SPONSOR_FANBASE_PER_CREDIT` with `SPONSOR_CREDITS_PER_THOUSAND_FANS = 1_100`
and rewrite its comment (at the starting fanbase a balanced offer is $11,000 a
week). `economy/sponsors.py`: `offer_terms` takes `credits_per_thousand_fans`.
`economy/tests/test_sponsor_maths.py` passes `credits_per_thousand_fans=500`,
the old divisor's equivalent, so its expectations are unchanged. `competitions/scoring.py`: the three prize tables, +10%.
Tests:
- `competitions/tests/test_scoring.py`: update the pinned amounts (this
  behaviour is meant to change). The ratio tests stay as they are and must pass.
- `economy/tests/test_sponsorship.py`: add
  `test_offer_round_at_starting_fanbase_pays_the_calibrated_baseline`. It
  generates a round for a team at `STARTING_FANBASE` through the service and
  asserts steady = 9,350, balanced = 11,000 and demanding = 13,750, so a
  future divisor change is a visible test edit, not a silent drift.

**W3 — Measure and document.** Run the script. If the average falls outside
+$10k–$20k, adjust the prize rise as decision 3 says and re-run. Then:
`economy/README.md` gets a new *Balance targets* section (spec items 1–3, the
measured table, the script's command) and an updated *Future work* bullet on
unmanaged insolvency. `world/README.md` gets its *Balances, measured* replaced
with a short pointer and the new steady-state line. `competitions/README.md`
gets its prize amounts updated if it quotes them.

**W4 — Close the ticket.** Set both specs to `implemented` and move them to
`specs/archive/`.

## Execution order

W1 → W2 → W3 → W4. One commit each.

## Verification

The evidence is the script's before and after output, not a passing test: a
test cannot show the average team breaks even. Paste both outputs into the PR.

**Outcome.** Three runs, season 2 average net per team: rate 1,250 →
+$28,159 (median +$9,614); 1,150 → +$26,228 (median +$23,742); 1,100 →
+$10,818 (median +$11,816, bottom quarter −$89,820, top quarter +$151,394).
Prize totals are close to fixed (the pot is shared by 16 teams). The noise
is wages, the trainer each team ends up with (−$28k to −$38k a season) and
fanbase, about ±$8k between runs, which is bigger than the 1,250-to-1,150 step.
1,100 was chosen to centre the band across the runs rather than to fit one.
The top quarter is about 14× the average surplus. That is above the
"ten times" sanity line in *Risks*, but only because the average is small.
In money terms (+$150k a season against a $500k start) it is not absurd.

## Risks

| Risk | Mitigation |
|---|---|
| A demanding sponsor's ceiling grows too (about $30k a week at the starting fanbase), so a top team on a hot streak earns a lot. | That is spec item 2 ("a clear profit"). Check that the top-quarter line isn't absurd, meaning more than about ten times the average surplus. |
| Merchandise and the trainer pool make the average jitter by a few thousand between runs. | The band is $10k wide. Run once, and run again only if the result sits within $2k of an edge. |
| Fanbase drifts up for winners, so their next season's offers grow. | That already happens today, and the bigger rate only makes it proportionally more visible. Accepted: fanbase is meant to matter more (spec, Decisions). |
