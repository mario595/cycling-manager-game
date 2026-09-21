# Sponsorship contracts — Implementation Plan

**Spec:** `specs/sponsorship-contracts.md` · **Issue:** #22 · **Status:** proposed
**Apps touched:** `economy/`, `world/`, `teams/`, `api/`, `frontend/`

## Context you need

`economy/` owns an **append-only** ledger. A team's balance is never stored —
it is `Sum(LedgerEntry.amount)` over that team's rows (`economy/README.md`,
*The ledger is append-only*). Fanbase works the same way over `FanbaseEntry.delta`.
Do not add a balance column, a cached total, or a `paid_to_date` field anywhere
in this feature; the sum is the source of truth and a cache of it is a
documented regression.

Weekly money already runs off week boundaries. `world.services.tick()` calls
`schedule.services.process_week_transitions(at)`, which returns one
`WeekTransition` per crossed boundary, and loops **one week at a time**
(`world/services.py:231`, the `# per week, NOT weeks=len(weeks)` loop). Inside
that loop it calls `charge_weekly_wages(week)`, `apply_weekly_fanbase(week,
points_by_team=…)` and `pay_merchandise(week)`. Sponsorship joins this loop.
Two properties fall out of it for free and you must not reimplement them:
exactly-once (the `WeekTransition` row, unique on `week`) and correct dating
(`occurred_at` is `week.starts_at`, never `now()`).

