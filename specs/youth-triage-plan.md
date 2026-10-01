# Youth triage — Implementation Plan

**Spec:** `specs/youth-triage.md` · **Issue:** #34 · **Status:** proposed
**Apps touched:** `riders/` (new module `youth_triage.py`), `transfers/`, `world/`, `api/`, `frontend/`, `teams/` (one call site), `seasons/` (a second example season)

## Context you need

Read `riders/README.md` sections *Development squad* and *Youth intake* first; this ticket extends both. In short:

- A team's **development squad** is one `riders.DevelopmentSquad` row (`team` one-to-one, `level` 1-3). Prices live in `riders/development_squad.py`'s `LEVELS` table, never on the row. Closing **deletes** the row.
- **Youth intake** (`riders/youth_intake.py`, `run_intake`) gives every open squad `INTAKE_BATCH_SIZE` (2) riders on weeks 4, 8 and 12 of a season. `world.services.tick` calls it inside the per-week loop, after growth, training and charges.
- A squad rider is a `Rider` with **`team = NULL` and `development_squad` set**. Every roster-shaped query filters on `team`, so squad riders draw no wage, get no trainer focus, cannot race and are not in the roster cap — with no exclusion code. `free_agents()` and `sign_free_agent` exclude them explicitly. Two `CheckConstraint`s hold: never both `team` and `development_squad`, and never retired while in a squad.
- `intake_at` is the `week.starts_at` of the intake week a rider arrived in. It is never cleared.
- Growth: `riders.services.apply_weekly_growth(weeks, extra_deltas)` moves every active rider along the age curve (`weekly_deltas`, a fraction of the gap to a per-attribute ceiling derived from hidden `potential`). It also folds in per-rider `extra_deltas`, settling both through `growth_debt`. `world.services._apply_training_week` builds `extra_deltas` (trainer focus plus race effect) and calls it once per crossed week.
- Week counting belongs to `schedule/`: `schedule.services.weeks_opened_between(start, end)` counts `Week` rows starting in `[start, end)`, so the off-season counts nothing. `riders/` and `transfers/` may **not** import `schedule/`. `world/` and `api/` do the counting and pass plain values down.
- Auctions (`transfers/services.py`): `list_for_auction` and `resolve_auction` both check `rider.team_id == seller_team.pk`. `resolve_auction` cancels the auction if the rider has left the seller.
- `ROSTER_CAP` (30) lives in `transfers/services.py`. `riders/` cannot import it.

Dependency rules that bite here (`AGENTS.md`):
- `riders -> core, teams` only.
- `transfers -> riders` only.
- `world` and `api` know everything, so ledger writes and week counting are injected from them.

## Goal

1. Squad riders develop faster than the age curve alone, at a pace that scales with hidden potential. Every one ends the spell visibly better than they arrived, and none passes their ceiling.
2. **Graduation:** 14 in-season weeks after arrival a rider graduates. They stay attached to the squad's team but stop occupying a place.
3. **Squad places:** a squad holds 6, 8 or 10 riders by level. Intake fills free places only, and the rest of the batch is lost.
4. **Manager actions:**
   - Promote a squad rider or graduate (salary starts, roster cap applies).
   - Discard them (the row is deleted).
   - List a graduate on the auction market without a roster place.
5. **Releases to the pool:**
   - A graduate not acted on within 2 in-season weeks is released to the free-agent pool.
   - So is an unsold listed graduate.
   - Closing the squad, or a claim, deletes squad riders and releases graduates.
6. **Squad screen:**
   - Shows places used, a warning when the next intake will be turned away, each rider's weeks left and rating change since arrival.
   - Lists graduates with their decision window and actions.

## Design decisions (settled — implement these, do not substitute)

1. **A graduate is still `development_squad`-linked, distinguished by a new `graduated_at` stamp.** "In the squad" means `development_squad IS NOT NULL AND graduated_at IS NULL`. "Graduate" means `development_squad IS NOT NULL AND graduated_at IS NOT NULL`. Keeping the squad link is what keeps a graduate out of every roster query, the wage bill and `free_agents()` for free. It also gives the owning team (`development_squad.team`) without a second FK.
   - **Do not** add a `graduate_of` FK to `Team`, a status enum, or set `team` on a graduate. A graduate with `team` set would draw a wage, be selectable for races and count towards the cap, which is everything the spec says a graduate does not do.
   - `graduated_at`, like `intake_at`, is **never cleared**: it is history. Membership is always decided by `development_squad` first.

2. **Places are a column of the `LEVELS` table, not of the row.** Add `places` to `LevelTerms` (6/8/10). The existing test that fees and costs rise strictly with level extends to places. Only riders *in the squad* count, never graduates.

