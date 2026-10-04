# Insolvency: act or lose the team — Implementation Plan

**Spec:** `specs/insolvency-ladder.md` · **Issue:** #27 · **Status:** proposed
**Apps touched:** `economy/`, `transfers/`, `world/`, `api/`, `frontend/` (and docs in `teams/`)

## Context you need

A team's balance is never stored: it is `Sum(LedgerEntry.amount)`
(`economy.services.balance_for`, `economy/README.md`, *The ledger is
append-only*). The weekly money moves all happen inside `world.services.tick()`'s
`for transition in weeks:` loop, one crossed `Week` at a time and in this order:
training, `charge_weekly_wages`, `charge_trainer_salaries`,
`charge_development_squad_costs`, youth intake, fanbase, `pay_merchandise`,
`pay_sponsorship`, then `_release_inactive` and `_expire_free_agents`. "Payday" in
the spec is the end of that money block for one week. Today a negative balance is
only flagged on the Finances screen ("nothing is blocked yet").

Every spending action already refuses when the balance cannot cover it, and the
check lives in **`api/views.py`**, not in the services, because `transfers/`,
`staff/` and `riders/` may not import `economy/` (`AGENTS.md`):
`SignFreeAgentView`, `PlaceBidView`, `HireTrainerView`, and `_squad_charge`
(used by `OpenDevelopmentSquadView` and `ChangeDevelopmentSquadLevelView`). The
embargo goes in the same place.