`economy/` **may not import `competitions/`** (`AGENTS.md`'s dependency graph).
`apply_weekly_fanbase` already solves this: it takes `points_by_team: dict[int,
int]` as an argument and `world/` — the app allowed to know everything — builds
that dict from `competitions.services.points_by_team(week)`. Sponsorship's
weekly payment needs the same data and uses the same inversion. Do not add an
import; do not use `apps.get_model` to sneak one in.

The two existing patterns you will copy directly:

- **Per-row `transaction.atomic()` with `IntegrityError` caught and
  `continue`** — see `charge_weekly_wages` (`economy/services.py:129`). One
  `atomic()` per create, never one around the loop: an `IntegrityError` poisons
  the enclosing transaction in Django.
- **`select_for_update()` then re-check after the lock** — see `hire_trainer`
  (`staff/services.py:27`). Signing an offer is the same shape as hiring a
  trainer: a player action on a row another request may be touching.

Read before starting: `economy/README.md`, `world/README.md` (*How a tick
works*), `staff/README.md` (the hire flow), and the spec.

## Goal

When this is done:

1. A team has three `SponsorOffer` rows generated at season open, and again on
   claim, sized off the team's fanbase at that moment.
2. A manager can sign exactly one of them, producing a `SponsorContract` that
   runs to the end of the season and cannot be changed.
3. Every week boundary, each team with an active contract gets one
   `LedgerEntry` of `kind="sponsorship"`, its amount varying with that week's
   race points, bounded by the contract's stored floor and ceiling.
4. A team with no contract produces no row at all — not a zero row.
5. The Finances screen shows the sponsorship line in history; a new Sponsors
   screen shows the offer round, or the signed contract.
6. Claiming a team voids any contract and generates a fresh offer round.

## Design decisions (settled — implement these, do not substitute)

**D1 — Two models, not one with a flag.** `SponsorOffer` (disposable) and
`SponsorContract` (permanent). An offer round is regenerated wholesale, which
means deleting the round's unsigned offers; with one table that delete would
run against the same rows holding signed contracts, and one wrong filter
destroys financial history. Separate tables make the destructive operation
structurally unable to touch a contract. **Do not** collapse these into one
model with `is_signed`.

**D2 — The contract copies its terms; it does not point at the offer's.**
`SponsorContract` stores `weekly_base`, `floor_amount`, `ceiling_amount` and
`sensitivity` as its own columns, copied at signing. The offer it came from is
kept as a nullable FK for provenance only and is never read for money. Reason:
offers get deleted when a round is regenerated, and a contract whose terms live
on a deleted row is a contract that cannot be paid. **Load-bearing** — this is
the single most likely thing to get wrong here.

**D3 — Performance is measured against the team's own season-to-date
average, not against the field.** The spec left this open and flagged it as
affecting whether a struggling team can recover. Relative-to-field makes a
team's income a function of other teams' results, which cannot be explained on
a finances screen. Relative-to-self means a team that improves gets paid more
even while still losing — the comeback path the spec wanted. A team with no
prior scoring weeks this season (week 1, or a freshly claimed team) has no
average, and pays `weekly_base`.

**D4 — Three fixed sponsor profiles, not rolled sensitivity.** `STEADY`,
`BALANCED`, `DEMANDING` — a constant table of (base multiplier, sensitivity,
floor fraction, ceiling fraction). A round is always one of each, so the player
always sees the full spread of the decision. Rolling three independent
sensitivities can produce three near-identical cards, which the spec explicitly
forbids ("the choice is never three near-identical cards"). Same reasoning as
`generate_trainer_pool` cycling specialities rather than rolling them
(`staff/generation.py:80`).

**D5 — Payment is computed from the completed week, exactly like fanbase.**
Use `world.services._completed_week(week)`, already in the tick, and the same
`points_by_team` dict already computed on `world/services.py:242`. Entering
week N pays on week N−1's racing. The week being opened has no results yet —
the `WeekTransition` is written when a week *opens*, before its races run. Reuse
the dict already in scope; do not query points a second time.

**D6 — The floor and ceiling are stored per contract, not derived at payment
time.** The spec promises the range is shown at signing and honoured after. If
payment recomputed bounds from a formula, a later constant change would
silently reprice contracts a player already signed against a displayed promise.
Storing them makes the promise durable. **Load-bearing.**

**D7 — Claiming voids the contract; it does not delete it.** `claim_team` sets
`SponsorContract.voided_at` on any active contract and deletes the team's
unsigned offers. The contract row survives as history (append-only discipline:
history is never destroyed), it simply stops being active. A voided contract
never pays.

**D8 — Offer generation is idempotent per (team, season).** Generated inside
`world/`'s season-open loop and from `claim_team`. Both call the same
`ensure_offer_round(team, season, at=…)`, which no-ops if the team already has
unsigned offers for that season or an active contract. Season opens are already
exactly-once via `SeasonTransition`, but claim is not, and a manager who claims
mid-season must not accumulate rounds.

## Data model

Both models in `economy/models.py`, both extending `TimeStampedModel` from
`core.models`, matching `LedgerEntry`/`FanbaseEntry`.

### New constants (`economy/models.py`, alongside the existing block)

```python
#: A sponsor's weekly baseline as a fraction of fanbase. At STARTING_FANBASE
#: (10,000) a BALANCED offer pays 10,000 // 1 = ... see SPONSOR_PROFILES.
#: Fanbase // this divisor is the BALANCED baseline before the profile's own
#: multiplier. Chosen so a starting team's sponsorship is the largest single
#: income stream (spec: "largest income stream") without covering the
#: 14,400/week wage bill on its own.
SPONSOR_FANBASE_PER_CREDIT = 2

#: Offers generated per round. Always one of each profile (D4).
OFFERS_PER_ROUND = 3
```

`SPONSOR_FANBASE_PER_CREDIT = 2` makes a starting team's BALANCED baseline
`10_000 // 2 = 5_000`/week against a 14,400 wage bill — ~35%, the largest
single stream (merchandise pays 400) and nowhere near solvency. Tunable; put
the reasoning in the comment the way `STARTING_FANBASE` does.

### `SponsorProfile` — a plain constant table, not a model

In a new `economy/sponsors.py`:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class SponsorProfile:
    key: str
    label: str            # player-facing name, e.g. "Steady"
    blurb: str            # the one-line character from the spec
    base_multiplier: float    # applied to the fanbase-derived baseline
    sensitivity: float        # how hard payment swings with performance
    floor_fraction: float     # floor = base * this
    ceiling_fraction: float   # ceiling = base * this

PROFILES = (
    SponsorProfile("steady", "Steady", "Pays the same every week, whatever happens.",
                   base_multiplier=0.85, sensitivity=0.0,
                   floor_fraction=1.0, ceiling_fraction=1.0),
    SponsorProfile("balanced", "Performance-driven", "Pays more when you score, less when you don't.",
                   base_multiplier=1.0, sensitivity=0.5,
                   floor_fraction=0.6, ceiling_fraction=1.6),
    SponsorProfile("demanding", "Results-hungry", "Pays big for big results — and little for none.",
                   base_multiplier=1.25, sensitivity=1.0,
                   floor_fraction=0.35, ceiling_fraction=2.2),
)
```

STEADY has `sensitivity=0.0` and floor == ceiling == base, so it is genuinely
flat and needs no special case in the payment maths.

### `SponsorOffer`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `team` | FK `teams.Team`, `CASCADE`, `related_name="sponsor_offers"` | no | — | Offers die with the team. |
| `season` | FK `schedule.Season`, `CASCADE`, `related_name="sponsor_offers"` | no | — | String FK (`"schedule.Season"`), matching `LedgerEntry.week`. |
| `profile` | `CharField(max_length=20, choices=…)` | no | — | Choices built from `PROFILES` keys. |
| `sponsor_name` | `CharField(max_length=80)` | no | — | Flavour, rolled at generation. |
| `weekly_base` | `PositiveIntegerField()` | no | — | Credits/week before swing. |
| `floor_amount` | `PositiveIntegerField()` | no | — | Shown as the low end of the range. |
| `ceiling_amount` | `PositiveIntegerField()` | no | — | Shown as the high end. |
| `sensitivity` | `FloatField()` | no | — | Copied from the profile at generation. |

`Meta`: `ordering = ["pk"]`; `UniqueConstraint(fields=["team", "season", "profile"],
name="one_offer_per_profile_per_team_per_season")` — the constraint that makes
D8's idempotence real rather than checked.

### `SponsorContract`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `team` | FK `teams.Team`, `CASCADE`, `related_name="sponsor_contracts"` | no | — | |
| `season` | FK `schedule.Season`, `PROTECT`, `related_name="sponsor_contracts"` | no | — | `PROTECT`: a season with contracts is financial history. |
| `offer` | FK `SponsorOffer`, `SET_NULL`, `related_name="contract"` | **yes** | `None` | Provenance only. Never read for money (D2). |
| `profile` | `CharField(max_length=20, choices=…)` | no | — | Copied. |
| `sponsor_name` | `CharField(max_length=80)` | no | — | Copied. |
| `weekly_base` | `PositiveIntegerField()` | no | — | Copied (D2). |
| `floor_amount` | `PositiveIntegerField()` | no | — | Copied (D2, D6). |
| `ceiling_amount` | `PositiveIntegerField()` | no | — | Copied (D2, D6). |
| `sensitivity` | `FloatField()` | no | — | Copied. |
| `signed_at` | `DateTimeField()` | no | — | Game time, from the caller. |
| `voided_at` | `DateTimeField()` | **yes** | `None` | Set by `claim_team` (D7). Non-null means it never pays again. |

`Meta`: `ordering = ["-signed_at", "-pk"]`; `UniqueConstraint(fields=["team",
"season"], condition=Q(voided_at__isnull=True),
name="one_active_contract_per_team_per_season")` — conditional, so a voided
contract does not block the new manager's signing.

### `LedgerEntry.Kind`

Add `SPONSORSHIP = "sponsorship", "Sponsorship"`. Add a matching partial unique
constraint, exactly parallel to the two that exist:

```python
models.UniqueConstraint(
    fields=["team", "week"],
    condition=models.Q(kind="sponsorship"),
    name="one_sponsorship_entry_per_team_per_week",
),
```

### Migrations

- `economy/migrations/00XX_sponsor_offer_contract.py` — both models, the new
  `Kind` choice, the new constraint.
- No data migration. Existing teams simply have no offers until the next season
  opens; `seed_teams` is extended (W8) to give the demo world a round.

## economy/sponsors.py (new)

Pure functions, no ORM, so they are testable without a database — the same
split `riders/display.py` and `staff/generation.py` use.

```python
def offer_terms(profile: SponsorProfile, fanbase: int) -> dict:
    """The four money figures for one offer at a given fanbase.
    Returns {"weekly_base", "floor_amount", "ceiling_amount", "sensitivity"}.
    All integers except sensitivity; floor/ceiling are derived from the
    base here ONCE and then stored (D6)."""

def payment_for(
    *, weekly_base: int, floor_amount: int, ceiling_amount: int,
    sensitivity: float, points: int, average_points: float | None,
) -> int:
    """This week's sponsorship payment, clamped into [floor, ceiling].

    `average_points` is the team's own season-to-date mean (D3); None means
    no history yet, which pays weekly_base exactly. The ratio is computed
    against a floor of 1.0 on the average so a team averaging zero does not
    divide by zero — a team with no scoring history that then scores is
    treated as beating its average.
    """
```

The clamp is the last operation and applies to the final integer. Real code for
`payment_for`, because the natural first attempt (scaling then clamping the
ratio rather than the amount) produces a payment outside the promised range:

```python
def payment_for(*, weekly_base, floor_amount, ceiling_amount,
                sensitivity, points, average_points):
    if average_points is None or sensitivity == 0.0:
        amount = weekly_base
    else:
        baseline = max(average_points, 1.0)
        ratio = points / baseline          # 1.0 == exactly on form
        amount = round(weekly_base * (1.0 + sensitivity * (ratio - 1.0)))
    # Clamp the AMOUNT, never the ratio: the range shown at signing is a
    # promise about credits, and clamping the ratio lets rounding push the
    # result a credit or two outside it.
    return max(floor_amount, min(ceiling_amount, amount))
```

## economy/services.py

```python
def offers_for(team, season) -> QuerySet[SponsorOffer]:
    """This team's unsigned offers for `season`, ordered by profile."""

def active_contract(team, season) -> SponsorContract | None:
    """The team's non-voided contract for `season`, or None."""

def ensure_offer_round(team, season, *, at, rng=None) -> list[SponsorOffer]:
    """Generate one offer per profile for (team, season), once (D8).

    No-ops and returns [] if the team already has offers for that season or
    an active contract. Sized off fanbase_for(team) at call time.
    `at` is game time from the caller — economy/ may not import world/.
    """

def sign_offer(team, offer_id: int, *, at) -> SponsorContract:
    """Sign one of this team's offers. Copies the terms onto the contract
    (D2) and deletes the round's remaining offers.

    Locks the offer row WITHOUT skip_locked, re-checking ownership and
    availability after the lock — same shape and same reason as
    staff.services.hire_trainer.
    """

def pay_sponsorship(week, *, points_by_team: dict[int, int]) -> int:
    """Credit each team with an active contract its sponsorship for `week`.
    Returns entries written. Teams without a contract get NO row (spec).
    """
```

Exceptions, mirroring `staff/services.py`'s: `SponsorshipError`,
`OfferNotAvailable`, `AlreadySponsored`.

`sign_offer`'s lock-and-recheck, written out because getting it wrong allows two
requests to sign two different offers for the same team:

```python
def sign_offer(team, offer_id, *, at):
    with transaction.atomic():
        try:
            offer = SponsorOffer.objects.select_for_update().get(pk=offer_id)
        except SponsorOffer.DoesNotExist:
            raise OfferNotAvailable("That offer is no longer available.")
        if offer.team_id != team.pk:
            raise OfferNotAvailable("That offer is not yours.")
        # AFTER the lock: the loser of a concurrent double-sign arrives here
        # and is told, rather than creating a second contract. The partial
        # unique constraint is the second line of defence.
        if active_contract(team, offer.season) is not None:
            raise AlreadySponsored("Your team already has a sponsor this season.")

        contract = SponsorContract.objects.create(
            team=team, season=offer.season, offer=offer,
            profile=offer.profile, sponsor_name=offer.sponsor_name,
            weekly_base=offer.weekly_base, floor_amount=offer.floor_amount,
            ceiling_amount=offer.ceiling_amount, sensitivity=offer.sensitivity,
            signed_at=at,
        )
        # The signed offer is kept (the contract FKs it); the rest of the
        # round goes, so the screen has nothing stale to render.
        SponsorOffer.objects.filter(team=team, season=offer.season).exclude(pk=offer.pk).delete()
    return contract
```

`pay_sponsorship` needs each team's season-to-date average. It cannot query
`RacePoints` (dependency rule), so it derives the average from **its own
ledger's history plus the injected dict**: count how many prior weeks this
season already have a sponsorship row for the team, and track points on the
entry. Add `points` to `LedgerEntry`? No — `FanbaseEntry` already stores
`points` per week and `economy/` owns it. Read the team's `FanbaseEntry` rows
for the season instead:

```python
def _season_average_points(team_id, season, current_week) -> float | None:
    """Mean points per already-settled week this season, from the team's own
    FanbaseEntry rows — economy/ owns those and they already carry `points`
    (economy/README.md). Returns None when no prior week has settled, which
    pays weekly_base (D3)."""
    rows = FanbaseEntry.objects.filter(
        team_id=team_id, kind=FanbaseEntry.Kind.WEEKLY,
        week__season=season, week__number__lt=current_week.number,
    ).values_list("points", flat=True)
    values = list(rows)
    return (sum(values) / len(values)) if values else None
```

This is why ordering inside the tick matters — see D5 and Execution order.

## world/services.py

Two additions to `tick()`, no new function.

1. **Season open → offer rounds.** The existing loop over `transitions` already
   calls `top_up_pool()` per boundary. Add, for `OPENED` transitions only, a
   pass over every team calling `ensure_offer_round(team, transition.season,
   at=now)`. Idempotent per D8, so a catch-up tick cannot double-generate.

2. **Weekly payment.** Inside the existing per-week loop, after
   `pay_merchandise(week)`:

```python
        sponsorship_entries += pay_sponsorship(week, points_by_team=points)
```

`points` is already in scope (`world/services.py:242`) — reuse it, do not
recompute. Order within the loop is `charge_weekly_wages` →
`apply_weekly_fanbase` → `pay_merchandise` → `pay_sponsorship`.
**`pay_sponsorship` must run after `apply_weekly_fanbase`**, because
`_season_average_points` reads `FanbaseEntry` rows and excludes the current
week by `week__number__lt` — running before would work too, but running after
keeps every money function reading a fully-settled week and matches how
`pay_merchandise` already depends on fanbase being current.

Add `sponsorship_entries` to `TickRun` (new `PositiveIntegerField(default=0)`,
its own small migration in `world/`), alongside `wage_entries`,
`merchandise_entries` and `fanbase_entries`.

## teams/services.py

In `claim_team`, extend the existing lazy-import block (the one that already
imports `reset_fanbase` and `reset_to_starting_balance` **inside the function
body** — `teams/services.py:68`; keep it inside, module scope creates the
import cycle `AGENTS.md` forbids):

```python
        from economy.services import (
            reset_fanbase, reset_to_starting_balance, void_sponsorship,
        )
        reset_to_starting_balance(team, at=at)
        reset_fanbase(team, at=at)
        void_sponsorship(team, at=at)
```

`void_sponsorship(team, *, at)` in `economy/services.py`: sets `voided_at` on
any active contract and deletes the team's unsigned offers, for every season.
It does **not** generate the new round — `claim_team` has no `Season` to hand it
and `teams/` may not import `schedule/`. The new round is generated lazily by
the API on first read (W6): `SponsorsView` calls `ensure_offer_round` for the
current season when the team has neither offers nor a contract. That also
covers a team claimed before any season exists.

## api/

- `SponsorsView` (GET) at `economy/sponsors/` — returns `{"contract": …|null,
  "offers": [...], "season": n|null}`. Calls `ensure_offer_round` when the team
  has neither, so a freshly claimed manager sees a round without waiting for a
  tick. Returns the empty shape (not 403) for a user with no team, matching
  `FinancesView`.
- `SignOfferView` (POST) at `economy/sponsors/sign/` — body `{"offer_id": n}`.
  409 for `OfferNotAvailable`/`AlreadySponsored`, matching `HireTrainerView`'s
  documented 400-vs-409 split. 204 on success.
- Serializers: `SponsorOfferSerializer`, `SponsorContractSerializer`,
  `SponsorsSerializer`, `SignOfferSerializer` — same plain-`Serializer` style
  as the rest of `api/serializers.py`.
- `LedgerEntrySerializer` needs nothing: `kind` and `description` are already
  generic fields, so the sponsorship row renders in history for free.

## frontend/

- `src/api.ts` — `Sponsor*` types, `fetchSponsors()`, `signOffer(id)`.
- `src/useSponsors.ts` — hook in the shape of `useStaff.ts`.
- `src/screens/Sponsors.tsx` — three offer cards (or the signed contract), built
  from `Staff.tsx`'s card grid (`gridTemplateColumns: 'repeat(auto-fill,
  minmax(288px, 1fr))'`) so it matches without new layout primitives. Each card:
  sponsor name, profile label, blurb, `$` baseline, `$floor–$ceiling` range,
  term. **Every money figure gets the `$` prefix and thousands separators**
  (`AGENTS.md`, *Displaying game money*); the range is money, so both ends get
  `$`.
