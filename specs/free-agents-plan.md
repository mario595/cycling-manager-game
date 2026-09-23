# Free agents — Implementation Plan

**Spec:** `specs/free-agents.md` · **Issue:** #29 · **Status:** proposed
**Apps touched:** `riders/`, `transfers/`, `world/`, `api/`, `frontend/`

## Context you need

A "free agent" already exists as a concept: `Rider.team` is nullable
(`riders/models.py`), and `teams.services.claim_team` already sends a whole
roster there every time a team is claimed (`team.riders.update(team=None)`).
Nothing today lists them, signs them, or removes them — they just sit,
invisible.

`transfers/` exists (from #31, merged as PR #93) holding exactly one thing:
`transfers.pricing.market_value_for(rider)`, a pure function of visible
attributes and age, never stored. `transfers/` has an empty `migrations/`
package and no models yet — this ticket gives it its first ones.
`AGENTS.md`'s dependency line is `transfers -> riders`; nothing else. Only
`api/` imports `transfers/`.

The two closest precedents in the codebase, both worth reading before
touching a line here:

- **`staff/services.hire_trainer(team, trainer_id, *, charge=None)`**
  (`staff/services.py`) — locks a pool row, re-checks availability under
  the lock, then runs an injected `charge` callback *before* the state
  change sticks, so a raised `InsufficientFunds` rolls the whole
  transaction back. `staff/` cannot import `economy/`, so the fee is
  charged via a callback the caller (`api/`) supplies. `transfers/`
  cannot import `economy/` either — the same shape applies here.
- **`world.services._release_inactive`** and its helper `_weeks_inactive`
  (`world/services.py`) — counts *`Week` rows that opened in a range*,
  not a wall-clock `timedelta`, so an off-season gap contributes nothing
  to the count. Both this ticket's claim-cooldown and its pool-expiry
  gate need the same in-season week counting, for the same reason
  (`schedule/README.md`, "off-season doesn't count").

Repo rules this plan is bound by (`AGENTS.md`):

- `transfers/` may import only `riders/`. Not `economy/`, `teams/`,
  `schedule/`, `world/`.
- `riders/` may import `core`, `teams` (model-level string FK only).
- Only `world/` and `api/` may import everything; nothing imports them.
- A management command may import outside its app's normal rules **inside
  `handle()`**, same as `reset_riders` and `seed_teams` already do.
- Postgres in dev and prod; tests are pytest
  (`.venv/bin/python -m pytest`).

## Goal

- A manager can see every free agent (a rider with `team = null`), with the
  same visible fields their own roster shows, plus market value.
- A manager can sign a free agent onto their team: pays an upfront fee
  (60% of market value, exact figure calibrated below) plus takes on the
  rider's frozen `weekly_salary`; refused if unaffordable or the roster is
  full.
- A manager can release a rider from their own roster: pays a severance
  fee (30% of market value) unless the rider joined that team as part of
  its most recent claim less than one in-season week ago, in which case
  it's free — and the roster screen always shows this figure per rider,
  including "$0".
- A free agent unattached 8+ in-season weeks **and** priced in the bottom
  20% of the current pool's market value is silently deleted at the
  weekly tick. Nothing else about a rider's supply changes.

## Design decisions (settled — implement these, do not substitute)

1. **One new field carries both "when did this rider join this roster"
   and "when did this rider become unattached": `Rider.joined_team_at`
   and `Rider.unattached_since`, both nullable `DateTimeField`s, both game
   time.** `joined_team_at` is set (to the caller's `at`) every time a
   rider's `team` is set to a non-null value — by `generate_roster`
   (fresh generation), by `claim_team` (new roster), and by this ticket's
   `sign_free_agent`. `unattached_since` is set every time `team` becomes
   null — by `claim_team`'s release of the *old* roster, and by this
   ticket's `release_rider`. **Do not** try to derive either from
   `updated_at`: that's a wall-clock stamp (`core.models.TimeStampedModel`)
   set on *any* save, including unrelated ones (freshness recovery,
   training), so it can't answer "since when has this rider had no team."
2. **The claim-cooldown check reads `joined_team_at` against the team's
   `managed_since`, not a rider-level "released_from" marker.** A rider is
   fee-exempt to release *right now* iff: `team.managed_since` is set,
   `rider.joined_team_at == team.managed_since` (they joined at the exact
   moment of that claim — i.e., they're part of the roster `claim_team`
   generated, not a rider signed in afterward), and fewer than
   `CLAIM_COOLDOWN_WEEKS` (1) in-season weeks have opened between
   `managed_since` and now. This needs no new model — `Team.managed_since`
   already exists (`teams/models.py`) — and correctly excludes a rider the
   manager signed after claiming, who was never "assigned, not chosen."
   **Do not** compare `joined_team_at >= managed_since`: `claim_team`
   assigns every generated rider the *same* `at`, so `==` is exact and
   deliberately excludes a same-week signing (which would get a *different*
   `at`, from `now()` at sign time).
3. **Fee percentages are module constants in `transfers/pricing.py`, not
   configurable per-request.** `SIGNING_FEE_RATE = 0.60`,
   `SEVERANCE_FEE_RATE = 0.30` — both fractions of `market_value_for`.
   Picked to land signing at roughly 7 weeks of an average rider's own
   wages (the README's existing calibration: value ≈ one season ≈ twelve
   weeks of wages, so 60% ≈ seven weeks), a real but survivable hit
   against `STARTING_BALANCE = 500_000`. Severance at half the signing
   rate: real cost, but releasing gives up an asset rather than buying
   one. Round with `transfers.pricing._round_to_nearest_1000`, the same
   helper `market_value_for` already uses — **do not** introduce a second
   rounding convention for fees.
4. **Roster cap is a module constant, `transfers.services.ROSTER_CAP = 30`**
   — comfortably above the 12-rider starting squad, generous enough that a
   manager who signs freely for a whole season doesn't hit it by accident,
   but still a real ceiling. Enforced only at signing time (spec's *Rules
   and edge cases*: a team already over the cap can still race, train,
   release). **Do not** enforce it anywhere else (squad selection, the
   tick) — it is a signing-time gate only.
5. **Expiry thresholds are module constants,
   `transfers.services.EXPIRY_WEEKS = 8` and
   `transfers.services.EXPIRY_VALUE_PERCENTILE = 0.20`.** A free agent
   expires when unattached 8+ in-season weeks *and* their market value
   sits at or below the 20th percentile of every free agent's value at
   that moment (computed fresh each tick — value is never stored, so
   there's nothing to have gone stale). With a small pool this can expire
   nobody in a given week (a pool of 3 has no meaningful 20th percentile
   split below the top rider) — that's correct, not a bug to guard
   against; see *Risks*.
6. **Expiry deletes the `Rider` row outright — it does not archive it.**
   `riders/README.md` already normalizes hard-deleting riders as
   acceptable in this pre-launch world (`reset_riders`'s own precedent).
   A deleted rider's `RaceResult`/`RaceSquadRider` rows cascade-delete
   with them (`riders/models.py`'s existing `on_delete` behaviour on those
   FKs) — the same trade-off `reset_riders` already accepts, and
   acceptable here for the same reason: a free agent who never raced for
   the releasing team leaves no race history worth preserving, and one
   who raced for a *previous* team already has that history attached to
   results, which point at the rider by id and simply lose that id.
   **Do not** add a soft-delete or archive table — nothing in the spec
   asks for one, and it would be new scope.
7. **Signing and releasing both go through `transfers/services.py`, which
   receives a `charge` callback from `api/`, exactly `hire_trainer`'s
   shape.** `transfers/` cannot import `economy/` (rule 1 above), so
   `api/views.py`'s `SignFreeAgentView`/`ReleaseRiderView` build a closure
   that calls `economy.services.charge_trainer_fee`-equivalent (a new,
   analogous one-off debit — see *transfers/services.py* below for the
   exact call) and raises `InsufficientFunds` if the balance won't cover
   it, run *inside* the same `transaction.atomic()` the sign/release
   locks the rider under. **Do not** import `economy/` from
   `transfers/services.py` even indirectly (e.g. via a helper module) —
   that breaks the dependency direction the same way it would in
   `staff/`.
8. **The roster-cap and affordability checks run under the same row lock
   as the rider assignment**, not as pre-checks before a transaction
   opens — same reasoning as `hire_trainer`'s post-lock re-check: two
   concurrent signings must not both succeed past a cap or a balance that
   only covers one of them. **Do not** check affordability/cap with a
   plain `Team.objects.get()` before entering `atomic()`.
9. **Expiry runs once per week transition inside `world.services.tick()`**,
   the same place `_release_inactive` already runs per week, and for the
   same reason: it is world-level cleanup that needs `schedule/`'s week
   counting, which `transfers/` may not import. `world/services.py` gets
   a new private helper, `_expire_free_agents(week)`, called from the
   per-week loop exactly where `_release_inactive` is today. **Do not**
   put expiry logic inside `transfers/services.py` itself trying to count
   weeks — pass the week count in, the same way `_weeks_inactive` is kept
   local to `world/`.

## Data model

**`riders/migrations/00XX_free_agent_tracking.py`** (new) — two fields on
`Rider`:

```python
joined_team_at = models.DateTimeField(
    null=True, blank=True,
    help_text=(
        "Game time this rider's team was last set to a non-null value — "
        "by generation, a team claim, or a free-agent signing. Null for a "
        "rider that has never had joined_team_at stamped (pre-migration "
        "data) or is currently unattached and was never tracked. Used to "
        "gate the free claim-release cooldown (transfers/README.md)."
    ),
)
unattached_since = models.DateTimeField(
    null=True, blank=True,
    help_text=(
        "Game time this rider's team last became null — by a team claim "
        "releasing its old roster, or a manager releasing them to the "
        "free agent pool. Null while on a team. Drives pool expiry "
        "(transfers/README.md)."
    ),
)
```

Both nullable, no default beyond null, no index needed yet (the only
query patterns are `team__isnull=True` filters already unindexed on
`Rider`, plus point lookups by pk under `select_for_update`). A data
migration is **not** needed: every existing free agent (from claims
already run) simply has both fields null, which for `unattached_since`
means "unattached, but we don't know since when" — treated as *never
expiring* (see `transfers/services.py`'s expiry query, which excludes
nulls) rather than guessed at, since inventing a date would be worse than
admitting we don't know.

**`transfers/models.py`** (new file, first models in this app) — no new
models. Value and fees stay pure functions; nothing here needs its own
table. (`transfers/migrations/` already exists as an empty package from
#31 and needs no new migration — the two new fields live on
`riders.Rider`.)

## riders/services.py

New function, called by every path that assigns or clears `Rider.team`:

```python
def mark_team_change(riders: Iterable[Rider], *, team_now, at) -> None:
    """Stamp joined_team_at or unattached_since on every rider in
    `riders` to reflect a team change happening `at` (game time).
    `team_now` is the new team value (a Team, or None for a release) —
    every rider in the iterable is assumed to be changing to this same
    value in this same call, the same assumption claim_team's bulk
    operations already make.
    Does not touch `.team` itself or save it — callers already do that
    (bulk_create, update(), or an individual .save()); this only stamps
    the timing fields, via the same call.
    """
```

Implementation: if `team_now is None`, set `unattached_since = at` (and
leave `joined_team_at` untouched — it still records when they joined the
team they just left, which is now irrelevant but harmless to keep for
debugging); otherwise set `joined_team_at = at` and `unattached_since =
None`. Called with `update_fields=[...]` alongside the existing `.team`
save wherever a team assignment already happens — see *Work items* for
each call site.

## transfers/pricing.py (extend the existing file)

```python
SIGNING_FEE_RATE = 0.60
SEVERANCE_FEE_RATE = 0.30

def signing_fee_for(rider) -> int:
    """SIGNING_FEE_RATE of this rider's market value, rounded the same
    way market_value_for rounds (nearest 1,000)."""

def severance_fee_for(rider) -> int:
    """SEVERANCE_FEE_RATE of this rider's market value, rounded the same
    way."""
```

Both pure, reuse `market_value_for` and `_round_to_nearest_1000`
unchanged.

## transfers/services.py (new file)

```python
ROSTER_CAP = 30
EXPIRY_WEEKS = 8
EXPIRY_VALUE_PERCENTILE = 0.20


class TransferError(Exception):
    """Base class for a free-agent action that cannot proceed."""

class RiderNotAvailable(TransferError):
    """That rider is not a free agent — signed by someone else, or never was."""

class RosterFull(TransferError):
    """Signing would put the team over ROSTER_CAP."""

class InsufficientFunds(TransferError):
    """The team cannot afford the fee."""

class RiderNotOnRoster(TransferError):
    """That rider is not on the caller's team."""


def free_agents() -> QuerySet[Rider]:
    """Every rider with no team, ordered by name — the pool listing."""


def sign_free_agent(team, rider_id: int, *, at, charge=None) -> Rider:
    """Move a free agent onto `team`, subject to the roster cap and an
    injected `charge(rider, fee)` callback (transfers/ may not import
    economy/ — see Design decision 7). Locks the rider row WITHOUT
    skip_locked (the caller asked for this specific rider — same choice
    hire_trainer makes, staff/README.md), re-checks team_id is still null
    under the lock, then re-checks the roster cap under the same lock
    before running charge(). A raise from charge() rolls back the whole
    transaction — team and ledger stay in step.
    """


def release_rider(team, rider_id: int, *, at, charge=None) -> Rider:
    """Send one of `team`'s riders to the free agent pool. Locks the
    rider row (must belong to `team`, checked under the lock), computes
    whether the claim-cooldown exemption applies (Design decision 2) and
    calls charge(rider, fee) with fee=0 when it does — charge still runs,
    so the caller's ledger-write path is uniform, it just writes a $0
    entry. (No entry at all for $0 is also acceptable — see Work items,
    which one to build.)
    """


def release_cost_for(team, rider) -> int:
    """What release_rider would currently charge for this specific rider
    on this specific team, without changing anything — the number the
    roster screen shows per rider, including 0. Pure read; safe to call
    for every rider on a GET."""
```

`sign_free_agent`/`release_rider` both call
`riders.services.mark_team_change([rider], team_now=..., at=at)` after the
lock and before/alongside the `.save()`, inside the same `atomic()` block
the charge runs in.

**Row locking detail (the part most likely to be got wrong):** lock the
`Rider` row itself (`Rider.objects.select_for_update().get(pk=rider_id)`),
not the `Team` row. Two managers racing to sign the *same* free agent must
serialize on that rider; two managers signing *different* free agents for
the *same* team should not block each other just because they share a
team — the roster-cap re-check reads `Rider.objects.filter(team=team).count()`
fresh under the rider's own lock, which is enough: a cap check racing
itself in the gap between two concurrent signings for the same team can
at worst let the cap be exceeded by the number of concurrent requests
in flight, which for a human-only feature (no AI yet, #30) is an
acceptable, narrow race — note it in *Risks* rather than adding
`select_for_update` on the `Team` row, which would serialize every
transfer action for a team including unrelated ones.

## world/services.py

```python
def _expire_free_agents(week) -> int:
    """Delete every free agent unattached EXPIRY_WEEKS+ in-season weeks
    as of this week boundary, and priced at or below the pool's
    EXPIRY_VALUE_PERCENTILE at that moment. Returns riders deleted.

    Mirrors _release_inactive's shape: counts Week rows via the same
    pattern as _weeks_inactive (unattached_since is a game-time
    DateTimeField, exactly like last_seen_at), and is called once per
    week transition in the same loop. A null unattached_since (pre-
    migration data — Data model, above) is excluded, never treated as
    "unattached since the beginning of time."
    """
```

Called from `tick()`'s `for transition in weeks:` loop, in the same
position `_release_inactive(week)` is called today — after the economy
calls (wages, fanbase, sponsorship), for the same reason: expiring a
rider must not change what this week already charged for them (a rider
who was on a roster this week keeps their wage entry even if, hmm — not
applicable, since expiry only ever touches unattached riders, who are
never charged wages; still, run it after the release-inactive call so
`teams_released` and `agents_expired` reflect the same, most-settled
world state for this week).

`TickRun` gets one new field, `agents_expired = models.PositiveIntegerField(default=0)`,
same shape as `teams_released`. New migration in `world/migrations/`.

## api/serializers.py

```python
class FreeAgentSerializer(RiderSerializer):
    """A free agent as the transfer market needs them: everything
    RiderSerializer already ships (the same visible fields a manager's
    own roster shows), plus the two figures this screen adds."""
    signing_fee = serializers.SerializerMethodField()

    def get_signing_fee(self, instance) -> int:
        return signing_fee_for(instance)


class FreeAgentPoolSerializer(serializers.Serializer):
    riders = FreeAgentSerializer(many=True)


class SignFreeAgentSerializer(serializers.Serializer):
    rider_id = serializers.IntegerField()


class ReleaseRiderSerializer(serializers.Serializer):
    rider_id = serializers.IntegerField()
```

`RiderSerializer` (existing, `api/serializers.py:87`) gets one new field
for the *owner's own roster* view, not the free-agent one: a
`release_cost` `SerializerMethodField` calling
`transfers.services.release_cost_for(team, instance)`. This needs the
requesting team in scope, which `RiderSerializer` doesn't have today.
**No existing call site in this file passes serializer `context`
(checked — `grep -n "context\[" api/serializers.py api/views.py` is
empty)**, so this is the first use of that DRF mechanism here, not a
reuse: `RiderListView.get` passes `context={"team": team}` into
`RosterSerializer(...)`, and DRF propagates `context` automatically to
every nested serializer (`RiderSerializer` via `RosterSerializer.riders`)
— no manual threading needed. `get_release_cost` reads
`self.context.get("team")`.

## api/views.py

```python
class FreeAgentsView(APIView):
    """Every free agent, with signing fee, no team scoping needed — the
    pool is the same for every manager. Same IsAuthenticated default as
    every other view here; requires a team (403 without one), matching
    RiderListView and StaffView's own-team gate, even though the pool
    itself isn't team-scoped, for consistency with how every other
    roster-adjacent screen behaves for a manager with no team."""

    def get(self, request): ...


class SignFreeAgentView(APIView):
    """POST rider_id. 409 for RiderNotAvailable, RosterFull,
    InsufficientFunds — well-formed request, world state refuses it.
    Same status-code split ClaimTeamView and HireTrainerView document."""

    def post(self, request): ...


class ReleaseRiderView(APIView):
    """POST rider_id. 409 for RiderNotOnRoster. No InsufficientFunds
    case — release never fails on affordability, only sign does."""

    def post(self, request): ...
```

`SignFreeAgentView.post`'s `charge` closure:

```python
def charge(rider, fee):
    if fee > 0 and balance_for(team) < fee:
        raise InsufficientFunds("You cannot afford this rider's signing fee.")
    if fee > 0:
        charge_transfer_fee(team, amount=-fee, at=at, description=f"Signed {rider.name}")
```

`economy/services.py` needs one new function, `charge_transfer_fee(team,
*, amount, at, description)` — identical shape to `charge_trainer_fee`
(no `(team, week)` uniqueness constraint; a team may sign/release several
times a season). Add a `Kind` choice, `TRANSFER_FEE = "transfer_fee",
"Transfer fee"`, to `LedgerEntry.Kind` (`economy/models.py`) — new
migration in `economy/migrations/`. **One kind covers both signing and
release**, distinguished by sign (negative for signing, negative for a
severance charge too — severance is still money *out*) and by
`description` ("Signed <name>" vs "Released <name>"); **do not** add a
second `Kind` for severance — it is the same shape of transaction
(a one-off transfer-related debit) and splitting it would be a distinction
the ledger UI has no use for.

## api/urls.py

```python
path("transfers/free-agents/", FreeAgentsView.as_view(), name="free-agents"),
path("transfers/free-agents/sign/", SignFreeAgentView.as_view(), name="sign-free-agent"),
path("transfers/riders/release/", ReleaseRiderView.as_view(), name="release-rider"),
```

Mirrors `staff/trainer/hire/` and `staff/trainer/fire/`'s naming
(action-suffixed paths under the domain).

## frontend/src

**`frontend/src/api.ts`** — extend the existing `Rider` interface with
`release_cost: number` (present on the roster response only — the
`FreeAgent` type below is a separate interface, not a widened `Rider`,
since the fields genuinely differ: no `release_cost`, but a
`signing_fee`):

```typescript
export interface FreeAgent extends Omit<Rider, 'release_cost'> {
  signing_fee: number
}

export async function getFreeAgents(): Promise<{ riders: FreeAgent[] }> {
  const response = await fetch('/api/transfers/free-agents/')
  ...  // same shape as getStaff
}

export async function signFreeAgent(riderId: number): Promise<void> {
  return writeJson('/api/transfers/free-agents/sign/', 'POST', { rider_id: riderId })
}

export async function releaseRider(riderId: number): Promise<void> {
  return writeJson('/api/transfers/riders/release/', 'POST', { rider_id: riderId })
}
```

**`frontend/src/useFreeAgents.ts`** (new) — copy `useStaff.ts`'s shape
exactly: 60s poll, `cancelledRef`, `refresh()`. No new pattern to invent.

**`frontend/src/screens/Transfers.tsx`** (new) — structurally
`Staff.tsx` with trainers swapped for riders: speciality filter, a sort
row (name/age/attributes/salary/value/fee), a card grid. Each card is
close to `Roster.tsx`'s `RiderCard` (same attribute bars, same
speciality glyph) with `Sign` replacing the hire button and
`signing_fee` shown where `Staff.tsx` shows `hire_fee`. Disable Sign
with the same `affordable` check `Staff.tsx` already does
(`fee <= balance` — the pool response doesn't carry the caller's
balance today, so `FreeAgentsView` also returns `balance: balance_for(team)`
the same way `StaffView`'s response does, and `FreeAgentPoolSerializer`
gains a `balance` field to match).

**`frontend/src/screens/Roster.tsx`** — add a `Release` button to
`RiderCard` and `RiderPanel`, showing `formatMoney(rider.release_cost)`
next to it (or "Free" when `release_cost === 0` — check with the user's
copy preference at build time, but "$0" per the spec's explicit "$0"
requirement is the safe default; do not silently swap in "Free" as a
different number). Confirm-before-release is a `window.confirm`-style
guard **only if** the codebase already has a confirmation pattern
elsewhere (check `ClaimTeamView`'s frontend flow first) — otherwise skip
it; the spec does not ask for a confirmation step, only for the cost to
be visible before the click.

**`frontend/src/App.tsx`** — add `'/transfers': Transfers` to the route
map and a `<Route path="/transfers" element={<Transfers />} />`, plus a
nav entry wherever `/staff` and `/roster` are listed (check `Nav.tsx` or
wherever the route map doubles as the nav — follow the existing pattern,
don't invent a second source of truth for the nav list).

## Work items

### W1 — `riders/`: add `joined_team_at`/`unattached_since`, stamp them everywhere `team` changes
- `riders/models.py`: the two new fields (Data model, above).
- `riders/migrations/00XX_...py`: generated, no data migration.
- `riders/services.py`: `mark_team_change(riders, *, team_now, at)`.
- `riders/generation.py`: `generate_roster` does **not** call this —
  generation doesn't know the game-time `at` (it's pure, no DB access
  guaranteed — see `riders/README.md`, *Generation*). Instead,
  `teams.services.claim_team` calls `mark_team_change` on the newly
  generated riders right after `bulk_create`, passing its own `at`. This
  keeps `riders/generation.py` free of a new required parameter every
  existing caller (`reset_riders`, tests) would need to pass.
- `teams/services.py`: `claim_team` calls
  `riders.services.mark_team_change(released_riders, team_now=None, at=at)`
  **before** `team.riders.update(team=None)` clears `.team` (need the
  queryset while it still identifies the right rows), then
  `mark_team_change(new_roster, team_now=team, at=at)` after
  `bulk_create`.
- Test: `riders/tests/test_services.py::test_mark_team_change_sets_joined_or_unattached`
  (new file if none exists — check first). `teams/tests/test_services.py`
  gets a new case asserting a freshly claimed team's riders all have
  `joined_team_at == at` and the released riders all have
  `unattached_since == at`.

### W2 — `transfers/`: pricing extensions (fees) and `services.py`
- `transfers/pricing.py`: `SIGNING_FEE_RATE`, `SEVERANCE_FEE_RATE`,
  `signing_fee_for`, `severance_fee_for`.
- `transfers/services.py` (new): `free_agents()`,
  `release_cost_for(team, rider)` first — both pure reads, no locking,
  easiest to get right and test in isolation.
- Test: `transfers/tests/test_pricing.py` — two new cases,
  `test_signing_fee_is_60_percent_of_value`,
  `test_severance_fee_is_30_percent_of_value`, following the file's
  existing style. `transfers/tests/test_services.py` (new) —
  `test_free_agents_returns_only_teamless_riders`,
  `test_release_cost_is_zero_during_claim_cooldown`,
  `test_release_cost_is_full_severance_after_cooldown_expires`,
  `test_release_cost_is_full_severance_for_a_signed_rider`.

### W3 — `transfers/services.py`: `sign_free_agent`/`release_rider`, with locking
- The two write paths, per *transfers/services.py* above. Exceptions:
  `RiderNotAvailable`, `RosterFull`, `InsufficientFunds`,
  `RiderNotOnRoster`.
- Test: `transfers/tests/test_services.py` — follow
  `staff/tests/test_services.py::test_charge_not_called_when_trainer_already_taken`'s
  pattern for the lock re-check: no real threading in this repo's test
  suite (checked — `staff/tests/` proves the post-lock re-check
  sequentially, by mutating the row between the lock and the check, not
  with a second thread), so test `sign_free_agent`'s "already signed"
  path the same way — set `rider.team` directly before calling
  `sign_free_agent`, assert `RiderNotAvailable`. Also
  `test_sign_free_agent_refuses_over_cap`,
  `test_sign_free_agent_raises_from_charge_and_rolls_back` (assert the
  rider's `.team` is still null and no `mark_team_change` stamp survived
  after a raised `InsufficientFunds`), `test_release_rider_refuses_a_rider_not_on_the_team`.
- **Load-bearing:** the raised-charge rollback test — this is the one
  place a bug would silently create money-losing or free riders.

### W4 — `economy/`: `charge_transfer_fee` and the new ledger kind
- `economy/models.py`: `TRANSFER_FEE` kind choice, migration.
- `economy/services.py`: `charge_transfer_fee`, copy `charge_trainer_fee`
  exactly (no per-week uniqueness).
- Test: `economy/tests/test_services.py::test_charge_transfer_fee_writes_a_debit`.

### W5 — `api/`: serializers, views, urls
- `api/serializers.py`: `FreeAgentSerializer`, `FreeAgentPoolSerializer`,
  `SignFreeAgentSerializer`, `ReleaseRiderSerializer`; add
  `release_cost` to `RiderSerializer` via context.
- `api/views.py`: `FreeAgentsView`, `SignFreeAgentView`,
  `ReleaseRiderView`; thread `charge` closures per *api/views.py* above.
- `api/urls.py`: the three new paths, plus the three new view imports.
- Test: `api/tests.py` — `test_free_agents_view_lists_teamless_riders`,
  `test_sign_free_agent_debits_the_fee_and_assigns_the_rider`,
  `test_sign_free_agent_409s_when_unaffordable`,
  `test_release_rider_is_free_within_claim_cooldown`,
  `test_release_rider_charges_severance_after_cooldown`,
  `test_roster_view_reports_release_cost_per_rider`.

### W6 — `world/`: `_expire_free_agents`, wired into `tick()`
- `world/models.py`: `TickRun.agents_expired`, migration.
- `world/services.py`: `_expire_free_agents(week)`, called from the
  per-week loop.
- Test: `world/tests/test_services.py` —
  `test_tick_expires_low_value_long_unattached_riders`,
  `test_tick_does_not_expire_a_high_value_unattached_rider`,
  `test_tick_does_not_expire_a_recently_unattached_rider`,
  `test_tick_never_expires_a_rider_with_null_unattached_since`.
- **Load-bearing:** the null-`unattached_since` test — pre-migration free
  agents must not be silently mass-deleted on the next tick.

### W7 — `frontend/`: Transfers screen, Roster release button
- `frontend/src/api.ts`: the three new functions, `FreeAgent` type,
  `release_cost` on `Rider`.
- `frontend/src/useFreeAgents.ts` (new).
- `frontend/src/screens/Transfers.tsx` (new), `Transfers.test.tsx`
  mirroring `Staff.test.tsx`'s structure.
- `frontend/src/screens/Roster.tsx`: release button + cost display;
  `Roster.test.tsx`'s mocked `riders`/`useRoster` return value
  (`squadValue: 135000` and a `riders` array, around line 78) needs a
  `release_cost` field added to each mocked rider — mirror how
  `market_value`/`weekly_salary` are already present in that mock.
- `frontend/src/App.tsx` / nav: new route.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7.

W1 first because every later write path (`sign_free_agent`,
`release_rider`, `claim_team`'s own change) depends on
`mark_team_change` existing and being correct — get the timing-field
semantics right in isolation before building fee logic on top of them.
W2 before W3: pure reads (`free_agents`, `release_cost_for`) are testable
without transactions or locking, so prove the cooldown/percentile math
before adding concurrency. W3 before W4: the service functions can be
tested with a fake `charge` callable, so the real `economy/` wiring
doesn't block proving the locking is correct. W4 before W5: `api/` needs
`charge_transfer_fee` to exist to close its closures. W6 (world/tick) can
technically move earlier (it only depends on W1's `unattached_since`), but
is sequenced after the human-facing sign/release flow exists, so manual
verification (below) can create a realistic aged pool to test expiry
against rather than hand-crafting `unattached_since` values in a shell.
W7 last, standard for this repo (backend proven and green before frontend
work starts).

Commit at the end of each work item — every one leaves
`.venv/bin/python -m pytest` green.

## Documentation update (required)

- **`transfers/README.md`**: add a section on the market itself — free
  agents, signing, releasing, the cooldown, expiry — alongside the
  existing market-value section. Update the app's one-line description
  in `AGENTS.md`'s table (drop "no models yet"; it now has migrations).
  Update *What `transfers/` may import* if anything changed (it
  shouldn't have — still just `riders/`).
- **`riders/README.md`**: document `joined_team_at`/`unattached_since`
  under a new subsection near *Salary*, following that section's style —
  what it's for, who writes it, what reads it (`transfers/`, `world/`).
- **`world/README.md`**: add `_expire_free_agents` to the tick's
  documented steps, alongside `_release_inactive`.
- **`economy/README.md`**: add `TRANSFER_FEE` to the documented `Kind`
  list.
- **`AGENTS.md`**: update the `transfers/` row's description; no
  dependency-graph change.
- Delete `specs/free-agents.md` and `specs/free-agents-plan.md` once
  merged, per `AGENTS.md`'s *Closing a ticket*.

## Verification

1. `.venv/bin/python -m pytest` green throughout, coverage floor held
   (`.github/workflows/ci.yml`'s 85%).
2. Manual, in this worktree's dev server
   (`config/worktree.py` for this checkout's port/db):
   - `seed_user`, `seed_teams --claim-for test@mail.com`,
     `seed_trainers`, `load_season` per `AGENTS.md`'s order.
   - Claim a *second* team by hand (or via a second account) to generate
     a fresh released roster — confirms the pool is non-empty.
   - Visit `/transfers`: confirm every teamless rider appears with a
     signing fee, sign one, confirm it disappears from the pool and
     appears on `/roster` with the fee debited on `/finances`.
   - On `/roster`, confirm every rider shows a release cost; release a
     rider inherited from the original claim within the same session —
     confirm $0 charged; release the just-signed rider — confirm full
     severance charged.
   - `mock_clock set`/`tick` forward 1 in-season week, re-check the
     originally-claimed roster's release costs now show full severance
     (cooldown expired).
3. **The likeliest failure mode is the claim-cooldown exemption silently
   applying to the wrong riders** — e.g. a signed rider mistakenly
   getting a free release, or an inherited rider being charged when they
   shouldn't be. `test_release_cost_is_full_severance_for_a_signed_rider`
   (W2) and the manual step above (sign, then immediately try to release
   for free) are what actually catch this — a coverage-satisfying test
   that never signs a rider mid-cooldown-window would pass without
   proving the exemption is scoped correctly.
4. **Second likeliest: the raised-`InsufficientFunds` rollback leaking a
   half-applied state** — a rider whose `.team` moved but whose
   `mark_team_change` stamp didn't, or vice versa. W3's
   `test_sign_free_agent_raises_from_charge_and_rolls_back` is the
   specific check; confirm by reading its assertions rather than trusting
   it exists.

## Risks

| Risk | Mitigation |
|---|---|
| Roster-cap check can be exceeded by concurrent signings for the same team (Design decision 8's accepted race) | Acceptable for a human-only feature with no AI bidder (#30) creating real concurrency pressure; revisit if #30 introduces bulk AI signing. |
| Expiry deletes riders permanently, cascading their race history | Matches `reset_riders`'s existing precedent (`riders/README.md`); only ever touches long-unattached, low-value riders. |
| A rider signed and released the same week churns the ledger with two fee entries in one week | Correct per spec — no rule against re-signing; note if this shows up as noisy in the Finances screen, but not a defect. |
| `RiderSerializer` gaining a context-dependent `release_cost` field | Low risk in practice — `RiderSerializer` has exactly one call site today (`RosterSerializer`, `api/serializers.py:122`, itself only built by `RiderListView`, which already has `team` in scope). Still pass `team` via serializer `context` rather than a positional arg, and make `release_cost` degrade to `None` if `context` lacks `team`, so a future second call site fails a test rather than 500ing in production. |
| Pool expiry's percentile is computed over a possibly-tiny pool (early game, few free agents) | Deliberate (Design decision 5) — a pool of 1-2 riders simply won't have a meaningful bottom 20%, so nobody expires that week; not a bug. |

## Open questions

None — every open point from the spec was settled in scoping, and the
remaining technical choices (fee percentages, roster cap, expiry
thresholds) are tuning constants this plan sets directly, per the spec's
own framing of them as implementation details.