Losing a team already exists: `teams.services.release_team(team, reason=..., at=...)`
(#62), and `ManagerialSpell.Reason.INSOLVENCY` **already exists** in
`teams/models.py`. No `teams/` migration is needed. `MeView` already reports an
unacknowledged spell as `lost_team` with `reason` = `get_reason_display()`
("Team insolvent"), and `ClaimTeam.tsx` already shows it. Inactivity (#63) is the
template for a tick step that releases teams: see `world.services._release_inactive`.

Auctions (`transfers/README.md`, *Auctions*) last `AUCTION_DURATION` (3 days),
and `world._resolve_expired_auctions` resolves them every tick through
`resolve_auction`. That function **cancels** an auction whose rider is no longer
on the seller's roster. A forced sale deliberately takes the rider off the roster
first, so `resolve_auction` needs a forced branch. `withdraw_bids(team, *, at)`
already exists (#30) and is reused unchanged. The AI (`world/ai_market.py`) bids
the reserve on any open, unbid listing whose seller is managed, so forced listings
get AI buyers with no change.

Rules this work is bound by: the dependency graph in `AGENTS.md`
(`transfers -> riders` only; `economy -> core, teams, riders, schedule`; `world`
and `api` orchestrate); per-row `transaction.atomic()` with `IntegrityError`
caught for every weekly write (never one atomic around the loop); and `$`-prefixed
money in the UI.

## Goal

- After each week's payday, every **managed** team with a negative balance has an
  open insolvency case. While the case is open the team is embargoed: no signing,
  no bidding, no hiring, and no opening or upgrading a squad. When the case opens,
  the team's live bids are withdrawn.
- Each case carries a strike count: consecutive paydays with a non-zero weekly
  shortfall. At four strikes the team is released with reason `insolvency`. A
  payday with zero shortfall resets the count to 0, and a payday with a balance
  of 0 or more closes the case.
- An insolvent team can force-sell a rider. The rider leaves the roster
  immediately and is auctioned with no severance; an unsold rider becomes a free
  agent.
- The Dashboard, Finances and Roster screens show the status, the target, how
  much has been cut so far, and the deadline. Forced listings are labelled in the
  market.

## Design decisions (settled — implement these, do not substitute)

**1. State is a weekly assessment row, not a flag on `Team`.** The new model is
`economy.SolvencyCheck`, with one row per (team, week) assessed. "Is this team
insolvent now?" is derived as: *the latest check in the current managerial spell
has `balance < 0`*. Do **not** add `is_insolvent` or `insolvent_since` to `Team`.
A cached flag drifts from the ledger the same way a cached balance would
(`economy/README.md`). It would also force `teams/` to know about insolvency and
need an explicit reset in `claim_team`.

**2. "Current spell" is what makes a claim clear insolvency.** Only checks with
`occurred_at >= team.managed_since` count. A claimed team's old checks fall out
of scope with no write in `claim_team`, which matches the spec's "a claim clears
any insolvency" without touching `teams/`. A team with `managed_since IS NULL`
(claimed before #62) counts every check. The assessment also **skips** a team
whose `managed_since > week.starts_at`: a catch-up tick crossing a boundary that
predates the claim must not judge the new manager on it.

**3. Rows are written only when they matter.** A check row is written for a
managed team whose balance is negative after payday, **or** whose current-spell
latest check is negative (the recovery row that closes the case). A solvent team
with no open case gets no row. This keeps the table to the insolvent handful and
lets "latest row" be the whole state machine.

**4. Strikes, exactly.** At each assessed payday for a team with balance `b` and
live shortfall `s`:

| previous (current spell) | `b` | row written | `strikes` |
|---|---|---|---|
| none / `balance >= 0` | `>= 0` | none | — |
| none / `balance >= 0` | `< 0` | yes — case **opens** | `1 if s > 0 else 0` |
| open (`balance < 0`) | `< 0` | yes | `prev.strikes + 1 if s > 0 else 0` |
| open | `>= 0` | yes — case **closes** | `0` |

The team is **lost** when a written row has `strikes >= INSOLVENCY_LOSS_STRIKES`
(4). That is the fourth consecutive insolvent payday with the target unmet,
counting the payday that opened the case. **Load-bearing:** `s` is computed at
assessment time from the roster *as it stands*, not from the last wage row. A
rider force-listed mid-week has already left the roster, so payroll no longer
includes them.

**5. Shortfall is regular outgoings minus regular income, floored at 0.**
- Outgoings: `payroll_for(team)` + trainer weekly salary + development squad
  weekly cost.
- Income: merchandise (`fanbase_for(team) // MERCHANDISE_FANBASE_PER_CREDIT`)
  + the active contract's `weekly_base` for the season (0 without a contract).
- Prize money is **excluded**: it is irregular, and counting it would make the
  target swing with one race.
- The sponsor term is the **base**, not this week's performance-adjusted
  payment. That is the "promised base" in the spec.

`economy/` may not read `staff/` or `riders.development_squad` prices, so the
trainer salary and squad cost arrive as plain dicts, in the same inversion
`charge_trainer_salaries` and `charge_development_squad_costs` already use. The
tick passes the maps it already builds. The API builds them for one team.

**6. The embargo is enforced in `api/`, next to the existing affordability
checks**, through one helper. The services stay ignorant of insolvency. The
blocked views are `SignFreeAgentView`, `PlaceBidView`, `HireTrainerView`,
`OpenDevelopmentSquadView` and `ChangeDevelopmentSquadLevelView`, each returning
**409** with one shared message (`EMBARGO_MESSAGE`). **Not** blocked:
`SignOfferView` (adding income is a lever), `FireTrainerView`,
`CloseDevelopmentSquadView`, `ReleaseRiderView` and `ListForAuctionView`.
Ordinary release and voluntary listing stay available, so the manager is never
locked out of a lever. Do not add the check inside `sign_free_agent` /
`hire_trainer` / `open_squad`, because those apps may not import `economy/`.

**7. A forced sale puts the rider in limbo: `team = NULL`, with an open
`Auction` where `forced = True`.**
- Taking the rider off the team at once is what stops the wage, since
  `charge_weekly_wages` sums by `team`, and it removes them from every roster
  query with no other change.
- A limbo rider must **not** be a signable free agent while the auction runs.
  `free_agents()` excludes riders with an open forced auction, and
  `sign_free_agent` refuses them under its lock.
- Rejected alternative: keeping the rider on the roster and excluding them from
  payroll. Every roster-shaped query (wages, squads, training, the AI's roster
  reads) would need the same exclusion, and one that forgot would charge or race
  a rider the manager has already given up.

**8. `resolve_auction` gets a forced branch, and only that changes.**
- For a forced auction the "rider still available" check is
  `rider.team_id is None and rider.retired_at is None`, instead of
  `rider.team_id == seller_team_id`.
- **Sold:** the buyer is charged, the seller (the insolvent team) is paid, and
  the rider moves to the buyer, exactly as today.
- **Unsold** (no bid, or the winner at `ROSTER_CAP`): status `UNSOLD` with no
  rider write. The rider is already `team = NULL`, and once the auction stops
  being `OPEN` they are an ordinary free agent.
- No severance is charged anywhere on this path.

**9. Forcing a rider who already has an open voluntary auction converts that
auction.** The existing row gets `forced = True`, keeping its reserve, deadline
and bids, and the rider moves to limbo. Do not cancel it and create a second one:
`one_open_auction_per_rider` forbids two open rows, and throwing away live bids
would cost the seller.

**10. The roster floor is `FORCED_SALE_ROSTER_FLOOR = 4` in `transfers/`.** It
equals `racing.models.SQUAD_SIZE`, but `transfers/` may not import `racing/`, so
the number is duplicated and a test pins the equality. A forced sale is refused
(`RosterAtFloor`) when the roster count is `<= FORCED_SALE_ROSTER_FLOOR`. The
count runs **after locking every roster row of the team** (ordered by pk). Two
concurrent forced sales must not both pass at five riders and leave three. See
the code under `transfers/services.py`.

**11. Live bids are withdrawn by `world/` when a case opens**, by calling the
existing `transfers.services.withdraw_bids(team, at=week.starts_at)`. Only on
**opening**, not on every insolvent payday: the embargo stops new bids, so after
opening there are none to withdraw.

**12. The assessment runs once per crossed week, after `pay_sponsorship` and
before `_release_inactive`.** Releases happen in `world/`, after the economy call
returns, through `release_team(..., reason=ManagerialSpell.Reason.INSOLVENCY,
at=week.starts_at)`. `release_team` returns `None` for an already-released team,
so the inactivity step after it is harmless. A team lost in week 1 of a three-week
catch-up is unmanaged by week 2's assessment and is skipped.

**13. Off-season and season boundaries need nothing special.** No `Week` opens
off-season, so there is no payday and no assessment. Checks persist, so strikes
continue at the next season's first payday. The deadline counts `Week` rows only,
like inactivity does.

**14. The deadline shown is derived, not stored.** `paydays_left` is
`INSOLVENCY_LOSS_STRIKES - strikes` while the **live** shortfall is above 0, and
`None` when it is 0 (the target is met for now). `deadline` is the `starts_at` of
the `paydays_left`-th `Week` after the latest check's week, or `None` if that
`Week` is not declared yet; the UI then says "in N paydays".

**15. "Cut so far"** is `max(0, check.shortfall - live_shortfall)`, where
`check.shortfall` is the shortfall stored at the last payday. It is shown
alongside the live shortfall. It resets at each payday; that is honest, because
each payday restates the target.

## Data model

### `economy.SolvencyCheck` (new) — `economy/models.py`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `team` | `ForeignKey("teams.Team", CASCADE, related_name="solvency_checks")` | no | — | |
| `week` | `ForeignKey("schedule.Week", CASCADE, related_name="solvency_checks")` | no | — | String reference: no `schedule` import, same as `SalaryReviewReport.season`. CASCADE because a check means nothing without its week (weeks are only deleted by `load_season --replace` before a season starts, when no check can exist). |
| `occurred_at` | `DateTimeField` | no | — | Game time = `week.starts_at`. What decision 2's "current spell" filter compares against. |
| `balance` | `BigIntegerField` | no | — | Balance at assessment. `< 0` ⇒ case open. |
| `shortfall` | `PositiveIntegerField` | no | — | Weekly shortfall at assessment (decision 5), floored at 0. |
| `strikes` | `PositiveSmallIntegerField` | no | `0` | Decision 4. |

Inherits `created_at`/`updated_at` from `core.models.TimeStampedModel`.
`Meta.ordering = ["-occurred_at", "-pk"]`. Constraint
`UniqueConstraint(fields=["team", "week"], name="one_solvency_check_per_team_per_week")`,
the second line of defence behind `WeekTransition`, as with every weekly row.
Index `Index(fields=["team", "-occurred_at"], name="solvency_team_recent_idx")`.

Migration: `economy/migrations/0013_solvencycheck.py` (`makemigrations economy`).
The current latest is `0012_gc_prize_money`. If master has moved by the time you
build this, take the next free number and regenerate. Never hand-edit a merge.

### `transfers.Auction.forced` (new field) — `transfers/models.py`

`forced = models.BooleanField(default=False, help_text="A forced sale under insolvency (#27): the rider left the seller's roster at listing, and an unsold auction makes them a free agent.")`

Migration: `transfers/migrations/0003_auction_forced.py`. Existing rows default
to `False`, which is correct: every auction so far was voluntary.

No `teams/` change (`Reason.INSOLVENCY` already exists).

## `economy/solvency.py` (new)

A new module rather than more of `economy/services.py` (735 lines). It imports
from `.models` and `.services` (for `balance_for`, `fanbase_for`, `payroll_for`,
`active_contract`), and `schedule.models.Week` for the deadline
(`economy -> schedule` is allowed).

```python
#: Consecutive paydays with the target unmet before the team is lost, counting
#: the payday that opened the case (spec: "the fourth consecutive insolvent payday").
INSOLVENCY_LOSS_STRIKES = 4

EMBARGO_MESSAGE = (
    "Your team is insolvent. Signing, bidding, hiring and squad upgrades are "
    "blocked until your balance is back to zero or above."
)

@dataclass(frozen=True)
class SolvencyOutcome:
    opened: list[int]   # team pks whose case opened at this payday
    lost: list[int]     # team pks whose strikes reached INSOLVENCY_LOSS_STRIKES
    written: int        # rows written

@dataclass(frozen=True)
class SolvencyStatus:
    insolvent: bool
    balance: int
    shortfall: int          # live
    target: int             # shortfall at the last payday (check.shortfall)
    cut_so_far: int         # max(0, target - shortfall)
    outgoings: int
    income: int
    strikes: int
    paydays_left: int | None
    deadline: datetime | None

def regular_income(team, season) -> int: ...
def weekly_shortfall(team, season, *, trainer_salary: int, squad_cost: int) -> int: ...
def open_check(team) -> SolvencyCheck | None:
    """Latest check in the current spell if its balance is negative, else None."""
def is_embargoed(team) -> bool:
    return open_check(team) is not None
def assess_solvency(week, *, salary_by_team: dict[int, int],
                    squad_cost_by_team: dict[int, int]) -> SolvencyOutcome: ...
def solvency_status(team, season, *, trainer_salary: int, squad_cost: int) -> SolvencyStatus: ...
```

`season` may be `None` (off-season reads from the API). `regular_income` then
counts merchandise only.

`open_check` — the current-spell filter (decision 2):

```python
def _current_spell_checks(team):
    checks = SolvencyCheck.objects.filter(team=team)
    if team.managed_since is not None:
        checks = checks.filter(occurred_at__gte=team.managed_since)
    return checks          # model ordering: newest first

def open_check(team):
    latest = _current_spell_checks(team).first()
    return latest if latest is not None and latest.balance < 0 else None
```

`assess_solvency` — the per-row shape every weekly writer here uses:

```python
def assess_solvency(week, *, salary_by_team, squad_cost_by_team):
    opened, lost, written = [], [], 0
    managed = Team.objects.filter(manager__isnull=False).order_by("pk")
    for team in managed:
        if team.managed_since is not None and team.managed_since > week.starts_at:
            continue                                   # decision 2: claimed after this boundary
        balance = balance_for(team)
        previous = open_check(team)
        if balance >= 0 and previous is None:
            continue                                   # decision 3: nothing to record
        shortfall = weekly_shortfall(
            team, week.season,
            trainer_salary=salary_by_team.get(team.pk, 0),
            squad_cost=squad_cost_by_team.get(team.pk, 0),
        )
        if balance >= 0:
            strikes = 0                                # case closes
        elif shortfall == 0:
            strikes = 0
        else:
            strikes = (previous.strikes if previous else 0) + 1
        with transaction.atomic():
            try:
                SolvencyCheck.objects.create(
                    team=team, week=week, occurred_at=week.starts_at,
                    balance=balance, shortfall=shortfall, strikes=strikes,
                )
            except IntegrityError:
                continue                               # already assessed this week
        written += 1
        if balance < 0 and previous is None:
            opened.append(team.pk)
        if strikes >= INSOLVENCY_LOSS_STRIKES:
            lost.append(team.pk)
    return SolvencyOutcome(opened=opened, lost=lost, written=written)
```

**`previous` must be read before the create.** Reading it after would see the row
just written. The `continue` on `IntegrityError` also skips the `opened`/`lost`
bookkeeping, which is what makes a re-run tick release nobody twice.

`solvency_status` builds the read model for `api/`. If `open_check(team)` is
`None`, it returns `insolvent=False` with `balance`, live `shortfall`,
`outgoings` and `income` filled in, and zeros/`None` for the rest. Otherwise it
applies decisions 14 and 15:

```python
upcoming = list(
    Week.objects.filter(starts_at__gt=check.occurred_at)
    .order_by("starts_at").values_list("starts_at", flat=True)[:paydays_left]
)
deadline = upcoming[paydays_left - 1] if len(upcoming) >= paydays_left else None
```

## `transfers/services.py`

```python
#: A forced sale may not take the roster below what a team needs to race.
#: Equal to racing.models.SQUAD_SIZE, duplicated because transfers/ may not
#: import racing/ (AGENTS.md); transfers/tests pins the equality.
FORCED_SALE_ROSTER_FLOOR = 4

class RosterAtFloor(TransferError):
    """A forced sale would leave fewer riders than a team needs to race."""

def force_list_for_auction(team, rider_id: int, *, at) -> Auction: ...
```

`force_list_for_auction`: the lock order and the floor count are the subtle
part:

```python
with transaction.atomic():
    # Lock the whole roster, pk order, BEFORE counting: two concurrent forced
    # sales from five riders must not both see five (decision 10). pk order
    # means two calls for the same team queue rather than deadlock.
    roster = list(Rider.objects.select_for_update().filter(team=team).order_by("pk"))
    rider = next((r for r in roster if r.pk == rider_id), None)
    if rider is None:
        raise RiderNotOnRoster("That rider is not on your team.")
    if len(roster) <= FORCED_SALE_ROSTER_FLOOR:
        raise RosterAtFloor(
            f"A team needs at least {FORCED_SALE_ROSTER_FLOOR} riders to race."
        )
    existing = (
        Auction.objects.select_for_update()
        .filter(rider=rider, status=Auction.Status.OPEN).first()
    )
    if existing is not None:                     # decision 9: convert, never duplicate
        existing.forced = True
        existing.save(update_fields=["forced", "updated_at"])
        auction = existing
    else:
        reserve = reserve_price_for(rider)
        auction = Auction.objects.create(
            rider=rider, seller_team=team, forced=True,
            reserve_price=reserve, current_price=reserve,
            min_increment=min_increment_for(reserve),
            deadline=at + AUCTION_DURATION, listed_at=at,
        )
    rider.team = None                            # decision 7: the wage stops now
    mark_team_change([rider], team_now=None, at=at)
    rider.save(update_fields=["team", "updated_at"])
return auction
```

`existing` can only be the team's own listing: the rider is on the team under the
lock, and `resolve_auction`/`cancel_*` are the only other writers.

**`free_agents()`** gains
`.exclude(Exists(Auction.objects.filter(rider=OuterRef("pk"), status=Auction.Status.OPEN, forced=True)))`.

**`sign_free_agent`** adds, under the rider lock and after the
`development_squad_id` check:
`if Auction.objects.filter(rider=rider, status=Auction.Status.OPEN, forced=True).exists(): raise RiderNotAvailable("That rider is being sold.")`.

**`resolve_auction`** replaces the roster check (decision 8):

```python
if auction.forced:
    available = rider.team_id is None and rider.retired_at is None
else:
    available = rider.team_id == auction.seller_team_id
if not available:
    ...  # CANCELLED, unchanged
```

Nothing else in it changes. A forced auction with no bid, or a winner at the cap,
falls through to the existing `UNSOLD` branches, which never write the rider.

`withdraw_bids` docstring: it no longer runs "on claim" only. Add "and when a
team becomes insolvent (#27)". No behaviour change.

## `world/services.py`

Import `assess_solvency` from `economy.solvency` and `withdraw_bids` from
`transfers.services`, and add `_settle_solvency(week, salary_by_team, squad_cost_by_team) -> tuple[int, int, str]`.
Like `_release_inactive`, it returns counts plus error text, because `TickRun`
does not exist yet at this point in the loop:

```python
def _settle_solvency(week, *, salary_by_team, squad_cost_by_team):
    outcome = assess_solvency(
        week, salary_by_team=salary_by_team,
        squad_cost_by_team={pk: cost for pk, (cost, _name) in squad_cost_by_team.items()},
    )
    error = ""
    for team_pk in outcome.opened:
        try:
            withdraw_bids(Team.objects.get(pk=team_pk), at=week.starts_at)
        except Exception:
            error += f"withdraw bids, team {team_pk}:\n{traceback.format_exc()}\n"
    released = 0
    for team_pk in outcome.lost:
        try:
            if release_team(Team.objects.get(pk=team_pk),
                            reason=ManagerialSpell.Reason.INSOLVENCY,
                            at=week.starts_at) is not None:
                released += 1
        except Exception:
            error += f"insolvency release, team {team_pk}:\n{traceback.format_exc()}\n"
    return outcome.written, released, error
```

In `tick()`'s loop, call it right after `pay_sponsorship(...)` and before
`_release_inactive(week)` (decision 12). Accumulate the counts into the new
`TickRun` fields and the error into the existing `error` concatenation.

### `world/models.py` — `TickRun`

Two counters, `solvency_checks = PositiveIntegerField(default=0)` and
`teams_lost_to_insolvency = PositiveIntegerField(default=0)`, next to
`teams_released`. Migration `world/migrations/0020_tickrun_solvency.py` (the next
free number). Keep `teams_released` meaning inactivity only, so the two causes
stay distinguishable in the admin.

## `api/`

### `api/views.py`

- **`_regular_costs(team) -> tuple[int, int]`** returns `(trainer_salary,
  squad_cost)` for one team: `staff.pricing.weekly_salary(trainer)` if
  `trainer_for(team)` else 0, and `riders.development_squad.weekly_cost(squad.level)`
  if `squad_for(team)` else 0. All of these are already imported in `views.py`
  apart from `weekly_salary` and `weekly_cost`.
- **`_embargo_response(team) -> Response | None`** returns
  `Response({"detail": EMBARGO_MESSAGE}, status=409)` if `is_embargoed(team)`,
  else `None`. Call it at the top of each blocked view's `post`, right after the
  `team is None` check and **before** serializer validation, so the refusal
  doesn't depend on payload shape: `SignFreeAgentView`, `PlaceBidView`,
  `HireTrainerView`, `OpenDevelopmentSquadView`, `ChangeDevelopmentSquadLevelView`.
- **`SolvencyView`** (new), `GET /api/economy/solvency/`. Returns
  `SolvencySerializer` built from `solvency_status(team, current_position(now()).season,
  trainer_salary=..., squad_cost=...)` plus
  `roster_floor=FORCED_SALE_ROSTER_FLOOR` and `roster_size=team.riders.count()`.
  A user with no team gets `insolvent: false` with zeros, matching
  `FinancesView`'s calm empty state.
- **`ForceSellView`** (new), `POST /api/transfers/auctions/force/` with body
  `{rider_id}`, validated by the existing `ListForAuctionSerializer`. Returns 403
  with no team, and 409 `"Only an insolvent team can force a sale."` when
  `not is_embargoed(team)`. Otherwise it calls `force_list_for_auction(team,
  rider_id, at=now())`, maps `RiderNotOnRoster` and `RosterAtFloor` to 409, and
  returns 204.
- **`AuctionMarketView`**: add `"forced": auction.forced` to each auction dict.

### `api/serializers.py`

- `AuctionSerializer.forced = serializers.BooleanField()`.
- `SolvencySerializer` has every `SolvencyStatus` field: `deadline` as
  `DateTimeField(allow_null=True)`, `paydays_left` as
  `IntegerField(allow_null=True)`, plus `roster_floor` and `roster_size`.

### `api/urls.py`

`path("economy/solvency/", SolvencyView.as_view(), name="solvency")` and
`path("transfers/auctions/force/", ForceSellView.as_view(), name="force-sell")`.
**Place the force route before `transfers/auctions/<int:auction_id>/bid/`.**
`<int:...>` cannot match `force`, but `api/README.md`, *URL ordering*, asks that
literal routes come first.

## `frontend/`

- **`src/api.ts`**: `forced: boolean` on `AuctionListing`; a `Solvency` interface
  mirroring the serializer; `getSolvency()` (same error shape as `getFinances`);
  `forceSell(riderId)` → `writeJson('/api/transfers/auctions/force/', 'POST', { rider_id })`.
- **`src/useSolvency.ts`** (new): a copy of `useFinances`'s lifecycle (60 s poll,
  `cancelledRef`, `refresh`).
- **`src/components/SolvencyBanner.tsx`** (new): renders nothing when
  `!insolvent`. Otherwise it renders a `Card` with a `color.negative` border, and
  the wording depends on the live shortfall:
  - `shortfall > 0`: "Your team is insolvent. Cut $X of weekly spending by <date>
    or you will lose the team." Use "within N paydays" when `deadline` is null.
    Below that, "Cut so far $A of $T".
  - `shortfall === 0`: "Your team is insolvent but recovering. Spending is
    blocked until your balance is back to zero or above."
  - Always: one line listing the levers (forced sales on the Roster, firing the
    trainer, closing the squad, signing a sponsor). Money uses `formatMoney`
    (`$`), dates the existing date formatter used by `Calendar`/`countdown`.
- **`Dashboard.tsx`**: `<SolvencyBanner />` directly under `PageHeading`.
- **`Finances.tsx`**: `<SolvencyBanner />` in the same place. The existing
  negative-balance card ("nothing is blocked yet") is shown only when
  `balance < 0 && !insolvent`, with its text changed to "Your balance is
  negative. If it is still negative at payday, your team becomes insolvent."
  This is the mid-week case: a signing that pushes the balance negative before
  any assessment.
- **`Roster.tsx`**: in the rider detail panel, when `solvency.insolvent`, add a
  "Force sale" button beside "List for auction". It asks for confirmation that
  the rider leaves now, is not returned if unsold, and costs no severance, then
  calls `forceSell`. After that it refreshes the roster and solvency. The button
  is disabled with a tooltip when `roster_size <= roster_floor`. On error, show
  the 409 `detail` through the existing `actionError` state.
- **`AuctionCard.tsx`**: a "Forced sale" pill when `auction.forced`, styled like
  `FinalSeasonTag` in `primitives.tsx`.

Embargo refusals on Transfers/Staff/Development squad need no new UI: those
screens already show a 409's `detail`. Check that each one does (W8). If one
swallows it, surface it there.

## Work items

### W1 — `economy/`: `SolvencyCheck` model and migration — done
Add the model (Data model) and `0013_solvencycheck`.
Tests in `economy/tests/test_models.py`:
- `test_solvency_check_unique_per_team_per_week`: a second create for the same
  `(team, week)` raises `IntegrityError`.
- `test_solvency_checks_order_newest_first`.

### W2 — `economy/solvency.py`: shortfall, income, open_check, status — done
Everything except `assess_solvency`. Tests in **new**
`economy/tests/test_solvency.py`:
- `test_shortfall_is_outgoings_minus_income_floored_at_zero`
- `test_income_counts_sponsor_base_not_weekly_payment`: a demanding contract;
  income uses `weekly_base`.
- `test_income_without_season_is_merchandise_only`
- `test_open_check_ignores_checks_before_managed_since`: decision 2; this is
  what makes a claim clear insolvency.
- `test_status_paydays_left_and_deadline`: strikes 1, live shortfall > 0 →
  `paydays_left == 3`, `deadline` = third `Week` after the check.
- `test_status_deadline_none_when_weeks_not_declared`
- `test_status_paydays_left_none_when_live_shortfall_zero`
- `test_cut_so_far_is_target_minus_live_shortfall`

### W3 — `economy/solvency.py`: `assess_solvency`
The decision 4 table, as code. Tests in `economy/tests/test_solvency.py`, one per
row of the table:
- `test_solvent_team_without_case_writes_nothing`
- `test_negative_balance_opens_case_with_one_strike`
- `test_case_opens_with_zero_strikes_when_no_shortfall`
- `test_strikes_accumulate_while_shortfall_open`
- `test_meeting_target_resets_strikes`
- `test_new_breach_after_reset_starts_at_one`: spec In scope 10.
- `test_recovery_row_closes_case`: balance ≥ 0 → row with strikes 0, and
  `is_embargoed` is False afterwards.
- `test_fourth_strike_is_reported_lost`
- `test_unmanaged_teams_are_never_assessed`
- `test_team_claimed_after_boundary_is_skipped`
- `test_reassessing_same_week_writes_and_reports_nothing`: **load-bearing**.
  Call twice; the second call returns `written == 0` and empty `opened`/`lost`.
- `test_forced_listing_counts_before_payday`: a rider moved to `team=None`
  mid-week is excluded from payroll at assessment. This is decision 4's
  load-bearing note.

### W4 — `transfers/`: `Auction.forced`, `force_list_for_auction`, pool and resolve changes
Model field and `0003_auction_forced`, plus the service code above. Tests in
`transfers/tests/test_services.py`:
- `test_force_list_moves_rider_off_roster_and_opens_forced_auction`
- `test_force_list_charges_nothing`: there is no callback at all; assert no
  ledger rows (the test may import economy).
- `test_force_list_refused_at_roster_floor`: a 4-rider team raises `RosterAtFloor`.
- `test_force_list_converts_existing_voluntary_auction`: same pk, bids kept,
  `forced` set.
- `test_force_listed_rider_not_in_free_agent_pool`
- `test_force_listed_rider_cannot_be_signed`
- `test_resolve_forced_sold_pays_seller_and_moves_rider`
- `test_resolve_forced_unsold_leaves_free_agent`: afterwards `free_agents()`
  includes the rider.
- `test_resolve_forced_winner_at_cap_goes_unsold`
- `test_resolve_voluntary_unchanged_when_rider_released`: a regression guard
  for the non-forced branch.
- `test_forced_sale_floor_matches_racing_squad_size`: asserts
  `FORCED_SALE_ROSTER_FLOOR == racing.models.SQUAD_SIZE`.

### W5 — `world/`: the tick step
`TickRun` counters plus migration, `_settle_solvency`, and the call site. Tests
in **new** `world/tests/test_insolvency.py`, driving `tick()` with the mock clock
the way `test_inactivity.py` does:
- `test_tick_opens_case_for_negative_managed_team`
- `test_tick_withdraws_live_bids_when_case_opens`
- `test_tick_releases_team_on_fourth_unmet_payday`: spell `reason == "insolvency"`.
- `test_tick_keeps_team_whose_target_is_met`: shortfall closed after strike 2;
  five more paydays; still managed.
- `test_catch_up_across_four_weeks_releases_once`: one tick crossing four
  weeks; `teams_lost_to_insolvency == 1` and exactly one spell.
- `test_insolvency_runs_before_inactivity`: a team due for both is released
  once, with reason `insolvency`.
- `test_claimed_team_starts_solvent`: release, then claim; the next payday
  writes no check (balance reset), and `is_embargoed` is False immediately after
  the claim.

### W6 — `api/`: embargo, status, force sale
Views, serializers and urls as above. Tests in `api/tests.py`:
- `test_embargo_blocks_signing` / `_bidding` / `_hiring` / `_opening_squad` /
  `_upgrading_squad`: each is a 409 with `EMBARGO_MESSAGE`.
- `test_embargo_allows_sponsor_signing_firing_closing_release_and_listing`
- `test_solvency_view_solvent_shape` and `test_solvency_view_insolvent_shape`
- `test_force_sell_requires_insolvency`
- `test_force_sell_at_floor_is_409`
- `test_force_sell_success_returns_204_and_lowers_payroll`
- `test_auction_market_reports_forced`

### W7 — `frontend/`: api, hook, banner, Dashboard, Finances
Tests:
- **new** `src/components/SolvencyBanner.test.tsx`: hidden when solvent; the
  insolvent wording with a deadline; the "within N paydays" fallback; the
  recovering wording.
- `Finances.test.tsx`: the negative-but-solvent card copy; the card is hidden
  when insolvent.
- `Dashboard.test.tsx`: the banner renders when insolvent.

### W8 — `frontend/`: Roster force sale, AuctionCard tag
Tests:
- `Roster.test.tsx`: the "Force sale" button shows only when insolvent, is
  disabled at the floor, confirms, then calls `forceSell`.
- `AuctionCard.test.tsx`: the forced pill.

Also check that Transfers/Staff/DevelopmentSquad show a 409 `detail` (read the
code). If one doesn't, fix it and add a test there.

### W9 — Docs, spec status, archive
See *Documentation update*.

## Execution order

1. **W1 → W2 → W3.** The state machine first, in pure `economy/` with no tick.
   Every later item reads it, and W3's table tests are the cheapest place to get
   the strike logic right. Commit after each.
2. **W4.** Independent of W1–W3. It can be built in either order, but land it
   before W5 so the tick test can force-list.
3. **W5.** This wires the first two together through the real tick. Run the
   full suite here: the tick change touches every world test.
4. **W6**, then **W7**, then **W8**. API before UI. Run `npm test` and `npm run
   build` in `frontend/` after W7 and W8.
5. **W9**, last, describing what was actually built.

Every item leaves `.venv/bin/python -m pytest` green. Commit per item.

## Documentation update (required, not optional)

- **`economy/README.md`**:
  - Add a new section, *Insolvency (#27)*: `SolvencyCheck` and why it is rows,
    not a flag (decision 1); the current-spell rule (decision 2); the strike
    table (decision 4); the shortfall definition, including why prize money is
    excluded and the sponsor base is used (decision 5); the embargo living in
    `api/` (decision 6).
  - Update *What this app owns*.
  - Replace the *Future work* "Insolvency" bullet with "Unmanaged-team
    insolvency (after #45)" and "Runway projection".
- **`transfers/README.md`**:
  - Add a new section, *Forced sales*: limbo (decision 7), the
    `resolve_auction` forced branch (decision 8), conversion (decision 9), and
    the floor and its duplication (decision 10).
  - Update the *Auctions* `Auction` field list.
  - Note that `withdraw_bids` is also called on insolvency.
  - Drop the *Future work* "Forced sales" bullet.
- **`world/README.md`**:
  - In *How a tick works*, add the solvency step and its position (decision 12).
  - Document the `TickRun` counters.
- **`teams/README.md`**: in *Releasing a team* / *Future work*, #27 now calls
  `release_team` with `INSOLVENCY`.
- **`api/README.md`**: document the two new endpoints, the embargo list (blocked
  and not blocked), and `forced` on the market payload.
- **`frontend/README.md`**: the banner and where it appears, the Roster force
  sale, and the market tag.
- **`AGENTS.md`**: one clause each in the `economy/`, `transfers/` and `world/`
  rows of the domain table.
- **Specs**: set `Status: implemented` in `specs/insolvency-ladder.md` and this
  plan, `git mv` both into `specs/archive/`, and commit with the work.

## Verification

Automated: `.venv/bin/python -m pytest` (coverage floor 85%), and in
`frontend/`, `npm test` and `npm run build`.

End to end, in this worktree, after the standard seeds (`seed_user`,
`seed_teams --claim-for test@mail.com`, `seed_trainers`, `load_season`), with
`GAME_CLOCK_CLASS=world.clocks.MockClock`:

1. `mock_clock set <season start>` and `tick`. The demo team is solvent and the
   Finances screen shows no banner.
2. Drive the demo team negative:
   ```bash
   .venv/bin/python manage.py shell -c "from teams.models import Team; from economy.services import charge_transfer_fee; from world.services import now; t=Team.objects.get(manager__email='test@mail.com'); charge_transfer_fee(t, amount=-600_000, at=now(), description='Test drain')"
   ```
   The Finances screen now shows the *negative-but-solvent* card, not the banner.
3. `mock_clock advance` one week and `tick`. The banner appears on Dashboard and
   Finances with a shortfall and a deadline three paydays out, and signing a free
   agent returns the embargo message.
4. On the Roster, force-sell riders until "Cut so far" reaches the target. The
   banner switches to "recovering". In Transfers the listing carries the
   "Forced sale" pill, and an AI bid appears after the next `tick`.
5. Advance four more weeks and tick each time. The team is still managed.
6. Repeat from a fresh claim, but force-sell nothing. On the fourth payday the
   team is released, and logging in shows the claim screen with "Team insolvent".

**The likeliest failure** is a re-run or catch-up tick double-counting strikes,
or releasing on a stale strike count, so that a team is lost a payday early.
`test_reassessing_same_week_writes_and_reports_nothing` and
`test_catch_up_across_four_weeks_releases_once` catch it. Step 6 confirms it by
hand: count the paydays.

**The second likeliest** is a force-listed rider leaking into the free-agent
pool and being signed while their auction is live.
`test_force_listed_rider_cannot_be_signed` catches that.

## Risks

| Risk | Mitigation |
|---|---|
| Reader stores insolvency on `Team` "for speed" and forgets to clear it on claim, so a new manager inherits an embargo. | Decision 1 forbids it. `test_claimed_team_starts_solvent` fails if the claim does not clear it. |
| `previous` read after the create in `assess_solvency`, so every case looks already open and strikes double. | The code above reads first; `test_negative_balance_opens_case_with_one_strike` fails otherwise. |
| `resolve_auction` keeps its old check, so every forced auction is CANCELLED and the seller never gets paid. | Decision 8; `test_resolve_forced_sold_pays_seller_and_moves_rider`. |
| Roster floor counted before the roster lock; concurrent forced sales drop a team below 4. | Lock-then-count code above. Accepted residual: an ordinary release isn't floored, as today. |
| A new season opens with no sponsor signed: income drops and a recovering team breaches again. | Intended (spec In scope 10). Signing the new season's offer is a lever the embargo does not block. Note it in the economy README. |
| An absent manager is lost in about three weeks, well inside #63's ten. | A decision taken in the spec. Not a defect. |
| Insolvent on purpose to dump riders without severance. | Accepted in the spec. The embargo and the deadline are the price. |
| Migration number collision with a concurrent branch. | Take the next free number at build time and regenerate. Never hand-merge. |

## Open questions

None.