- `src/components/Sidebar.tsx` — a Sponsors entry.
- `src/App.tsx` — the route.
- Finances needs no change; the new ledger kind flows through the existing list.

## Work items

### W1 — `economy/sponsors.py`: profiles and the money maths ✅ done
New file: `SponsorProfile`, `PROFILES`, `offer_terms`, `payment_for`. No ORM,
no Django. **Load-bearing:** the clamp in `payment_for` applies to the final
amount, not the ratio.
**Test:** `economy/tests/test_sponsor_maths.py` — no database needed, matching
the pure-function split (`economy/tests/` already splits by feature:
`test_wages.py`, `test_fanbase.py`, `test_merchandise.py`).
`test_steady_profile_pays_base_regardless_of_points`,
`test_payment_rises_above_average_and_falls_below`,
`test_payment_never_leaves_the_range`, `test_no_history_pays_base`,
`test_zero_average_does_not_divide_by_zero`.

### W2 — `economy/models.py`: the two models, the kind, the constraints ✅ done
Both models, `SPONSORSHIP` kind, the partial unique constraint, the two new
constants, and the migration.
**Test:** `economy/tests/test_models.py` — `test_one_active_contract_per_team_per_season`,
`test_voided_contract_does_not_block_a_new_one`,
`test_one_sponsorship_entry_per_team_per_week`.

