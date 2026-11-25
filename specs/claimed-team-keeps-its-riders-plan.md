# A claimed team keeps its riders — Implementation Plan

**Spec:** `specs/claimed-team-keeps-its-riders.md` · **Issue:** #156 · **Status:** proposed
**Apps touched:** `teams/`, `api/` (description only), `scripts/measure_economy.py`, `beta_agents/` (guide), docs

## Context you need

`teams.services.claim_team(user, *, name, code, roster_size=ROSTER_SIZE, at)`
(`teams/services.py`) is the only way a human gets a team. Today, in one
transaction, it does the following:

1. It locks the **lowest-pk** unmanaged team with
   `select_for_update(skip_locked=True)`.
2. It renames the team.
3. It **releases every rider** to the free-agent pool
   (`mark_team_change(..., team_now=None)` then `team.riders.update(team=None)`).
4. It **generates** `roster_size` new riders (`riders.generation.generate_roster`),
   stamps their `joined_team_at = at` (`mark_team_change(..., team_now=team)`)
   and writes their baseline snapshots (`record_initial_snapshots`).
5. It closes the development squad, then resets the balance and fanbase and
   voids sponsorship (lazy `economy` imports).

`api.views.ClaimTeamView` wraps it with `withdraw_bids` and `cancel_listings`
in one outer transaction. `seed_teams --claim-for` calls it directly.

**Why this ticket exists.** On staging, steps 3–4 put every late claimant
below the whole field: a fresh roster's top four average about 204 raw
strength, while the AI field is at about 290 after three seasons of training.
The spec reverses that: keep the riders, hand over the middle team, and top up
a short roster.

**The claim cooldown depends on `joined_team_at`.**
`transfers.services._claim_cooldown_exempt` frees a rider's release only when
`rider.joined_team_at == team.managed_since`. Inherited riders must therefore
still be stamped `joined_team_at = at`, or the spec's "free release during the
cooldown is unchanged" quietly breaks.

Rules this is bound by (see `AGENTS.md`): `teams -> riders` is allowed at
module scope, `teams -> economy` only lazily inside function bodies, and
`teams/` must not import `world/`, `transfers/` or `racing/`. Read
`teams/README.md`, *Claiming a team*, before starting.

## Goal

- `claim_team` keeps the team's riders and stamps them `joined_team_at = at`.
- It hands over the unmanaged team whose squad strength is closest to the
  field's median, and it is still safe under concurrent claims.
- It tops a roster under `roster_size` up to `roster_size` with generated
  riders, and only those riders get baseline snapshots.
- Everything else a claim does is untouched.
- `scripts/measure_economy.py` claims a team before the measured season and
  reports it next to the AI field.
- The players' guide, the API description and the READMEs say the squad comes
  with the team.

## Design decisions (settled — implement these, do not substitute)

1. **Squad strength = the mean `riders.pricing.strength()` of the team's best
   `SQUAD_STRENGTH_DEPTH = 8` riders, with missing places counted as 0.**
   - Why 8: a squad is four riders, and eight covers a rotation and a stage
     race's fatigue. The whole roster is the wrong measure, because a 30-rider
     roster of filler would read as weak. The top four is too noisy.
   - Missing places count as 0 so that a stripped team (say 3 riders) ranks
     as weak rather than as "three good riders".
   - Use `riders.pricing.strength`, not the raw attribute sum. It is the
     game's existing "how good is this rider" measure, and it already drives
     salary and market value.
   - Only `Rider.objects.filter(team=team)` counts, which is what
     `team.riders` already is. Development squad riders have `team = NULL`,
     so they are excluded automatically, and retired riders have no team.
   - Put it in `teams/services.py` as a module-level function
     `squad_strength(riders: list[Rider]) -> float`, pure over a list so it
     can be tested without a database.
2. **The field is every `Team` row; the candidates are the unmanaged ones.**
   - The median is taken over all teams, managed or not, per the spec. Use
     `statistics.median`.
   - Rank the candidates by `(abs(score - median), pk)`. The pk tiebreak is
     what makes "the same world gets the same team" true and testable.
   - **Load-bearing:** compute the scores *without* a lock, then walk the
     ranked candidates. For each one, try
     `Team.objects.select_for_update(skip_locked=True).filter(pk=c, manager__isnull=True).first()`
     and take the first that returns a row. Do **not** lock every
     unmanaged team up front: that serialises concurrent claims, which
     `skip_locked` exists to avoid. Do **not** lock the first by pk and then
     "switch": that is exactly today's bug.
   - If no candidate locks, raise `NoTeamAvailable`, as today.
   - Read all teams' riders in one query
     (`Rider.objects.filter(team__isnull=False)`), grouped in Python. Sixteen
     teams of 12 is trivial, and N queries are not needed.
