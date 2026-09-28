# Rider retirement and roster churn — Implementation Plan

**Spec:** `specs/archive/rider-retirement.md` · **Issue:** #42 · **Status:** implemented
**Apps touched:** `riders/`, `transfers/`, `world/`, `api/`, `frontend/`

## Context you need

**The retired state already exists.** #104 (PR #112) added `Rider.retired_at`,
a nullable game-time stamp. `NULL` means active; once set it is never cleared.
`Rider.objects.active()` (`riders/models.py`, `RiderQuerySet`) is the single
definition of "still in the game", and the four all-rider passes
(`apply_weekly_growth`, `apply_weekly_recovery`, `advance_ages`, `reprice_all`)
already use it. A retired rider is therefore frozen for free. A DB check
constraint `retired_rider_has_no_team` requires `retired_at IS NULL OR
team_id IS NULL`. The profile API already reports `retired: {season, week}`
(`api/rider_profile.py`, `retired_payload`), and the profile screen already
renders "Retired · Season N, Week W" (`frontend/src/screens/RiderProfile.tsx`,
`retiredLabel`). Read `riders/README.md`, *Retirement*.

**What is missing** is the age-driven trigger, the season-long warning and
cleaning up a retiring rider's open auction.

**The season close lives in `world.services.tick()`** (`world/services.py`,
the `for transition in closed:` loop). Today it calls `advance_ages()` and then
`reprice_all()` + `write_salary_reviews()`. This feature adds a step at the top
of that loop body.

**Relevant hidden traits.** `peak_age` is generated 24–32
(`riders/generation.py`, `_PEAK_AGE_RANGE`; validator 22–34). `decline_rate` is
1–100. Both are set once at generation and **never mutated anywhere afterwards**
(verified by grep). A value derived purely from them is therefore stable for a
rider's whole life. `age` is 18–40 (validator), generated 18–36, and advanced
once per season close.

**Leaving a team mid-plan is already safe for racing.** `racing/services.py`
drops a squad member whose rider has left the team (see the comment near line
330), whatever the reason. Retirement nulls the team exactly like a release, so
racing needs no change.