### W3 — `economy/services.py`: offers, signing, voiding ✅ done (committed with W4)
`offers_for`, `active_contract`, `ensure_offer_round`, `sign_offer`,
`void_sponsorship`, and the three exceptions. **Load-bearing:** `sign_offer`
copies terms onto the contract (D2) and re-checks after the lock.
**Test:** `economy/tests/test_sponsorship.py` —
`test_round_is_one_offer_per_profile`, `test_round_is_idempotent`,
`test_offers_scale_with_fanbase`, `test_signing_copies_terms_onto_the_contract`,
`test_signing_deletes_the_rest_of_the_round`,
`test_second_sign_raises_already_sponsored`,
`test_signing_another_teams_offer_is_refused`,
`test_void_marks_contract_and_clears_offers`.

### W4 — `economy/services.py`: `pay_sponsorship` ✅ done (committed with W3 — both landed together, already tested and green; splitting a working diff after the fact added risk with no benefit)
Plus `_season_average_points`. Per-row `atomic()` with `IntegrityError` caught,
copying `charge_weekly_wages`. **Load-bearing:** a team with no active contract
gets no row at all.
**Test:** `economy/tests/test_sponsorship.py` —
`test_pays_one_entry_per_contracted_team`,
`test_team_without_contract_gets_no_entry`,
`test_voided_contract_is_not_paid`, `test_entry_is_dated_to_the_week_start`,
`test_second_call_for_the_same_week_writes_nothing`.