3. **Inherited riders are kept and re-stamped.** Replace step 3 with
   `mark_team_change(list(team.riders.all()), team_now=team, at=at)`. This
   sets `joined_team_at = at` and clears `unattached_since` (already None),
   which keeps the cooldown exemption working. Do **not** write new baseline
   snapshots for them: they already have history, and a second `week=None`
   snapshot would break `record_initial_snapshots`' "one baseline" invariant.
4. **Top-up fills only the gap.**
   `missing = max(0, roster_size - team.riders.count())`, then
   `generate_roster(missing, team=team)`, `mark_team_change` and
   `record_initial_snapshots` on those riders only. Keep the `roster_size`
   parameter as "the size a short roster is topped up to". `roster_size=0`
   (used by `api/tests.py`) then means "no top-up", which keeps that test's
   intent. A roster above `roster_size` is never trimmed.
5. **Order inside the transaction.** Pick and lock, rename, re-stamp the kept
   riders, top up, `close_squad`, then the economy resets. `close_squad`
   stays after the roster write, as the README requires. It does not touch
   `team.riders` (squad riders have `team = NULL`), so the top-up count is
   not affected by it.
6. **No change to `transfers/`, `economy/`, `staff/` or `world/` code.**
   Listings and bids are still cancelled by `ClaimTeamView`. A rider the AI
   listed (seller = this team) stays on the roster when the listing is
   cancelled, which is what we want. A forced-sale rider (insolvency) has
   already left the roster at listing and is excepted from cancellation, as
   today.
7. **The measurement claims one team before the measured season.** In
   `scripts/measure_economy.py`, after ticking through every season but the
   last, claim with a throwaway user (created with `User.objects.create_user`),
   then run `withdraw_bids` and `cancel_listings`, mirroring
   `ClaimTeamView`. Keep ticking day by day. Directly after the first tick of
   the last season, call `ensure_offer_round` and sign that team's
   `AI_SPONSOR_PROFILE` offer (`economy.services.sign_offer`), the same thing
   `world.ai_management.sign_ai_sponsors` does for AI teams. A passive human
   who signs the steady sponsor and touches nothing else is the "average
   team" the target describes.
   - Report the claimed team's last-season net, its squad strength at the
     claim, and its strength rank in the field, next to the AI average and
     median that the script already prints. The AI figures already exclude it
     (`manager__isnull=True`).
   - Claim just before season 2 opens, the last season the script plays. Do
     **not** add a `--seasons` option or a world-calendar mode: the example
     calendar only declares two seasons, and runtime stays about 25 minutes.

## Data model

No change. No migration.

## teams/services.py

```python
#: How many of a team's best riders its squad strength averages — two
#: squads' worth. Missing places count as zero (Design decision 1).
SQUAD_STRENGTH_DEPTH = 8

def squad_strength(riders: list[Rider]) -> float: ...
def _claim_candidates() -> list[int]:
    """Unmanaged team pks, nearest the field's median squad strength first,
    pk breaking ties. Reads only; locks nothing."""
def claim_team(user, *, name: str, code: str, roster_size: int = ROSTER_SIZE, at) -> Team: ...
```

Import `strength` from `riders.pricing` at module scope (`teams -> riders` is
allowed). Rewrite the `claim_team` docstring: it no longer "releases its
riders and gives it a freshly generated roster".

## api/views.py

Change only `ClaimTeamView`'s `extend_schema` description. It must say that
the team comes with its riders, its trainer and its standings, that a roster
under twelve is topped up with new riders, and that you are given the free
team nearest the middle of the field. `api/tests.py` has a test that fails on
a missing description, so keep one.

## scripts/measure_economy.py

As in Design decision 7. Keep `_reset_database` and the printing as they are,
and add a "Claimed team" block at the end.

## Work items