3. **Squad development is an extra delta fed into the existing `apply_weekly_growth`.** It is not a second growth pass and not a change to `weekly_deltas`.
   - For each in-squad rider, per attribute: `gap = max(0, ceiling - current)` and `base = weekly_deltas(rider)[a]`. The total wanted is `min(gap, max(base + gap * SQUAD_GROWTH_FRACTION, SQUAD_MIN_WEEKLY_GAIN if gap > 0 else 0))`. The extra delta is `total - base`.
   - **Proportional to the gap:** it tracks hidden potential, which makes "fast developer" the clue the spec wants.
   - **The floor:** it delivers "everyone ends better".
   - **The `min(gap, …)` cap:** it delivers "never past the ceiling".
   - Constants: `SQUAD_GROWTH_FRACTION = 0.03`, `SQUAD_MIN_WEEKLY_GAIN = 0.8` (stored points).
   - **Simulated before writing this plan:** 20,000 Elite-odds youths over 14 weeks, with 0 ending without a displayed gain. Average best attribute moves hopeless 1.3→2.5, journeyman 1.9→3.8, promising 2.4→5.3, gem 3.1→7.0. A starting-roster rider's best attribute sits around 3-5, so gems become genuinely competitive and hopeless riders don't. The age curve alone leaves 17 in 4,000 with no visible gain, which is why the floor exists.
   - Graduates get **no** squad development, only the ordinary age curve. Their spell is over.

4. **Graduation, the window and intake all run in `world/`'s week loop, in this order, after the week's growth, training and charges:**
   1. Graduate riders whose spell is complete.
   2. Release graduates whose window has closed.
   3. Run intake.

   Graduation before intake is **load-bearing**: a rider leaving and a batch arriving at the same boundary must not collide on the last place (spec, *Rules*). Growth before graduation means a rider receives exactly 14 weeks of squad development: arriving at week N's boundary, they develop at N+1 … N+14 and graduate at N+14 after that boundary's growth.

5. **Week counting uses `world/`'s existing cutoff trick, not a COUNT per rider.** "At least `n` in-season weeks opened in `[since, boundary)`" is monotone in `since`. It is therefore `since <= the n-th newest Week.starts_at before boundary`. `_expire_free_agents` already does exactly this inline. Extract it as `_weeks_ago_cutoff(boundary, n) -> datetime | None` and use it for both new steps. Do **not** refactor `_expire_free_agents` onto it in this ticket. That is optional and out of scope, and an untouched expiry path is one less thing to review.

6. **`SPELL_WEEKS = 14` and `GRADUATE_WINDOW_WEEKS = 2` live in `riders/youth_triage.py`.** They are product constants of the squad, like `INTAKE_INTERVAL_WEEKS`. `world/` and `api/` import them and do the counting.

7. **Promotion lives in `riders/` and takes the roster cap as an argument.** `promote(team, rider_id, *, at, roster_cap)`. `api/` passes `transfers.services.ROSTER_CAP`. `riders/` may not import `transfers/`, and the cap is a transfers constant.
   - **Do not** duplicate the 30 into `riders/`.
   - **Do not** move promotion into `transfers/`: it is not a market move, and it would make `transfers/` write squad state.
   - Promotion:
     - sets `team`, clears `development_squad` in the **same `save()`**, because the `rider_not_on_roster_and_in_squad` constraint is checked per statement;
     - sets `weekly_salary = weekly_salary_for(rider)`, the spec's "formula value at the moment of promotion";
     - stamps `joined_team_at` via `mark_team_change`.
   - The roster-cap count runs under the rider's row lock, with the same accepted narrow race `sign_free_agent` documents.

8. **Discard deletes the row and takes an injected `check(rider)` callback.** `api/` passes a check that raises `ProspectListed` if the rider has an OPEN auction. `riders/` cannot see auctions, and deleting a listed rider would cascade the auction and its bid history away. A squad rider or graduate has never raced and cannot have a `RaceResult` or `RaceSquadRider`. Their only dependents are `RiderAttributeSnapshot` rows, which cascade. That is the precondition that makes a plain `delete()` safe. Assert it in a test rather than guarding it in code.