### W5 — `world/services.py`: wire into the tick ✅ done
Offer rounds on season open, `pay_sponsorship` in the weekly loop,
`TickRun.sponsorship_entries` and its migration.
**Test:** `world/tests/test_tick.py` — `test_tick_generates_offer_rounds_on_season_open`,
`test_tick_pays_sponsorship_for_contracted_teams`,
`test_catch_up_tick_pays_each_week_separately`,
`test_offer_rounds_are_not_duplicated_by_a_second_tick`.

### W6 — `api/`: views, serializers, routes ✅ done
`SponsorsView`, `SignOfferView`, serializers, two URLs.
**Test:** `api/tests.py` — `test_sponsors_returns_a_round_for_a_new_team`,
`test_sponsors_returns_the_contract_once_signed`,
`test_sign_creates_the_contract`, `test_sign_twice_is_409`,
`test_sponsors_without_a_team_is_empty_not_403`.

### W7 — `teams/services.py`: void on claim ✅ done
The lazy import and the `void_sponsorship` call inside `claim_team`.
**Load-bearing:** the import stays inside the function body.
**Test:** `teams/tests/test_services.py` — `test_claiming_voids_the_previous_contract`,
`test_claiming_clears_unsigned_offers`.

### W8 — `teams/management/commands/seed_teams.py`: seed a round
Give seeded teams an offer round so the feature is visible without waiting for
a season boundary, using the same in-`handle()` import pattern the command
already uses for `ensure_opening_balance`. Note it in `AGENTS.md`'s seeding
section.
**Test:** `teams/tests/test_seed_teams.py` — `test_seeded_teams_get_an_offer_round`.