### W1 — teams/services.py: `squad_strength` and `_claim_candidates`
Add both, plus `SQUAD_STRENGTH_DEPTH`. Tests in `teams/tests/test_services.py`:
- `test_squad_strength_means_the_best_eight` (riders built unsaved, 10 of
  them; the two weakest don't count).
- `test_squad_strength_counts_missing_places_as_zero` (3 riders → mean over 8).
- `test_claim_candidates_rank_by_distance_from_field_median` (three unmanaged
  teams of known strength plus one managed team that moves the median; the
  expected order is asserted).
- `test_claim_candidates_break_ties_by_pk`.

### W2 — teams/services.py: `claim_team` keeps riders, picks the middle team, tops up
This item is load-bearing: the lock walk (Design decision 2) and the
re-stamp (Design decision 3). Update the tests in
`teams/tests/test_services.py`:
- Replace `test_claim_generates_a_full_roster` with
  `test_claim_keeps_the_teams_riders` (the old rider is still on the team,
  and the count is unchanged when the team already has 12).
- Replace the released-rider test with `test_claim_keeps_riders_on_the_team`.
- `test_claim_tops_a_short_roster_up_to_twelve` (team with 3 riders → 12; the
  3 originals are among them).
- `test_claim_does_not_trim_a_large_roster` (14 → 14).
- `test_only_top_up_riders_get_a_baseline_snapshot` (an inherited rider with
  an existing baseline still has exactly one).
- `test_claim_stamps_inherited_riders_joined_team_at` (equals `managed_since`).
- `test_claim_hands_over_the_team_nearest_the_median` (weak, middle and strong
  unmanaged teams: the middle one is claimed, not the lowest pk).
- `test_claim_skips_a_locked_candidate` is hard to do with pytest-django
  transactions. Cover it instead by testing that a managed candidate is
  skipped: make the best candidate managed between ranking and locking by
  patching `_claim_candidates` to return it first. The `manager__isnull=True`
  filter inside the lock query must refuse it, and the next candidate is
  claimed.
- Update `test_claim_gives_every_new_rider_a_baseline_snapshot` to the
  top-up case.
Check `transfers/tests` for a claim-cooldown test that builds its roster
through `claim_team`. It must still pass unchanged: that is the proof for
Design decision 3. Run `world/tests/test_insolvency.py` (it claims an
insolvent team) and `api/tests.py -k claim`.

### W3 — api/views.py: claim description
Change the description text only. Test: the existing schema-description test.

### W4 — scripts/measure_economy.py: claimed-team measurement
As in Design decision 7. No unit test (the script is a measurement, like
today). Verify by running it (see *Verification*) and pasting the output into
the PR.

### W5 — docs
See *Documentation update*.

## Execution order

W1 → W2 → W3 → W5 → W4. W1 is pure and proves the ranking before it touches
the transaction. W2 is the behaviour. W3 and W5 are text. W4 last, because its
run takes about 25 minutes and should measure the final code. Commit after
each.

## Documentation update (required, not optional)

- `teams/README.md`, *Claiming a team*: rewrite steps 1, 3 and 4 (middle-team
  pick and lock walk, kept riders re-stamped, top-up). Add one line that
  explains `SQUAD_STRENGTH_DEPTH` and links the spec.
- `riders/README.md`: the lines on claim stamping (around "claim_team stamps
  every rider claimed") and on the claim's generated roster (around line 834)
  must now say inherited and top-up riders.
- `beta_agents/PLAYERS_GUIDE.md`, *Managing*: you take over the team's
  riders, its trainer and its standings, and a short roster is topped up to
  twelve. Keep it in step: the testers know the rules only from here.
- `economy/README.md`, *Balance targets*: one paragraph saying that #156 found
  the drain was claimed rosters, not prices, and that the measurement now
  reports a claimed team.
- `AGENTS.md` `teams/` row: "claiming an unmanaged team (keeping its riders,
  #156)".
- `specs/archive/claiming-a-team.md` is **not** edited (history). The new spec
  records the reversal.

## Verification

1. `.venv/bin/python -m pytest teams transfers world api -q`, then the full
   suite.
2. By hand, run `seed_user`, `seed_teams`, `seed_trainers`, then claim
   through the API (`POST /api/teams/claim/`). Check that the roster screen
   shows the riders the team had before (compare ids from
   `/api/riders/?team=` before and after).
3. `scripts/measure_economy.py`. **The evidence that this works** is that
   the claimed team's last-season net lands inside the AI field's middle half,
   not in its bottom quarter. The likeliest failure is a measurement that
   cannot fail: a claimed team that by accident is still a fresh roster would
   show a strength rank near the bottom. The script prints that rank, so check
   it.

## Risks

| Risk | Mitigation |
|---|---|
| Inherited riders not re-stamped, so the cooldown's free release silently stops | Design decision 3; `test_claim_stamps_inherited_riders_joined_team_at` |
| Locking all unmanaged teams, which serialises claims | Design decision 2 spells out the walk |
| Duplicate baseline snapshots on inherited riders | Snapshots for top-up riders only; a dedicated test |
| Measured season starts with the claimed team unsponsored | The script signs the steady offer right after the season opens |
| A claimant on a two-season staging world gets a mid team that is still weak in absolute terms | Accepted. It is the middle of *that* world, which is what the economy is tuned for |

## Open questions

None.