**Auctions** (#28, `transfers/`). `resolve_auction` already **cancels** an
auction whose rider has left the seller's roster, with no money moved. Bids are
never escrowed, so cancelling needs no refunds. However, `place_bid` does not
look at the rider, so an auction left `OPEN` after its rider retires stays
biddable until its deadline. That is why W3 exists.

**Repo rules that bind this work** (`AGENTS.md`):
- `riders/` may not import `schedule/`, `world/`, `transfers/` or `racing/`.
- `transfers/` may import only `riders/`.
- `world/` and `api/` may import everything.
- Hidden traits are never serialized. The new boolean is a *consequence*
  of them, which is allowed (`riders/README.md`, *Visible vs hidden*: every
  hidden trait must be inferable). The derived retirement age itself is
  never serialized.

## Goal

1. Every active rider has a hidden retirement age from 33 to 38, derived from
   `peak_age` and `decline_rate`, with no new stored trait.
2. While a season is in progress, every active rider whose age has reached
   their retirement age is flagged `final_season: true` in every API payload
   built on `RiderSerializer`. The roster, rider profile and free-agent
   screens show a "Last season" tag for them.
3. At each season close, before ageing, every active rider whose age has
   reached their retirement age is retired in a single update: team cleared,
   `retired_at` stamped. Any open auction of theirs is cancelled.
4. `TickRun` records how many riders retired by age.

## Design decisions (settled — implement these, do not substitute)

**D1. The retirement age is derived, not stored.** It is computed as
`retirement_age(rider)`, a pure function of `peak_age` and `decline_rate`, with
no new model field and no migration on `Rider`.
*Why:* the spec's decision that retirement is "not a wholly new hidden trait".
Both inputs are immutable, so the result is stable for life, and there is no
backfill for existing riders.
*Do not* add a `retirement_age` column or a stored "announced" flag (see D3).

**D2. The formula.** It lands on 33–38 inclusive with no clamping at the
extremes:

```python
RETIREMENT_AGE_MIN = 33
RETIREMENT_AGE_SPAN = 5   # MIN + SPAN = 38, the latest anyone retires

def retirement_age(rider) -> int:
    low, high = PEAK_AGE_RANGE                      # (24, 32), from generation.py
    peak_share = min(1.0, max(0.0, (rider.peak_age - low) / (high - low)))
    staying_power = (100 - rider.decline_rate) / 99  # decline 1 -> 1.0, 100 -> 0.0
    return RETIREMENT_AGE_MIN + round(3 * peak_share + 2 * staying_power)
```

*Why:*
- Late peakers retire later, and fast decliners retire sooner. Earlier in the
  spec discussion this was the stated behaviour: "riders deeper into decline go
  sooner".
- The 3 + 2 weighting makes peak age the bigger driver, so a player watching
  many careers can learn "late bloomers last". This is the inferability rule
  in action.
- With uniform generation, the mean is about 35.5.
- The `min/max` guard exists because the validator allows `peak_age` 22–34,
  outside the generation range.

*Load-bearing:* `PEAK_AGE_RANGE` must be the **same constant** generation
uses. Rename `_PEAK_AGE_RANGE` to public `PEAK_AGE_RANGE` in
`riders/generation.py` and import it. *Do not* copy the tuple, because the two
would drift.

**D3. "Final season" is derived at read time.** It is
`in_season and rider.retired_at is None and rider.age >= retirement_age(rider)`.
*Why:*
- The spec says the marker appears when the season opens and lasts until
  it closes. Between seasons (a gap between declared seasons) nobody is
  marked. At that point, anyone marked last season has just retired, and
  those who crossed into the window by ageing wait for the next opening.
- A freshly generated rider already inside the window is marked immediately if
  a season is running. The spec accepts this explicitly ("a brand-new roster …
  can include riders already carrying the marker").
- *Do not* store a flag written at season open. It would drift from `age`
  whenever a rider is generated mid-season, and it needs a migration, a
  season-open step and a backfill, all for a value that is a pure function.

**D4. Retire before ageing, inside the same closed-season iteration.** The
order at a season close becomes: `retire_due_riders` → `advance_ages` →
`reprice_all` → `write_salary_reviews`.
*Load-bearing:* the reverse order would age a rider from R−1 to R and retire
them in the same breath, **without the season of warning** the spec
guarantees.
Retiring first also keeps retirees out of the salary review for free
(`reprice_all` iterates `active()`), and freezes their age at the one the
player last saw.

**D5. Retirement is one conditional UPDATE that clears the team and stamps
`retired_at` together:**
`Rider.objects.filter(pk__in=due, retired_at__isnull=True).update(team=None, retired_at=at)`.
*Why:* the check constraint is evaluated per row after the UPDATE, so setting
both columns in one statement satisfies it.
*Do not* reuse `retire_riders()`. It deliberately filters `team__isnull=True`
(it serves free-agent expiry) and would silently skip every rostered rider.
*Do not* call `mark_team_change` first either: `unattached_since` means "sat
in the free-agent pool since", and a retired rider never sits in the pool.
Leave `unattached_since` and `joined_team_at` untouched.

**D6. The stamp is the closing season's final week's `starts_at`, not
`season.ends_at`.**
*Why:* `retired_payload` resolves the stamp through `current_position()`, whose
ranges are half-open (`starts_at <= at < ends_at`).
- `ends_at` falls *outside* the closing season. With back-to-back seasons it
  would resolve to "Season N+1, Week 1"; with a gap, to "Season N" with no week.
- The final week's `starts_at` resolves to "Season N, Week 12" in both
  layouts, with no change to `api/`.

This also matches #104's convention of stamping a week's `starts_at`. Nothing
compares `retired_at` against race times.

**D7. Cancel the retiring riders' open auctions in the same transaction as the
retirement.** Add `transfers.services.cancel_open_auctions(rider_ids, *, at)
-> int`. It is one UPDATE, `status=CANCELLED`, `resolved_at=at`, on `OPEN`
rows only. `world/` calls it right after `retire_due_riders`, inside one
`transaction.atomic()`.
*Why:*
- Leaving the auction open lets managers keep bidding on a retired rider
  for up to three days.
- `resolve_auction` would cancel it eventually anyway, so this only brings
  the cancellation forward.
- No money moves because bids are never escrowed.

*Do not* put this in `riders/`, which may not import `transfers/`.

**D8. The in-season check lives in `api/` and is computed once per response.**
`RiderSerializer.get_final_season` reads a cached `in_season` flag from the
serializer context. On first use it computes `current_position(now()).state
== "in_season"` and stores it back into `self.context`. DRF nested and `many`
serializers share the root's context dict, so a 30-rider roster costs one
query, not 30.
*Why:* `riders/` may not import `schedule/`, and serializer context is the
existing way this file threads request-wide values (`release_cost` does the
same).
*Do not* make the four views pass `in_season` by hand. The lazy cache is
correct even when a future view forgets.

**D9. The field goes on `RiderSerializer`, so it reaches all four payloads
built on it:** roster, free agents, rider profile and the auction market.
The **UI** tag is added only on the spec's three screens: roster, rider
profile and free-agent listing. The auction card is not in the spec's
*In scope* #3. The field arrives there unused, and adding the tag to
`AuctionCard` is a one-line follow-up if wanted. *Do not* add it here.

**D10. Riders signed, sold or released while marked still retire.** No code is
needed, because D3 derives the marker from age and traits, which a team change
does not touch. The concurrent case, where a rider is signed or auction-sold
in the same instant the close runs, is handled by the row lock: whichever
statement commits second wins. If the retirement lands second, the buyer has
paid for a rider who retires at once. That is accepted, because the rider was
visibly marked all season (spec: "the marker travels with the rider").

**D11. No replacement riders, no notification, no market-value change.** These
are the spec's *Out of scope* items. Rosters shrink. A team below four riders
is already skipped from races with a warning (`racing/README.md`), and that
stays as is.

## Data model

**No change to `Rider`.** Everything reads existing fields.

`world.TickRun` gains one counter:

| Field | Type | Null | Default | Help text |
|---|---|---|---|---|
| `riders_retired` | `PositiveIntegerField` | no | `0` | "Riders retired by age at a season close this tick (#42). Distinct from `agents_retired` (free-agent expiry)." |

Migration: `world/migrations/0016_tickrun_riders_retired.py` (generated by
`makemigrations world`).

## riders/generation.py

- Rename `_PEAK_AGE_RANGE` to `PEAK_AGE_RANGE` and update its one use in
  `generate_rider`. No behaviour change.

## riders/services.py

Add, near `advance_ages`:

```python
RETIREMENT_AGE_MIN = 33
RETIREMENT_AGE_SPAN = 5

def retirement_age(rider: Rider) -> int: ...          # D2, exactly as written
def is_due_to_retire(rider: Rider) -> bool: ...       # active and age >= retirement_age
def retire_due_riders(*, at) -> list[int]: ...        # D5; returns retired ids
```

`retire_due_riders` in full, because the single-UPDATE shape is the point:

```python
def retire_due_riders(*, at) -> list[int]:
    """Retire every active rider whose age has reached their retirement
    age, as of `at` (game time). Clears the team and stamps retired_at in
    one UPDATE so retired_rider_has_no_team holds row by row. Returns the
    ids actually retired. Pure with respect to seasons: world decides when."""
    due = [
        rider.pk
        for rider in Rider.objects.active().only("id", "age", "peak_age", "decline_rate")
        if rider.age >= retirement_age(rider)
    ]
    if due:
        Rider.objects.filter(pk__in=due, retired_at__isnull=True).update(
            team=None, retired_at=at,
        )
    return due
```

The select and the UPDATE run inside the caller's `transaction.atomic()` (see
`world/`). The season close is exactly-once (`SeasonTransition`'s unique
constraint), so no second close can race this one.

Update the `advance_ages` docstring. Its line "automatic age-driven retirement
(#42) is still future work" becomes a pointer to `retire_due_riders`, which
runs first. Leave the `age__lt=40` cap: retirement at 38 at the latest means
it only ever affects riders generated old and never used, and it is harmless.

## transfers/services.py

```python
def cancel_open_auctions(rider_ids: Iterable[int], *, at) -> int:
    """Cancel every OPEN auction of these riders — no money moves (bids are
    never escrowed). Returns auctions cancelled."""
    return Auction.objects.filter(
        rider_id__in=list(rider_ids), status=Auction.Status.OPEN,
    ).update(status=Auction.Status.CANCELLED, resolved_at=at)
```

`QuerySet.update()` does not bump `auto_now` `updated_at`. That is acceptable
and matches `retire_riders`, since nothing reads `Auction.updated_at` for
logic. *Do not* loop and `.save()` per auction.

## world/services.py

In `tick()`, add a counter `riders_retired = 0` next to `riders_aged`, and at
the top of `for transition in closed:`:

```python
for transition in closed:
    final_week = transition.season.weeks.order_by("-starts_at").first()   # D6
    with transaction.atomic():
        retired_ids = retire_due_riders(at=final_week.starts_at)
        cancel_open_auctions(retired_ids, at=at)
    riders_retired += len(retired_ids)
    riders_aged = advance_ages()          # unchanged; must stay AFTER (D4)
    ...
```

- Imports: `retire_due_riders` from `riders.services` and
  `cancel_open_auctions` from `transfers.services`. `transaction` is already
  imported (`from django.db import IntegrityError, transaction`).
- Pass `riders_retired=riders_retired` into the `TickRun.objects.create(...)`
  call alongside `riders_aged`.
- `cancel_open_auctions` gets `at` (the tick's `now()`) as `resolved_at`. That
  matches how `resolve_auction` stamps `resolved_at` with the tick time, not a
  week boundary.

A season always has twelve weeks (`schedule/`'s loader creates them), so
`final_week` is never `None`. Do not add a fallback.

## world/models.py

Add `riders_retired` (see *Data model*) after `riders_aged`.

## api/serializers.py

On `RiderSerializer`:

```python
final_season = serializers.SerializerMethodField()

def get_final_season(self, instance) -> bool:
    return _in_season(self.context) and is_due_to_retire(instance)
```

and a module-level helper:

```python
def _in_season(context: dict) -> bool:
    """Whether a season is running now, computed once per response and
    cached on the shared serializer context (D8)."""
    if "in_season" not in context:
        context["in_season"] = current_position(now()).state == "in_season"
    return context["in_season"]
```

Import `is_due_to_retire` from `riders.services`, `current_position` from
`schedule.services` and `now` from `world.services`. `api/views.py` already
imports `now` the same way. `api/serializers.py` does not import `schedule`
or `world` yet, and both are allowed for `api/`. Extend the `RiderSerializer` docstring by one
sentence: `final_season` is the only visible consequence of the hidden
retirement age, and the age itself is never shipped.

`is_due_to_retire` already returns `False` for a retired rider, so a retired
profile never shows the tag.

## frontend/src/api.ts

Add `final_season: boolean` to `interface Rider`, with one line in its doc
comment: "true while a season runs and this is the rider's last; they retire
when it closes (#42)". `FreeAgent` and `RiderProfile` inherit it.

## frontend/src/components/primitives.tsx

New `export function FinalSeasonTag()`. It is a small pill reading `LAST
SEASON`, mono font, 10.5px, `letterSpacing: '1px'`, background
`color.accentWash`, text `color.accentInk`, `borderRadius: 6`, `padding: '2px
7px'`, `title="Retires when this season ends"`. Use theme tokens only, no
new colours. Check `design/README.md` for a pill or tag convention first, and
follow it if one exists.

## frontend screens

Render `{rider.final_season ? <FinalSeasonTag /> : null}` at:

- `screens/Roster.tsx`, `RiderCard`: on the speciality/age sub-line, after
  "`N yrs`".
- `screens/Roster.tsx`, `RiderPanel`: beside the name in the panel header.
- `screens/RiderProfile.tsx`: as `PageHeading`'s `aside`.
- `screens/Transfers.tsx`, `FreeAgentCard`: beside the name link.

Every existing test fixture building a `Rider`/`FreeAgent`/`RiderProfile`
needs `final_season: false` added, or `tsc -b` fails. They are in
`AuctionCard.test.tsx`, `Dashboard.test.tsx`, `RiderProfile.test.tsx`,
`Roster.test.tsx`, `Transfers.test.tsx` and `useRiderProfile.test.ts` (grep
`release_cost` to find each).

## Work items

### W1 — `riders/`: retirement age and the retire step ✅
Rename `PEAK_AGE_RANGE`, and add `RETIREMENT_AGE_MIN/SPAN`, `retirement_age`,
`is_due_to_retire` and `retire_due_riders`. Tests go in
`riders/tests/test_services.py`:
- `test_retirement_age_spans_33_to_38`: (peak 24, decline 100) → 33;
  (peak 32, decline 1) → 38.
- `test_retirement_age_is_later_for_late_peakers` and
  `test_retirement_age_is_sooner_for_fast_decliners`: vary one trait and hold
  the other.
- `test_retirement_age_clamps_out_of_generation_peak`: peak 22 and 34 stay
  inside 33–38.
- `test_generated_population_retires_within_window`: 2,000 seeded
  `generate_rider()`s, all in [33, 38], mean between 35 and 36. This pins D2
  against generation.
- `test_is_due_to_retire_false_for_retired_rider`.
- `test_retire_due_riders_retires_rostered_rider_and_clears_team`.
  **Load-bearing:** a rider *with a team* ends with `team=None` and
  `retired_at` set, and the constraint does not fire.
- `test_retire_due_riders_retires_free_agent`.
- `test_retire_due_riders_skips_riders_below_their_age`.
- `test_retire_due_riders_leaves_already_retired_untouched`: the original
  `retired_at` is kept.
- `test_retire_due_riders_leaves_unattached_since_untouched`.

### W2 — `transfers/`: cancel open auctions ✅
Add `cancel_open_auctions`. Tests go in `transfers/tests/test_services.py`:
- `test_cancel_open_auctions_cancels_only_open`: OPEN → CANCELLED with
  `resolved_at`; SOLD/UNSOLD untouched.
- `test_cancel_open_auctions_keeps_bid_history`: the auction's `Bid` rows
  survive, since bids are append-only. The no-money-moves guarantee is
  structural (the function takes no charge or pay callbacks), and W3's
  world-level test checks the ledger.

### W3 — `world/`: retire at season close, before ageing ✅
Add the `TickRun.riders_retired` field and migration 0016, plus the step in
`tick()`. Tests go in `world/tests/test_services.py`:
- `test_tick_retires_due_riders_at_season_close`.
- `test_tick_does_not_retire_mid_season`: only week boundaries crossed.
- **`test_tick_retires_before_ageing`** (load-bearing, D4): a rider one year
  below their retirement age is *not* retired at this close and ends one year
  older. A rider at their age *is* retired and their age is unchanged.
- `test_retired_rider_is_stamped_with_final_week_start` (D6).
- `test_retired_rider_leaves_salary_review`: a managed team's
  `SalaryReviewReport` does not list the retiree.
- `test_tick_cancels_retiring_riders_open_auction`, in
  `world/tests/test_auctions.py`: the auction is `CANCELLED` and no
  `LedgerEntry` is written for either team.
- `test_tick_records_riders_retired`.

### W4 — `api/`: `final_season` on every rider payload ✅
Serializer field and `_in_season` helper. Tests go in `api/tests.py`:
- `test_roster_marks_final_season_rider_in_season`.
- `test_roster_does_not_mark_final_season_off_season`: clock between
  seasons, same rider → `false`.
- `test_free_agents_carry_final_season` and
  `test_rider_profile_carries_final_season`.
- `test_retired_rider_profile_final_season_false`.
- `test_roster_in_season_is_computed_once`: `django_assert_max_num_queries`,
  or extend the existing constant-query-count guard. The roster's query count
  must not grow with roster size.
- Update the existing hidden-trait key-set tests (profile "exact key set",
  and `test_rider_list_response_has_no_hidden_traits`) so `final_season` is
  expected. Add `"retirement_age"` to the list of keys that must never
  appear.

### W5 — `frontend/`: the Last season tag ✅
Type, primitive, the four render sites and the fixture updates. Tests:
- `Roster.test.tsx`: the tag renders on a `final_season: true` card and is
  absent on `false`.
- `RiderProfile.test.tsx`: the tag appears in the heading when true.
- `Transfers.test.tsx`: the tag appears on a free-agent card when true.
- `npm run lint`, `npm run build` (runs `tsc -b`) and the full `npm test` pass.

### W6 — Docs, seed note, spec/plan archive ✅
See *Documentation update*. Set both `Status:` lines to `implemented` and
move both files to `specs/archive/`.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6, committing after each.

- W1 and W2 are leaf changes with no callers, and green on their own.
- W3 wires them into the tick. It is the item where D4's ordering can be
  broken, so it lands with its load-bearing test.
- W4 depends on W1 (`is_due_to_retire`) but not on W3, so either order works.
  Keep W3 first so the backend behaviour is complete before it is surfaced.
- W5 depends on W4's payload.
- Run the full backend suite after W3 and W4, and the frontend suite after W5.

## Documentation update (required, not optional)

- **`riders/README.md`**
  - *The age curve*: replace "Decline has no floor, but retirement is
    explicit" with the rule that riders now retire by age, and point to
    *Retirement*.
  - *Retirement*: add a subsection *Retiring by age*. Cover:
    - the 33–38 window;
    - that the age is derived from `peak_age` and `decline_rate` (name the
      weighting, not the full formula), with no stored trait;
    - `is_due_to_retire`;
    - `retire_due_riders`'s single UPDATE and why it cannot reuse
      `retire_riders`;
    - that `unattached_since` stays untouched;
    - the final-week stamp (D6).
  - *Visible vs hidden*: add that `final_season` is the one visible
    consequence of the retirement age.
  - *Future work*: remove the "Age-driven retirement" bullet.
- **`world/README.md`**, *How a tick works*: the season-close sequence is now
  retire → cancel auctions → age → reprice → salary reviews, with D4's reason.
  Mention `TickRun.riders_retired` vs `agents_retired`.
- **`transfers/README.md`**, *Auctions*: `cancel_open_auctions`, and that a
  retiring rider's open auction is cancelled at the close with no money moved.
- **`api/README.md`**: `final_season` on every `RiderSerializer` payload, and
  the context-cached in-season check (D8).
- **`frontend/README.md`**: the `FinalSeasonTag` primitive and where it
  renders.
- **`AGENTS.md`**: the `riders/` row adds "age-driven retirement with a
  season's warning". The `world/` row's tick description adds "retires riders
  who have reached their retirement age at each season close".

## Verification

**The likeliest failure is D4 reversed or skipped**: a rider retires at a
close without having carried the tag that season. Unit test W3's
`test_tick_retires_before_ageing` catches it. Confirm it end to end too.

From the worktree root, with `GAME_CLOCK_CLASS=world.clocks.MockClock`:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python scripts/dev_db.py
/home/mario/dev/cycling-manager/.venv/bin/python manage.py migrate
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_user
/home/mario/dev/cycling-manager/.venv/bin/python manage.py seed_teams --claim-for test@mail.com
/home/mario/dev/cycling-manager/.venv/bin/python manage.py load_season seasons/season-1.example.json
/home/mario/dev/cycling-manager/.venv/bin/python manage.py mock_clock set <season start + 1 day>
/home/mario/dev/cycling-manager/.venv/bin/python manage.py tick
```

1. **Before the close:** in `manage.py shell`, list active riders with `age >=
   retirement_age(r)`. Record their ids and count. Generated rosters reach 36,
   so there are always some. Log in as `test@mail.com`, and check:
   - **Roster:** exactly the demo team's riders in that set show LAST SEASON.
   - **Transfers → Free agents:** the same holds for the pool.
   - **One marked rider's profile:** the tag shows in the heading.
   - **An unmarked rider aged 33+:** no tag. This proves the age window
     varies per rider (spec *In scope* #6).
2. **Close the season:** `mock_clock set <season end + 1 day>`, then `tick`.
   Confirm:
   - The newest `TickRun.riders_retired` equals the count from step 1.
   - Every recorded id now has `team_id IS NULL` and a `retired_at` equal to
     week 12's `starts_at`.
   - **No other rider retired.** This is the real proof of D4.
3. **Between seasons:** reload the roster. The retirees are gone and **no
   rider shows the tag** (off-season, D3). Open a retiree via an old race
   result: the profile shows "Retired · Season 1, Week 12" and no tag.
4. **Auction:** before step 2, list one marked demo-team rider for auction
   and bid on it from a second account. After the close, the auction is
   `CANCELLED`, the market no longer shows it, and neither team's ledger has
   an entry for it.

Full suites: `.venv/bin/python -m pytest` (the 85% coverage floor must hold)
and, in `frontend/`, `npm test`, `npm run lint` and `npm run build`.

## Risks

| Risk | Mitigation |
|---|---|
| Ageing runs before retiring, so riders retire without their warning season. | D4 is marked load-bearing, `test_tick_retires_before_ageing`, and verification step 2's "no other rider retired" check. |
| Reusing `retire_riders()` silently skips every rostered rider (it filters `team__isnull=True`). | D5 names this explicitly, and `test_retire_due_riders_retires_rostered_rider_and_clears_team` fails if it happens. |
| Stamping `season.ends_at` mislabels the retirement as the next season's week 1 when seasons abut. | D6, plus `test_retired_rider_is_stamped_with_final_week_start`. |
| The `in_season` check adds one query per rider on a roster. | D8's context cache, plus the W4 query-count test. |
| `retirement_age` or its inputs leak into a payload. | Only the boolean is serialized, and W4 extends the hidden-key tests with `retirement_age`. |
| A fresh world retires a large batch at its first close (generated ages reach 36, so every 36-year-old and most 34–35-year-olds are marked from day one). | Accepted by the spec as realistic. Verification step 1 makes the size visible, so it is not a surprise. |
| Unmanaged rosters shrink below four riders over several seasons and stop racing. | Accepted by the spec (*Decisions taken*, replacement supply). Covered by #32/#33, next on the roadmap. |
| A manager signs or wins a marked rider in the same instant the close runs, and pays for a rider who retires at once. | Accepted (D10). The rider was visibly marked all season. |
| The generation age range or peak-age range changes later and shifts the window. | `PEAK_AGE_RANGE` is shared rather than copied (D2), and `test_generated_population_retires_within_window` re-checks the distribution. |

## Open questions

None.