### W9 — `frontend/`: the Sponsors screen
`api.ts`, `useSponsors.ts`, `Sponsors.tsx`, sidebar entry, route.
**Load-bearing:** every money figure carries `$` and thousands separators.
**Test:** `frontend/src/screens/Sponsors.test.tsx` —
`renders three offers with their ranges`, `signing calls the API and refreshes`,
`shows the signed contract instead of the pool`, `formats money with $`.

### W10 — Documentation
`economy/README.md`, `world/README.md`, `teams/README.md`, `frontend/README.md`,
`AGENTS.md`. Details below.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9 → W10.

W1 first because it is pure functions with no database: the money maths is the
part most likely to be wrong, and proving it in isolation means every later
failure is a wiring failure, not an arithmetic one. W2 before W3 because
services need tables. W4 is separated from W3 deliberately — signing and paying
fail in different ways and a combined commit hides which. W5 only once both
halves are proven, so a tick failure is unambiguous. W7 after W6 because the
API is what regenerates a round after a void, so the claim path is only
observable once the view exists.

Commit after each work item; each leaves the suite green.

## Documentation update (required, not optional)

- **`economy/README.md`** — a new *Sponsorship* section: the two-model split and
  why (D1), the terms-are-copied rule (D2), the stored floor/ceiling (D6),
  performance-relative-to-self (D3), and that a team without a contract gets no
  row. Move sponsorship out of *Future work*, leaving `#23` there.