9. **A graduate is "owned" by their squad's team for the market.** Add `riders.youth_triage.belongs_to(rider, team) -> bool`: true if `rider.team_id == team.pk`, or if the rider is a graduate (squad link set, `graduated_at` set) and `rider.development_squad.team_id == team.pk`. An in-squad, not-yet-graduated rider is **not** listable; the spec only lets graduates be sold.
   - `list_for_auction` uses `belongs_to` instead of its `team_id` comparison.
   - `resolve_auction` does too, for its "still the seller's?" check. A graduate promoted mid-auction still belongs to the seller, so the sale proceeds, exactly as for a listed roster rider.
   - On **SOLD** for a graduate: set `team = winner` and `development_squad = None` in one save.
   - On **UNSOLD** for a graduate (no bid, or the buyer's roster is full): release them to the pool with `release_graduates([rider.pk], at=at)` (spec In scope 10). A roster rider's UNSOLD path is unchanged.

10. **The window does not release a listed graduate.** The window step skips any graduate with an OPEN auction, because the auction's outcome decides (sold → buyer, unsold → pool). Without this, a rider listed on the last day would be pulled into the pool mid-auction and the auction cancelled at its deadline, a worse outcome than the spec's.

11. **Closing (and claiming) deletes in-squad riders and releases graduates.** `close_squad` changes from "release everyone" to:
    - stamp graduates through `release_graduates`;
    - then delete in-squad riders;
    - then delete the squad row.

    Release must happen **before** the row is deleted, for #33's reason: `SET_NULL` would unlink graduates with no `unattached_since`, and they would never expire from the pool. Return type changes from `bool` to `SquadClosure | None` (`discarded: int`, `released: list[int]`). `None` means there was no squad. The API's `if not close_squad(...)` keeps working, and `claim_team` ignores the value as before.

12. **Listings of released graduates are cancelled immediately, through one new transfers function.** `transfers.services.cancel_unowned_listings(seller_team, *, at) -> int` cancels every OPEN auction by `seller_team` whose rider no longer `belongs_to` it. `CloseDevelopmentSquadView` and `ClaimTeamView` call it after the close/claim, inside the same transaction.
    - Without it, a released graduate's auction stays biddable until its deadline. That is the same defect #114 describes for roster riders.
    - **This also fixes #114:** on a claim it cancels the old roster's listings too, since those riders no longer belong to the team. That is deliberate; a narrower query would need a special case to *not* fix it. Say so in the PR, and close #114 with it if the reviewer agrees.

13. **`run_intake` creates `min(INTAKE_BATCH_SIZE, free places)` riders.** It does not generate the full batch and drop some. Fewer draws is equivalent for odds and simpler. The existing `(squad, intake_at)` idempotency check stays: a batch turned away entirely writes no riders, so a re-run would try again, but the `WeekTransition` row remains the exactly-once guarantee, as `riders/README.md` says. `run_intake` returns `IntakeResult(created, turned_away)` instead of an int.

14. **The full-squad warning is a projection computed in `api/`.** For the next intake week:
    - `free = places - (in_squad - graduating_by_then)`, where `graduating_by_then` counts in-squad riders with at least `SPELL_WEEKS` weeks opened in `[intake_at, next_intake.starts_at)`;
    - `arrivals_at_risk = max(0, INTAKE_BATCH_SIZE - free)`.

    It is a projection, so a discard changes it. The screen words it as "will be turned away unless you make room".

15. **"Change since arrival" is current displayed value minus the rider's baseline snapshot.** The baseline is `RiderAttributeSnapshot` with `week IS NULL`, written by `run_intake`. One query for the whole squad. Never derived from stored 1-100 values, which would leak finer movement than the display shows (`riders/README.md`, *Display scale*). A rider with no baseline (impossible for intake riders, but defensive) gets `null` changes.

16. **Weeks-left figures are counts, not calendar positions.** `weeks_left = SPELL_WEEKS + 1 - weeks_opened_between(intake_at, now)`, and the same with `GRADUATE_WINDOW_WEEKS` from `graduated_at` for graduates. A count needs no future season declared, while a `{season, week}` would be null across a season boundary when the next season is not yet loaded. Floor at 1.

17. **Three new `TickRun` counters:** `youth_graduated`, `youth_graduates_released`, `youth_intake_turned_away`. Same shape as `youth_intake_riders`. They are how verification sees the mechanics fire.

18. **No change to who intake serves.** Unmanaged teams' squads also graduate and release. They never list, so their graduates go to the pool when the window closes. That is acceptable, since #45 owns AI squad behaviour.

## Data model

`riders.Rider`, new field:

| Field | Type | null/blank | Default | Notes |
|---|---|---|---|---|
| `graduated_at` | `DateTimeField` | `null=True, blank=True` | `None` | Game time (a `week.starts_at`) the rider completed the spell. Never cleared. Meaningful only alongside `development_squad` — see Design decision 1. |

New `CheckConstraint` on `Rider`: `graduated_requires_intake` — `Q(graduated_at__isnull=True) | Q(intake_at__isnull=False)`. Only an intake rider can graduate.

Migration `riders/migrations/0015_rider_graduated_at.py`: add the field and the constraint. No data migration; existing squad riders start with `graduated_at = NULL` and their 14 weeks count from their own `intake_at`, so some may graduate on the first tick after deploy. That is correct.

`world.TickRun`, three new `PositiveIntegerField(default=0)` fields as in Design decision 17. Migration `world/migrations/0020_tickrun_youth_triage.py`.

`riders/development_squad.py` `LevelTerms` gains `places: int`. `LEVELS`: Regional 6, National 8, Elite 10. Not a model change.

## `riders/youth_triage.py` (new)

```python
SPELL_WEEKS = 14
GRADUATE_WINDOW_WEEKS = 2
SQUAD_GROWTH_FRACTION = 0.03
SQUAD_MIN_WEEKLY_GAIN = 0.8

class TriageError(Exception): ...
class NotYourProspect(TriageError): ...      # not in this team's squad, nor its graduate
class RosterFull(TriageError): ...
class ProspectListed(TriageError): ...       # raised by api's injected check

@dataclass(frozen=True)
class IntakeResult: created: int; turned_away: int   # (lives in youth_intake.py, see below)

def in_squad(squad) -> QuerySet[Rider]          # development_squad=squad, graduated_at null
def graduates(squad) -> QuerySet[Rider]         # development_squad=squad, graduated_at not null
def free_places(squad) -> int                   # LEVELS[squad.level].places - in_squad(squad).count(), floored 0
def belongs_to(rider, team) -> bool             # Design decision 9
def squad_development_deltas(rider) -> dict[str, float]   # Design decision 3; one week
def graduate(rider_ids, *, at) -> int
def release_graduates(rider_ids, *, at) -> list[int]
def promote(team, rider_id, *, at, roster_cap: int) -> Rider
def discard(team, rider_id, *, check=None) -> None
```

- `graduate`: one `UPDATE … WHERE pk IN ids AND development_squad IS NOT NULL AND graduated_at IS NULL SET graduated_at = at`. The re-check in the WHERE makes it safe against a concurrent promote/discard, as `retire_riders` is.
- `release_graduates`: select graduates among `rider_ids` (`graduated_at` not null, squad link set) **under `select_for_update()`**. Then `mark_team_change(riders, team_now=None, at=at)` to stamp `unattached_since`, then `.update(development_squad=None)`. Returns the ids actually released. Callers: the window step, `resolve_auction`'s UNSOLD path and `close_squad`.
- `promote`: real code, because the lock and the one-save are the parts people get wrong:

```python
def promote(team, rider_id, *, at, roster_cap):
    with transaction.atomic():
        rider = (Rider.objects.select_for_update()
                 .select_related("development_squad").filter(pk=rider_id).first())
        if rider is None or rider.development_squad is None \
                or rider.development_squad.team_id != team.pk:
            raise NotYourProspect("That rider is not in your development squad.")
        if Rider.objects.filter(team=team).count() >= roster_cap:
            raise RosterFull(f"Your team already has {roster_cap} riders.")
        rider.team = team
        rider.development_squad = None          # same save: the check constraint
        rider.weekly_salary = weekly_salary_for(rider)
        mark_team_change([rider], team_now=team, at=at)   # stamps joined_team_at
        rider.save(update_fields=["team", "development_squad", "weekly_salary", "updated_at"])
    return rider
```

  `mark_team_change` bulk-updates `joined_team_at` and `unattached_since` itself, so they are not in `update_fields` here. Same split `sign_free_agent` uses.

- `discard`: lock the rider as `promote` does, apply the same ownership check (in squad **or** graduate), call `check(rider)` if given, then `rider.delete()`.

## `riders/development_squad.py`

- `LevelTerms.places`, and `LEVELS` gains the three values.
- `close_squad(team, *, at) -> SquadClosure | None`:
  1. under the existing team lock, `released = release_graduates(graduates(squad) ids, at=at)`;
  2. then `discarded = in_squad(squad).delete()` (count riders only, not the cascaded total — read `delete()[1]["riders.Rider"]`);
  3. then `squad.delete()`.

  Update the module and function docstrings: closing no longer releases squad riders.

## `riders/youth_intake.py`

- `run_intake` computes `free = free_places(squad)` under the existing team lock, after the idempotency check, and creates `min(INTAKE_BATCH_SIZE, free)` riders.
- It accumulates `turned_away += INTAKE_BATCH_SIZE - created_for_squad` and returns `IntakeResult(created, turned_away)`.
- Put `IntakeResult` here; `youth_triage` does not need it.

## `riders/services.py`

No changes. `apply_weekly_growth`, `weekly_deltas` and `attribute_ceilings` are used as they are. `retire_due_riders` already clears `development_squad`.

## `transfers/services.py`

- Import `belongs_to` and `release_graduates` from `riders.youth_triage`. This is allowed: `transfers -> riders`.
- `list_for_auction`: replace `rider.team_id != team.pk` with `not belongs_to(rider, team)` (fetch with `select_related("development_squad")`).
- `resolve_auction`:
  - The ownership check uses `belongs_to(rider, auction.seller_team)`.
  - **UNSOLD (both paths):** if the rider is a graduate (`rider.team_id is None and rider.development_squad_id is not None`), call `release_graduates([rider.pk], at=at)` before saving the auction.
  - **SOLD:** set `rider.development_squad = None` alongside `rider.team = winner` and add it to `update_fields`. Harmless for a roster rider.
- New `cancel_unowned_listings(seller_team, *, at) -> int` (Design decision 12): iterate OPEN auctions of `seller_team` with `select_related("rider__development_squad")`, collect those whose rider no longer `belongs_to(seller_team)`, then `cancel_open_auctions(ids, at=at)` (existing).

## `teams/services.py`

`claim_team` keeps calling `close_squad(team, at=at)` and ignoring the result. Update only the comment above it: squad riders are discarded and graduates released.

## `world/services.py` and `world/models.py`

- New `_weeks_ago_cutoff(boundary, n) -> datetime | None` (Design decision 5).
- New `_graduate_squad_riders(week) -> int`:
  - compute the cutoff for `SPELL_WEEKS`; if there is none, return 0;
  - collect ids of riders with `development_squad` set, `graduated_at` null, `intake_at <= cutoff`;
  - call `graduate(ids, at=week.starts_at)`.
- New `_release_expired_graduates(week) -> int`:
  - cutoff for `GRADUATE_WINDOW_WEEKS`;
  - graduates with `graduated_at <= cutoff`, **excluding** any with an OPEN `Auction` (`~Exists(...)`);
  - `release_graduates(ids, at=week.starts_at)`;
  - also cancel nothing — they have no open auction by construction.
- `_apply_training_week`: after the trainer and race loops, for every `Rider.objects.active().filter(development_squad__isnull=False, graduated_at__isnull=True)`, **add** `squad_development_deltas(rider)` into `extra[rider.pk]` (merge per attribute, don't overwrite, even though a squad rider can have no other extra today).
- `tick()`: in the week loop, replace the intake block with:

```python
youth_graduated += _graduate_squad_riders(week)
youth_graduates_released += _release_expired_graduates(week)
if is_intake_week(week.number):
    result = run_intake(at=week.starts_at)
    youth_intake_riders += result.created
    youth_intake_turned_away += result.turned_away
```

  Keep the existing comment about why intake comes after growth, and add one line on why graduation precedes intake (Design decision 4).
- `TickRun.objects.create(...)` passes the three new counters.

## `api/`

- `views.py`, `DevelopmentSquadView.get`:
  - Each level gains `places`.
  - The top level gains `places` (current level's, or `null` when closed), `in_squad` (count), `roster_count` and `roster_cap`. The last two let the Promote button disable without a 409.
  - `riders` becomes the **in-squad** riders only, each with `weeks_left` and `change`.
  - New `graduates` list, each with `weeks_left` (the window), `change`, `market_value` (`transfers.pricing.market_value_for`), `promotion_salary` (`riders.pricing.weekly_salary_for`) and `listed` (OPEN auction exists).
  - In-squad riders also carry `promotion_salary`.
  - `intake.next` gains `arrivals_at_risk` (Design decision 14). Compute the next intake *week row*, not just its `{season, week}`: change `_next_intake` to return the `Week` (or `None`) and build the payload from it.
- New views:
  - `PromoteSquadRiderView`: POST `development-squad/riders/<int:rider_id>/promote/`. Calls `promote(team, rider_id, at=now(), roster_cap=ROSTER_CAP)`. 409 on `NotYourProspect` / `RosterFull`, 204 otherwise.
  - `DiscardSquadRiderView`: POST `development-squad/riders/<int:rider_id>/discard/`. Calls `discard(team, rider_id, check=_not_listed)`. `_not_listed` raises `ProspectListed("Your listing for this rider is still open.")` if an OPEN auction exists. 409 on any `TriageError`.
  - POST, not DELETE, for `CloseDevelopmentSquadView`'s reason.
- `CloseDevelopmentSquadView`: wrap `close_squad` and `cancel_unowned_listings(team, at=at)` in one `transaction.atomic()`, using the same `at`.
- `ClaimTeamView`: add `cancel_unowned_listings(team, at=at)` after `withdraw_bids` inside the existing atomic block.
- `ListForAuctionView` needs no change. The service now accepts graduates.
- `serializers.py`:
  - `DevelopmentSquadRiderSerializer` gains `weeks_left`, `change` (a dict of the five attribute keys to ints, or null) and `promotion_salary`.
  - New `DevelopmentSquadGraduateSerializer` extends it with `market_value` and `listed`.
  - Values come from serializer `context` maps built once in the view: `{rider_id: weeks_left}`, `{rider_id: baseline}`, `{rider_id: listed}`. Do not query per rider.
  - `DevelopmentSquadLevelSerializer` gains `places`, and `DevelopmentSquadIntakeSerializer`'s `next` gains `arrivals_at_risk`. Use a dedicated small serializer; do not keep reusing `RetiredSerializer` once the shape has a third field.
- `urls.py`: the two routes, named `promote-squad-rider` and `discard-squad-rider`.

## `frontend/`

- `api.ts`:
  - Extend `DevelopmentSquadLevel` (`places`), `DevelopmentSquadRider` (`weeks_left`, `change`, `promotion_salary`) and `DevelopmentSquadIntake.next` (`arrivals_at_risk`).
  - Add `DevelopmentSquadGraduate`.
  - Extend `DevelopmentSquad` with `places`, `in_squad`, `roster_count`, `roster_cap` and `graduates`.
  - Add `promoteSquadRider(id)` and `discardSquadRider(id)` through `writeJson`.
  - Reuse the existing list-for-auction call for "List for sale".
- `useDevelopmentSquad.ts`: expose `promote`, `discard` and `list`, each refreshing afterwards like the existing open/upgrade/close.
- `screens/DevelopmentSquad.tsx`:
  - Level cards show a `Places` `Figure`.
  - The "Squad riders" card header shows `in_squad / places`.
  - A warning line when `intake.next.arrivals_at_risk > 0`: "Squad full — N arrival(s) in Season S, Week W will be turned away unless you make room."
  - Each rider row shows, next to each attribute bar, the change since arrival as a signed number (`+2`). `0` is shown muted; `null` shows nothing.
  - Each rider row also shows "Graduates in N weeks" and buttons **Promote** (disabled at `roster_count >= roster_cap`, with the reason) and **Discard**.
  - **Discard asks for confirmation**, naming the rider and saying it is permanent.
  - A new **Graduates** card lists graduates with "Decide within N weeks", the promotion salary and market value (both `formatMoney`, with `$`), and buttons **Promote**, **List for sale** and **Discard**.
  - A listed graduate shows "Listed on the transfer market" instead of List and Discard.
  - The card is hidden when there are no graduates.
  - No numbers about odds, no potential, ever.
- `screens/DevelopmentSquad.test.tsx`: cases listed under W8.

## `seasons/season-2.example.json` (new)

A copy of season 1 with `"number": 2` and `"starts_at": "2027-05-24T00:00:00Z"`, exactly 12 weeks after season 1 opens, so they abut. Race names can stay. It exists because graduation (week 18 for a week-4 arrival) cannot be seen with only one 12-week season declared. Add it to the seeding block in `AGENTS.md`.

## Work items

### W1 — `riders/`: `graduated_at`, constraint, `places` in `LEVELS`, migration
Add the field, `graduated_requires_intake`, `LevelTerms.places` and the values.
Tests:
- `riders/tests/test_models.py::test_graduated_requires_intake` (IntegrityError for `graduated_at` without `intake_at`).
- `riders/tests/test_development_squad.py::test_levels_rise_strictly_in_both_columns` extended to `places` (rename to `..._in_every_column`).

### W2 — `riders/youth_triage.py`: queries, ownership, graduate/release, promote, discard
Everything in that section except `squad_development_deltas`. Tests in new `riders/tests/test_youth_triage.py`:
- `in_squad` / `graduates` / `free_places` partition a squad correctly.
- `belongs_to`:
  - true for a roster rider and for a graduate of the team;
  - false for an in-squad rider and for another team's graduate.
- `graduate` stamps only un-graduated squad riders, and is a no-op for a promoted one.
- `release_graduates` stamps `unattached_since`, clears the squad and ignores non-graduates.
- `promote`:
  - sets team, clears squad and sets `weekly_salary == weekly_salary_for(rider)`;
  - stamps `joined_team_at`;
  - refuses at `roster_cap`;
  - refuses another team's rider.
- `discard`:
  - deletes the rider and their snapshots;
  - runs `check` and is rolled back when it raises;
  - refuses another team's rider.
- `test_squad_riders_have_no_race_history_dependents` — the precondition from Design decision 8. Build a squad rider and assert that no FK other than snapshots can point at them in a normal flow; this is a guard against a future squad-racing feature making delete unsafe.

### W3 — `riders/`: squad development deltas
`squad_development_deltas` per Design decision 3. Tests:
- `test_squad_development_never_passes_ceiling` (rider at ceiling gets 0).
- `test_squad_development_tracks_potential` (same attributes, higher potential, larger delta).
- **`test_every_youth_gains_over_a_spell`** — seeded `random.Random`, 2,000 riders per level from `generate_youth_rider`. Apply 14 weeks of `weekly_deltas + squad_development_deltas` through `_settle` in memory (no DB) and assert every rider's summed display value rose. This is the load-bearing test of the spec's "everyone improves" promise. If it fails after a tuning change, the tuning is wrong, not the test.

### W4 — `riders/`: intake respects places; `close_squad` discards and releases
- `run_intake` returns `IntakeResult` and creates `min(batch, free)`.
- `close_squad` behaves as in Design decision 11 and returns `SquadClosure | None`.
- Update `teams/services.py`'s comment.
- Tests in `test_youth_intake.py`:
  - full squad → 0 created, 2 turned away;
  - one place → 1 and 1;
  - graduates do not count.
- Tests in `test_development_squad.py`:
  - close deletes in-squad riders and releases graduates with `unattached_since`;
  - returns `None` when closed.
- Update existing tests that asserted every squad rider becomes a free agent on close. They encode #33's rule, which this ticket deliberately reverses.

### W5 — `transfers/`: graduates on the market
- `belongs_to` in `list_for_auction` and `resolve_auction`.
- The UNSOLD release and the SOLD squad-clear.
- `cancel_unowned_listings`.

Tests in `transfers/tests/test_services.py`:
- list a graduate (ok);
- list an in-squad rider (refused);
- resolve sold → buyer roster, squad cleared;
- unsold → free agent with `unattached_since`;
- buyer roster full → unsold → free agent;
- promoted mid-auction → sale proceeds;
- `cancel_unowned_listings` cancels a released graduate's listing and a released roster rider's, and leaves an owned one open.

### W6 — `world/`: development, graduation, window, counters
- The helpers, the loop order, the `_apply_training_week` merge, the `TickRun` fields and the migration.

Tests in new `world/tests/test_youth_triage.py`, driving `tick()` across weeks with the existing tick fixtures:
- A week-4 arrival is in the squad at week 17 and a graduate at week 18 (two seasons declared).
- Graduation at the same boundary as an intake frees the place for it.
- A graduate is released to the pool two weeks after graduating.
- A listed graduate is **not** released by the window, and an unsold one is released at resolution.
- A squad rider's attributes grow faster than an identical rider's with no squad.
- The new `TickRun` counters match.

### W7 — `api/`: squad payload, promote/discard, cancel on close/claim
Views, serializers and urls as in that section. Tests in `api/tests.py`:
- the GET shape (places, `in_squad`, `weeks_left`, `change` from baseline, graduates with `listed`/`market_value`/`promotion_salary`, `arrivals_at_risk` for a full squad);
- promote 204 and 409 (roster full / not yours);
- discard 204, and 409 when listed;
- close cancels a listed graduate's auction;
- claim cancels the old roster's open listings.

### W8 — `frontend/`: squad screen triage
Types, hook and screen as in that section. `DevelopmentSquad.test.tsx` cases:
- places shown on cards and header;
- warning shown only when `arrivals_at_risk > 0`;
- change rendered signed;
- Promote disabled at the roster cap;
- Discard confirms before calling the API;
- Graduates card hidden when empty;
- a listed graduate shows no List/Discard;
- no text contains a percentage.

Run `npm test` and `npm run build` in `frontend/`.

### W9 — `seasons/season-2.example.json` and the seed note
The file, plus the `AGENTS.md` seeding block line (`load_season seasons/season-2.example.json`). Test: `schedule/tests/test_load_season.py::test_season_2_example_loads_after_season_1` — load both files and assert season 2 starts at season 1's `ends_at` (they abut, no overlap error).

### W10 — Documentation, archive spec and plan
See below.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9 → W10, one commit each.

- W1-W4 are all `riders/` and leave the tick untouched, so the suite stays green with no caller changes. One exception: `run_intake`'s new return type breaks `world/services.py`'s `+=`. **Update the call site to `.created` in W4 itself**, not W6, so W4 is green on its own.
- W5 before W6 because the window step's "skip listed graduates" and the UNSOLD release need to be one coherent rule before the tick exercises it.
- W7 after W6 because the API's weeks-left and at-risk figures mirror the tick's counting, and they should be written against code that already does it.
- Stop and run the full suite (`.venv/bin/python -m pytest`) after W4, W6 and W7.

## Documentation update (required, not optional)

- `riders/README.md`:
  - *Development squad*: places per level; closing now deletes squad riders and releases graduates.
  - *Youth intake*: intake fills free places only; the "closing releases riders" paragraph now names graduates only.
  - New section *Youth triage*: in squad vs graduate (Design decision 1), squad development and its tuning with the simulated figures, the spell and window, promote/discard and their injected `roster_cap` / `check`, `belongs_to`.
- `transfers/README.md`, *Auctions*: graduates are listable without a roster place; `belongs_to` replaces the team comparison; the UNSOLD-graduate release; `cancel_unowned_listings` and its claim call (and #114).
- `world/README.md`, *How a tick works*: graduation and the window in the week loop, their order relative to intake, the three counters.
- `api/README.md`: the squad payload's new keys and the two endpoints.
- `frontend/README.md`: the squad screen's triage actions.
- `AGENTS.md`:
  - `riders/` row: graduates, places, promote/discard, closing deletes squad riders;
  - `transfers/` row: graduates on the market;
  - seeding block: season 2.
- Set `Status: implemented` on the spec and this plan and move both to `specs/archive/`.

## Verification

Unit tests prove the parts. End to end, in this worktree:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python scripts/dev_db.py
/home/mario/dev/cycling-manager/.venv/bin/python manage.py migrate
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_user
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_teams --claim-for test@mail.com
/home/mario/dev/cycling-manager/.venv/bin/python manage.py load_season seasons/season-1.example.json
/home/mario/dev/cycling-manager/.venv/bin/python manage.py load_season seasons/season-2.example.json
```

Then, with `GAME_CLOCK_CLASS=world.clocks.MockClock`:
1. Set the clock to season 1 week 1, log in and open a Regional squad.
2. Step the clock week by week with `tick`. At week 4, two riders arrive; the screen shows `2 / 6` and change `0` everywhere.
3. By week 12 the squad is full at 6. The screen must show the "turned away" warning for season 2 week 4, and that tick's `TickRun.youth_intake_turned_away` must be 2.
4. Season 2 week 6 (the 18th week): the two week-4 riders appear under **Graduates** with "Decide within 2 weeks". Every one of them shows a positive change.
5. List one graduate, promote one (wage appears in next week's ledger entry) and let a third's window lapse. It shows in the free-agent pool.
6. Close the squad: in-squad riders disappear entirely (their profile URL 404s), and any graduate is in the pool.

**The likeliest failure is a graduate silently becoming a free agent with no `unattached_since`**, via a path that clears `development_squad` without `release_graduates`. That would leave them in the pool forever. Check after step 6:

```sql
select count(*) from riders_rider
where team_id is null and development_squad_id is null
  and retired_at is null and unattached_since is null and intake_at is not null;
```

It must be 0. The second likeliest is graduation running after intake: step 3's counter and the season-2 week-4 batch arriving into a squad with free places would show it.

## Risks

| Risk | Mitigation |
|---|---|
| Promotion sets `team` without clearing `development_squad` in the same save → IntegrityError. | Real code given above; W2 test covers it. The constraint makes the mistake loud rather than silent. |
| A new path clears `development_squad` without stamping `unattached_since` (expiry would never see the rider). | All releases go through `release_graduates`; the Verification SQL check. |
| Discarding deletes race history if a future ticket lets squad riders race. | W2's precondition test fails the moment that changes. |
| `close_squad` now deletes riders, which #33's tests asserted the opposite of. | Expected; W4 updates those tests, and the reversal is the spec's *Decisions taken*. |
| The window releases a rider mid-auction. | Design decision 10; W6 test. |
| Squad development tuned too strong, so every Elite squad mints stars. | Simulated figures are in Design decision 3; the constants are in one module; the gem band is 8% of Elite arrivals. |
| `cancel_unowned_listings` on claim changes #114's ticket out from under it. | Deliberate (Design decision 12); called out in the PR so #114 is closed or re-scoped knowingly. |
| `run_intake`'s return type change breaks the tick between commits. | Updated in W4 (Execution order). |

## Open questions

None blocking. Two calls you may want to overrule:
- Design decision 12 incidentally fixes #114.
- The squad-development constants (`0.03` / `0.8`) are a first tuning, backed by the simulation above.