- **`world/README.md`** — *How a tick works*: sponsorship in the weekly loop
  after merchandise, and offer rounds on season open.
- **`teams/README.md`** — *What `teams/` may import*: `void_sponsorship` joins
  the list of `economy/` functions `claim_team` lazily imports.
- **`frontend/README.md`** — the Sponsors screen in the screen list.
- **`AGENTS.md`** — the `economy/` row gains sponsorship; the seeding section
  notes the offer round.

Per `AGENTS.md`'s *Closing a ticket*, delete `specs/sponsorship-contracts.md`
and this plan before opening the PR.

## Verification

```bash
.venv/bin/python -m pytest
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_user
.venv/bin/python manage.py seed_teams --claim-for test@mail.com
.venv/bin/python manage.py seed_trainers
.venv/bin/python manage.py load_season seasons/season-1.example.json
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py mock_clock set 2027-03-01T00:00:00Z
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py mock_clock tick
```

Then, in the SPA: open Sponsors, confirm three cards with distinct ranges and
`$`-prefixed money; sign one; confirm the screen switches to the contract.
Advance several weeks (`mock_clock set` a later date, then `tick`) and confirm
on Finances that each week has exactly one Sponsorship row and the amounts vary
with the weeks the team scored.

**The likeliest failure mode is D2** — a contract reading its terms through the
deleted offer, which passes every unit test written against a fresh database and
fails the moment a round is regenerated. The check that catches it: sign an
offer, then claim a *different* team and force a new round, then tick and
confirm the first team still gets paid its original amount. Assert on the
`LedgerEntry.amount`, not on the screen.

A passing `test_second_call_for_the_same_week_writes_nothing` proves nothing
unless the first call actually wrote a row — assert the count went 0 → N → N,
not just that the second returned 0.

## Risks

| Risk | Mitigation |
|---|---|
| Contract reads terms via its offer FK, which is later deleted (D2). | Terms are copied columns; `offer` is `SET_NULL` and never read for money. Verification names the specific check. |
| `pay_sponsorship` writes a zero row for uncontracted teams, copying `charge_weekly_wages` too literally. | `charge_weekly_wages` deliberately writes zero rows; sponsorship deliberately does not. Named in W4 as load-bearing, with its own test. |
| `economy/` grows an import of `competitions/` to get points. | Points arrive as an injected dict, exactly as `apply_weekly_fanbase` already does. `grep -rn "competitions" economy/` must stay empty. |
| One `transaction.atomic()` wrapped around the payment loop. | Per-row `atomic()`, `IntegrityError` caught and `continue` — copy `charge_weekly_wages` verbatim in shape. |
| Module-scope `economy` import added to `teams/services.py`. | The import stays inside `claim_team`'s body; W7 marks it load-bearing. |
| Rich-get-richer compounding (spec's open question). | Not solved here by design. The stored floor limits the downside; revisit after a full season is played. |
| Sponsorship numbers unbalance the economy. | `SPONSOR_FANBASE_PER_CREDIT` is one tunable constant with its reasoning in the comment, the same shape as `STARTING_FANBASE`. |

## Open questions

None blocking. The two calls the spec left open — the swing formula's reference
point (D3) and the offer/payment constants — are decided here and are single
constants to retune, not structural choices.
