# Riders — the roster asset

## What this app owns

`Rider` — persisted riders mirroring the race engine's attributes, plus
everything the engine does not know about: speciality, build, age, and a set
of hidden traits. Generation (`generation.py`), the display mapping
(`display.py`), the age curve (`services.py`), the `reset_riders`
management command, a team's **development squad** — which level it runs
at and what that costs (`development_squad.py`) — and **youth intake**
(`youth_intake.py`, #33) — the batches of young riders a squad periodically
receives. Not race-day squads or results (`racing/`), not the race
simulation itself (`race_engine/`).

## Visible vs hidden

Every rider carries two kinds of attribute:

- **Visible**: `speciality`, `nationality`, `height_cm`, `weight_kg`, `age`,
  `freshness`, `weekly_salary`, and the five engine attributes (`climb`,
  `sprint`, `flat`, `resistance`, `positioning`). These are what
  `api.RiderSerializer` and `api.SquadRiderSerializer` ship to the player
  (`weekly_salary` is roster-only — see *Salary*, below). `intake_at` and
  `development_squad` are visible too, but only through their consequence:
  `intake_at` resolves to the `arrived` season/week on the squad screen and
  `development_squad` resolves to the owning team on a rider's profile —
  neither ships as the raw field (see *Youth intake*, below).
- **Hidden**: `potential`, `peak_age`, `decline_rate`, `injury_proneness`,
  `training_affinity`, `recovery_rate`, `growth_debt`. **Never add one of
  these to a serializer.** The whole premise of the hidden-trait design is that the
  player cannot see them — a hidden trait leaking onto a screen is a
  defect, not a convenience for debugging. Look at them in Django admin
  instead.

`potential`, `peak_age` and `decline_rate` are live: `services.py` reads
them every week to grow or decline a rider's attributes, and `age`
advances once per season — see *The age curve*, below.
`training_affinity` is live too: `services.training_deltas` reads it each
week to scale the trainer's focused training
([#36](https://github.com/mario595/cycling-manager/issues/36); see *Weekly
training*, below) — and it is **still never serialized**: the Training
screen ships only the display-scale before/after, never the trait behind
them. `injury_proneness` remains inert, waiting on injuries
([#41](https://github.com/mario595/cycling-manager/issues/41)): the
training pass skips injured riders through `services.is_injured()`, a
placeholder that returns `False` for everyone until #41 gives it a real
answer. `growth_debt` is an implementation detail of the age curve,
not a game concept — see below.

The rule that *every hidden trait must be inferable* — a hidden value with
no observable consequence is an unfair dice roll, not depth — applies from
the point each trait goes live, not before. Growth/decline (#58) and weekly
training (#36) each clear it: `training_affinity`'s only observable
consequence is how quickly a focused trainer's work accumulates, which the
Training screen surfaces. `recovery_rate` is the newest entry: its only
observable consequence is how fast `freshness` — a visible number that moves
every week — climbs back up, so it clears the same bar. #41 must clear it too
when it lands.

**The retirement age (#42) is the one hidden value shipped only as its
consequence.** `peak_age` and `decline_rate` are read together to place a
rider in the 33–38 window, and the API ships *only* the boolean
`final_season` — never the age, never the traits, never a "why". That clears
the inferability rule the same way the others do: a player can watch a
late-peaking rider play on and a fast-declining one go sooner, and read *that*
a rider is in their last season, without ever seeing the number behind it.

## Display scale: stored 1-100, shown 0-10

The five engine attributes are stored 1-100 — the same range the engine
validates and the same range its six bundled courses are balanced against.
**That range never changes.** What the player sees is coarser: `display.
to_display_scale(value)` maps it onto 0-10 with `value // 10` — it floors,
it does not round — and it is the **only** place that mapping happens.
Every serializer that ships an attribute calls it; nothing else should
reimplement it.

This is deliberate lossiness, not a rounding bug: two riders at 71 and 74
both show 7, and a rider is not shown to have reached a level until their
stored value actually gets there (58 shows 5, not 6). The roster cannot
offer a meaningful sort on a raw attribute number, and growth (see *The
age curve*, below) arrives as an occasional visible jump rather than a
number that visibly creeps every week.

**Do not rescale the stored values to make display simpler.** A stored
range change invalidates the verified realism balance across all six
bundled courses (`race_engine/README.md`) and requires re-deriving it —
that cost is exactly why the display scale exists as a read-time mapping
instead.

**`staff.Trainer` shares this exact convention** — a trainer's five skills
are stored 1-100 and shown 0-10 through this same `to_display_scale`, not a
second mapping. See `staff/README.md`, *Stored 1-100, displayed 0-10*.

## The age curve

`services.py` moves every rider's five attributes a little each week, along
a curve individual to that rider — driven entirely by their existing
`potential`, `peak_age` and `decline_rate`, with no new hidden trait
([#58](https://github.com/mario595/cycling-manager/issues/58)). No new API
field or frontend surface exists for this: the player only ever sees the
changed numbers, never a report of what moved.

**Two halves, joined at `peak_age`, not one polynomial.** Below `peak_age`,
`weekly_deltas` closes a fraction of the remaining gap to a per-attribute
ceiling; at or above it, attributes fall at a rate scaled by
`decline_rate` and by years past peak, capped at `DECLINE_YEARS_CAP` (3)
so decline keeps accelerating for a rider newly past their peak — where it
matters for a manager's decision — without compounding without bound the
longer a rider remains active without an age-driven exit. Growth speed and
decline speed are governed by different hidden traits and must be tunable
apart — a rider's `potential` says nothing about how fast they fall once they're
past their best. Both constants are tuned so a season of growth or
decline for the *representative* case — a young rider well below
potential, or an average-`decline_rate` veteran comfortably past peak —
lands at roughly one to two points on the display scale (10-20 stored
points), the band `specs/archive/rider-growth-and-decline.md` promised before it
was deleted post-implementation (see `AGENTS.md`, *Closing a ticket*); a
rider with a near-maximum `decline_rate` can still lose somewhat more.

**The ceiling is per-attribute, not `potential` itself.** `potential` is
one number; a rider has five attributes. `attribute_ceilings()` scales it
by the same `SPECIALITY_PROFILES` weights that shaped the rider's starting
attributes (`generation.py`), so a Climber's climb ceiling sits well above
their sprint ceiling. Growing every attribute toward `potential` directly
would flatten every rider into the same profile by their peak age and
destroy speciality — this is the load-bearing decision of the whole
feature.

**`growth_debt` carries the fraction a week doesn't round to.** A week's
movement is usually well under one stored point. `apply_weekly_growth`
adds each week's delta into `growth_debt`, moves out whole points, and
keeps the remainder — so twelve weeks of 0.6 becomes 7 stored points
instead of being rounded to 0 every week or inflated to 12. It is hidden
and never serialized, like every other trait in this section.

`riders/` knows nothing about weeks, seasons or the clock —
`apply_weekly_growth(weeks, extra_deltas=None)` and `advance_ages()` are
pure with respect to time; `world.services.tick()` is what decides when to
call them and how many weeks have passed. The signature gained
`extra_deltas` and a return value for #36 — see *Weekly training*, below.
This keeps the dependency direction in `AGENTS.md` intact: `riders/` may not
import `schedule/` or `world/`.

**Decline has no floor, but retirement is what ends the decline.** A rider
can decline indefinitely toward the bottom of the range; the season close is
where they leave instead, by age. See *Retiring by age*, below.

## Weekly training

`services.training_deltas(rider, *, focus, trainer_skill, raced_attributes)`
computes one rider's weekly training movement: the trainer's skill in the
focused attribute × `WEEKLY_TRAINING_UNIT` (0.010) × the rider's hidden
`training_affinity` for that attribute, plus a flat `RACE_TRAINING_UNIT`
(0.25) stored points per race finished last week, toward each attribute that
week's terrain rewarded (the list coming from
`racing.services.riders_who_raced`). Values are stored points in the same
1-100 world the age curve operates in; a focused season lands at roughly one
display point and racing "much less" (tuning reasoning: the plan's Design
decision 8). Both units are named module constants, not literals.

The effect never goes negative and off-speciality training is never zero —
`WEEKLY_TRAINING_UNIT` scales a weak trainer's 30-score off-speciality skill
to ~0.3 stored points a week, and `staff/generation.py`'s 25 floor exists so
no generated trainer ever sits below that. `services.is_injured(rider)`
returns `False` for everyone: it is #41's seam — named and called now so the
pass skips injured riders the moment injuries exist, with no data model for
#41 to inherit (the plan's Design decision 6). Do **not** add an
`is_injured` field to `Rider`; that is #41's decision to make.

`training_deltas` never touches the database. The caller
(`world.services._apply_training_week`) collects one deltas map per affected
rider and hands it to
`apply_weekly_growth(weeks, extra_deltas=None)`, which adds the week's
training movement to its age-curve movement and settles both through the one
`growth_debt` — one pass, one rounding point (Design decisions 1 and 2; see
*The age curve*, above). The return is one record per rider whose
*displayed* value moved, which the world writes to `staff.TrainingWeekReport`
so the Training screen can report the week without diffing attributes after
the fact — the "what moved" summary this readme's *Future work* once asked
for. Because both mechanisms settle together, a listed change is the visible
number moving, not an attribution of how much came from which; that split
would be fake precision on a 0-10 scale and is deliberately not offered.

## Attribute history

`RiderAttributeSnapshot` records a rider's five attributes over time, so a
future screen ([#96](https://github.com/mario595/cycling-manager/issues/96))
can eventually plot a career arc — see
[#95](https://github.com/mario595/cycling-manager/issues/95) and
`specs/archive/rider-attribute-history.md`. A row holds all five attributes even when
only one moved: the consumer plots five lines on one graph and needs a value
for every attribute at every recorded moment, not just the one that changed.

**Snapshots record the displayed 0-10 value, never the stored 1-100 value.**
The whole point of the display scale (*Display scale*, above) is that a rider
can improve without the shown number moving; recording the finer stored value
would put growth into the database that the design deliberately hides from
the player — the same leak `Visible vs hidden` calls a defect for a hidden
trait. `riders.services.record_initial_snapshots` and `record_week_snapshots`
both write through `to_display_scale`, never the raw attribute.

**Two writers, matching the two moments a rider's attributes are set.** A
baseline row (`week=None`) is written at creation —
`record_initial_snapshots(riders)` is called immediately after
`Rider.objects.bulk_create(...)` at each of the three places a rider comes
into being (`teams.services.claim_team`, `seed_teams`, `reset_riders`) — so a
graph is never empty and a rider who never changes still plots as a flat
line. Thereafter, a row is written only in a week where at least one
displayed value actually moved: `world.services._apply_training_week`
already computes exactly that from `apply_weekly_growth`'s return, so
`record_week_snapshots(rider_ids, week_id=...)` just writes it — one call per
crossed week, so a tick that catches up several missed weeks attributes each
week's change to that week, never bunching them into the week the tick
happened to run.

**`record_week_snapshots` takes a plain `week_id` int, not a `Week`.**
`riders/` may not import `schedule/` (`AGENTS.md`) — `RiderAttributeSnapshot.
week` is declared as the string `"schedule.Week"`, the same import-free
pattern `staff.TrainingWeekReport.week` uses.

**Served by `GET /api/riders/<id>/`** (#96, `api/README.md`) — the rider
page's attribute-history chart. The endpoint ships the snapshots in time
order, baseline first, and **must not** pass them through
`to_display_scale` a second time: they are already the displayed 0-10
value this section describes, and re-mapping would floor an 8 to a 0.
There is no other API field and no admin surface beyond the default
read-only list.

## Freshness

`freshness` is a rider's race readiness — a visible field, stored 1-100
(default, and ceiling, 100 — the same range as the engine attributes) and
mapped onto the 0-10 display scale for the player. `recovery_rate` (default
50, hidden) is how much of that ground a rested week wins back. The two
fields follow the same stored-1-100 / shown-0-10 convention as the engine
attributes; the recovery rate is a *rate of change*, so it has no display
scale and is never serialized ([#59](https://github.com/mario595/cycling-manager/issues/59)).

**Cost and recovery are fixed constants in `services.py`, not field-tuned.**
`RACE_FRESHNESS_COST` (25 stored points) is deducted from every **starter**
when their race is simulated (`racing.services.simulate_race`) — a rider
cut by the race engine's time limit (the broom wagon; see
`race_engine/README.md`, *Simulation tick*) pays the same cost as a
finisher, because missing a race that way still costs a rider's legs the
same as racing it. A stage of a stage race costs `STAGE_FRESHNESS_COST`
(10) instead — less than a full race, but a whole tour still costs more:
a 7-stage tour costs 70, above one race (25) but below wrecking a fresh
rider (`FRESHNESS_FLOOR` is 20). `racing.services.simulate_race` is what
picks which constant applies, via `apply_race_cost`'s `cost` keyword — see
`racing/README.md`, *Stage races*. A week's recovery is the rider's `recovery_rate` mapped
linearly onto `[RECOVERY_MIN, RECOVERY_MAX]` = [8, 20], applied once per
week by the tick to every rider who did **not start** a race that week.
Because the recovery rate is
hidden, a rider's max race-and-recover cadence varies from rider to rider:
the fastest-recovering roster at 20/week can race ~1.3 times per week without
net loss, the slowest at 8/week only once — a race almost always costs more
than a single resting week returns, which is the point: consistent racing
wears a rider down and a manager must rotate their four-rider squad between
races within a twelve-week season.

**Three hard limits.** `FRESHNESS_MAX` caps recovery; `FRESHNESS_FLOOR` (20)
is where cost stops: a rider never drops below it, because below the floor
they would be racing at a fixed minimum rather than a further-restricted
one — races below it still cost the rider nothing extra (cost stops, rather
than bouncing at the floor). `PENALTY_AT_FLOOR` (0.80) is the ceiling on how
much fatigue can hold a rider back. `freshness_multiplier` maps stored
freshness linearly onto `[PENALTY_AT_FLOOR, 1.0]` and breaks the
inferability rule's *rate* half: the player watches freshness move on the
squad screen and takes the consequences (weaker racing) without ever seeing
the multiplier.

**`riders/` never applies the penalty or the cost.** `services.py` owns the
arithmetic and the weekly recovery pass; the *penalty* is applied in exactly
one place — `racing.adapters.to_engine_rider` scales a rider's five engine
attributes by their freshness as they cross into the engine — and the *cost*
in exactly one place — `racing.services.simulate_race`, which deducts it from
every starter's stored freshness (`racing.services.riders_who_started`'s
population — finisher or cut by the time limit) inside the same transaction
that records results. The weekly pass lives where the week lives:
`world/services.py` calls `apply_weekly_recovery` alongside
`apply_weekly_growth`, excluding riders who **started** a race in the week
being settled — the same starters set, not just finishers
(`racing.services.riders_who_raced` stays the *training* reader and is
unaffected: a cut rider didn't complete the course, so there's nothing to
have learned from it). This keeps the
dependency direction in `AGENTS.md` intact — `riders/` may not import
`racing/` or `world/`, so the consumption and the recovery both live where
the caller lives.

## Salary

`weekly_salary` is a rider's weekly wage, stored in whole credits, visible
on the roster and never mapped through `to_display_scale` — it is money,
not a 0-100 attribute ([#25](https://github.com/mario595/cycling-manager/issues/25)).
`pricing.weekly_salary_for(rider)` is the single formula that computes it,
from two inputs only:

- **`strength(rider)`** — the five engine attributes, weighted by
  `SPECIALITY_PROFILES` (the same table `generation.py` uses to shape a
  starting roster), so a Climber's price tracks their climb more than their
  sprint.
- **`age_multiplier(rider.age)`** — a mild adjustment, at most ±15%, that
  reads the visible `age` field only.

**No hidden trait feeds it, deliberately.** `potential` says how good a
rider could become; pricing off it would put a number on screen that
silently reveals a trait the player is never shown directly, which
*Visible vs hidden* above treats as a defect everywhere else it could
happen. Two riders who look identical on the roster page cost the same,
even if one has far more room to grow — an accepted imprecision, not an
oversight.

**Set at creation, recomputed at every season close — frozen in between.**
`generate_rider()` calls `weekly_salary_for` and stores the result. The
weekly age curve and training move the same rider's attributes every week,
but nothing changes their stored salary mid-season — the player's wage bill
is predictable inside a season. At a season boundary that changes:
`world.services.tick()` calls `reprice_all()`, which recomputes every
rider's salary from the formula — *after* `advance_ages()` has aged them
(`world/README.md`, *How a tick works*) — and `economy/services.py` writes
one `SalaryReviewReport` per managed team (see `economy/README.md`, *Salary
review*).

`reprice_all()` (in `riders/services.py`) always writes every rider's exact
formula value, but only returns the riders whose salary moved by at least
`SALARY_REVIEW_THRESHOLD` — the threshold filters the *report*, never the
write, so a stored salary can never drift from the formula on behalf of a
quiet rounding step.

**Calibrated against generated rosters, not the 1-100 range.** A
generated rider's attributes cluster well under 100 (`QUALITY_SPREAD`,
`_MAX_STARTING_ATTRIBUTE` above), so `pricing.py`'s constants
(`SALARY_AT_MIN_STRENGTH`, `SALARY_AT_MAX_STRENGTH`, the strength
exponent) were picked by sampling `generate_rider`, not by reasoning about
the theoretical range — see `riders/tests/test_pricing.py`'s two
calibration tests, which pin the spread at roughly 10x between a weak and
a strong generated rider and the average at `economy.models.
WEEKLY_WAGE_PER_RIDER`. Retuning the formula means re-running those tests
until they pass again, not eyeballing the constants.

**A second price exists in `transfers/`** — market value
([#31](https://github.com/mario595/cycling-manager/issues/31)), what a
rider is worth rather than what they cost to keep. It reuses `strength()`
unchanged but defines its own age curve rather than reusing
`age_multiplier`: salary's curve is a mild, symmetric penalty around a
prime band, which is right for a wage and wrong for a valuation that needs
to price in years of career remaining. A change to `strength()` moves both
prices; a change to `age_multiplier` moves only this one. See
`transfers/README.md`, *Value vs salary*.

`economy.services.charge_weekly_wages` sums every team's riders'
`weekly_salary` each week — see `economy/README.md`, *Wages run off week
transitions*.

## Team membership stamps

`joined_team_at` and `unattached_since` are two nullable game-time stamps on
`Rider` that frame a rider's place in the transfer market: `joined_team_at`
is the instant the rider joined the team they are currently on (or the last
team, once teamless), and `unattached_since` is the instant they were last
released to the pool. Both are written by
`riders.services.mark_team_change(riders, team_now, at)` — a single helper,
used by every team move so the two stamps can never drift out of step with
`team`:

- `teams.services.claim_team` stamps every rider claimed with
  `joined_team_at = at` (the claim instant), so a claimed roster is exactly
  the riders whose stamp equals the team's `managed_since`.
- `transfers.services.sign_free_agent` and `release_rider` stamp signings
  and releases the same way — releasing sets `team = None` **and**
  `unattached_since`, so the pool can age riders.
- `riders.services.mark_team_change` is deliberately unused by direct
  `save()` writes; settling a new `at` through it is the rule.

Who reads them, and why:

- `transfers/` — `release_cost_for` tests the **claim-cooldown exemption**
  by comparing a rider's `joined_team_at` with the team's `managed_since`:
  a rider who joined at the exact claim instant releases for free while the
  cooldown holds, a rider signed afterwards pays severance.
  `free_agents()` is `Rider.objects.active().filter(team__isnull=True)`, so
  retired riders are never in the pool.
- `world/` — `_expire_free_agents` ages `unattached_since` against `Week`
  rows (the same count schedule.services.weeks_opened_between uses for managers) to find free
  agents that have sat too long, then retires selected riders who have raced
  and deletes selected riders who never raced. See `transfers/README.md`,
  *Free agents*, and `world/README.md`, the tick.

The stamps are game time (same clock as salary/tick), never wall-clock time,
and are both null for riders generated teamless (generation creates riders
off the market; see `transfers/README.md` for what happens to pre-migration
rows whose `unattached_since` is null).

## Retirement

`retired_at` is a nullable game-time stamp on `Rider`: `NULL` means the rider
is active, and a non-null value is the permanent moment they left the game. It
is never cleared. A timestamp is deliberately used instead of a status enum so
it can answer when the rider retired and can later be shared with age-driven
retirement ([#42](https://github.com/mario595/cycling-manager/issues/42))
without adding a week foreign key to this app.

A retired rider must have no team. The database constraint
`retired_rider_has_no_team` enforces `retired_at IS NULL OR team_id IS NULL`;
`riders.services.retire_riders` rechecks both teamlessness and active state in
its conditional update. The rider's profile and historical race rows remain
available, but the rider is out of circulation for good.

`Rider.objects.active()` is the single definition of an active rider. Every
new loop that processes every rider must use it rather than
`Rider.objects.all()`. The four existing all-rider passes use it so a retired
rider is frozen: `apply_weekly_growth`, `apply_weekly_recovery`,
`advance_ages`, and `reprice_all`. Once `retired_at` is set, attributes,
`growth_debt`, freshness, age, and `weekly_salary` do not change. Expiry dates
the stamp to the qualifying `week.starts_at`; age-driven retirement
(#42) does the same with the closing season's final week — see *Retiring by
age*, below.

### Retiring by age

A rider leaves the game at a **hidden age between 33 and 38**
(`RETIREMENT_AGE_MIN` + `RETIREMENT_AGE_SPAN` in `services.py`), with a full
season's warning first
([#42](https://github.com/mario595/cycling-manager/issues/42)). Every active
rider is affected — rostered or a free agent, managed team or unmanaged. The
window is a band, not a number: no rider retires young, and every rider
eventually does, but *where* in the band is the rider's own.

**The age is derived, never stored.** `retirement_age(rider)` is a pure
function of the two hidden traits set once at generation and never mutated —
`peak_age` and `decline_rate` — weighted 3 for peak age against 2 for decline
rate. A late peaker and a slow decliner play on; a fast decliner goes sooner,
and a rider who peaked at 32 outlasts one who peaked at 24. Peak age being
the bigger driver is deliberate: it makes the trait *inferable* — a player
watching many careers can learn "late bloomers last" without ever seeing the
number. Both inputs are immutable, so the result is stable for a rider's
whole life, and there is no backfill for existing riders. The formula clamps
its `peak_age` share to the generation range (now the public
`PEAK_AGE_RANGE`, renamed from `_PEAK_AGE_RANGE` and imported rather than
copied, so the window cannot drift from what generation produces), because
the validator allows a `peak_age` outside it.

**`is_due_to_retire(rider)` is the read-time marker**, and returns `False`
for a retired rider whatever their age — which is what lets `api/` tag riders
without ever tagging one who is already gone.

**`retire_due_riders(at=...)` is one conditional UPDATE** that clears the team
and stamps `retired_at` together, so the `retired_rider_has_no_team`
constraint holds row by row. It deliberately does **not** reuse
`retire_riders()`, which filters `team__isnull=True` to serve free-agent
expiry and would silently skip every rostered rider. Nor does it call
`mark_team_change`: `unattached_since` means "released into the pool at", and
a retired rider never sat in the pool — both that stamp and `joined_team_at`
are left untouched, so the roster they left still says when they joined it.
`world/` decides when it runs; this app knows nothing about seasons, in the
same way `advance_ages()` and `reprice_all()` do not.

**The stamp is the closing season's final week's `starts_at`,** written by
`world.services.tick()` — not `season.ends_at`, which falls outside the
season and would resolve to the next season's week 1 in the profile's
`Retired · Season N, Week W` label. The `is_due_to_retire` check and the
retire pass both run **before** `advance_ages()` at that close, which is what
gives the rider their full season of warning: the reverse order would age
them into the window and retire them in the same tick. See `world/README.md`,
*How a tick works*.

## Development squad

A team can run a development squad at one of three levels, and the levels form
a ladder it climbs one rung at a time. The whole
facility lives here rather than in `transfers/`, which is where the *free-agent
market* lives: the squad is a long-lived attribute of the team, not a
transaction.

`DevelopmentSquad` holds a one-to-one link to the team, the `level` it runs
at, and `opened_at` (game time, informational). **That is all it stores.**

**One row per open squad, and closing deletes it.** There is no `closed_at`
flag and no `is_open`. A team with no row has no squad; a team with a row is
running one. A flag would leave a second way for the same question to be
answered — `squad.level is not None` on a row, or the absence of a row — and
every reader would have to know which one to trust. Deleting also means
closing is not an event that has to be written to the ledger or replayed;
`close_squad` returns whether there was a squad to close, which is all a
caller needs to know.

**Prices and capacity are a table in `LEVELS`, never columns on the row.** A
stored price could only ever drift from the table, which is the same
reasoning `staff/pricing.py` gives for a trainer's fee and salary: derive
it, never persist it. `LEVELS` maps level to `LevelTerms(level, name,
opening_fee, weekly_cost, places)`, and `weekly_cost` / `level_fee` /
`free_places` read it. `places` is how many prospects the level can hold —
6 / 8 / 10 — so a rung costs more to reach, more to run **and** holds more,
which is what makes the ladder worth climbing rather than a price list.

**The squad is a ladder, climbed one rung at a time, with no way back down.**
A squad opens at `ENTRY_LEVEL` (`min(LEVELS)`, derived so adding a level
cannot leave it stale) and is upgraded to the level directly above the one
held. Opening above the entry level raises `LevelLocked` however rich the team
is, skipping a rung raises it too, and any level below the one held raises
`CannotDowngrade` — there is no way to spend less except closing the squad,
which forgets the level, so a reopened squad starts at the bottom again.

**A level's fee is what reaching it costs, in every state.** `level_fee(level)`
is the only pricing function there is: opening (at the entry level) and
upgrading into any level both charge the target's own `opening_fee`, so the
figure the panel quotes is the figure the ledger is debited, and reaching Elite
costs 30,000 + 75,000 + 150,000 = 255,000 rather than its fee alone. There is
no per-move arithmetic to disagree with, and no discount for a team that
climbed here before.

**Both columns rise strictly with level, and a test enforces it.** Load-bearing,
though not for the reason it first was. It is no longer about an upgrade
undercutting a direct opening — there is no way to open above the entry level,
so that side door is shut structurally. It is that the top of the ladder has to
be the most expensive thing to reach *and* to run, or a player would
rationally stop short of it, or climb to save money. The numbers are tunable;
the ordering is not.

`level_status(current, target)` is the single place the ladder rule lives,
returning a `LevelStatus(action, note)`. `open_squad`, `change_level` and the
API's per-level `action` all go through it, so a padlock the screen draws and a
refusal the service raises cannot disagree. It returns the `note` alongside
the action because a locked level has **two** reasons and they need different
words: a rung not yet reached ("Upgrade to National first") and one already
climbed past ("Climbed past. Close the squad to start over."), since with no
downgrade the only way back is to close. `change_level` distinguishes its two
exceptions by comparing levels rather than asking `LevelStatus`, because
`note` is copy for the screen while an exception type is a promise to a caller
about *why*.

**The fee is debited by an injected `charge` callback, not here.** `riders/`
may not import `economy/` (`AGENTS.md`: `riders -> core, teams`), so
`open_squad` and `change_level` take `charge(amount, description)` and run it
themselves — the same pattern `staff.services.hire_trainer` establishes. The
callback runs **after** the state checks and **before** the row write, and the
write sits in a nested savepoint. That order is the whole design: a callback
that raises (`InsufficientFunds`) takes its ledger row down with the whole
operation, and the savepoint means the `IntegrityError` path still leaves the
enclosing transaction usable, so the caller sees `SquadAlreadyOpen` rather
than a poisoned transaction. Without a callback the operation is free, which
is what the domain-level tests use.

**All three write operations take the `Team` row lock**, in one order:
validate the level, lock, then check state and act. When the squad is closed
there is no squad row to lock, so the team row is the only thing that
serialises two concurrent "open" requests — and locking it for upgrade and
close too means there is one lock order rather than two.
`select_for_update()` **without** `skip_locked`, unlike `claim_team`: the
caller asked for this specific team, so a contended row should make the
request wait, not behave as though the squad were not there. The
`OneToOneField`'s unique index is the second line of defence behind that
lock.

**Closing is two different events wearing one button (#34).** Before #34 a
close released every rider in the squad to the free-agent pool. Now the
rider's **state** decides, and the two go opposite ways: one still *in the
squad* is **discarded outright**, while a **graduate** is **released to the
pool**. The reason is the spec's: a rider who served their full spell is a
plausible signing and worth a market place, and one pulled mid-development is
not. `close_squad` returns a `SquadClosure` naming which riders went where
(`discarded: int`, `released: list[int]`, or `None` when there was no squad to
close), because a caller that has to cancel the released riders' auctions
afterwards needs to know they existed. See *Youth triage*, below, and
`transfers/README.md`, *Auctions*.

Closing writes nothing to the ledger and refunds nothing, and it is the only
way to reduce the weekly cost — which is what makes it a drastic measure
rather than a cheaper setting, and why reopening has to start from the bottom
again. A mid-week change is charged at the new rate from the next
week boundary, with nothing prorated and nothing refunded for the half-week
just gone; see `economy/README.md`, *Development squad costs*.

Claiming a team closes its squad the same way — discarding every rider still
in it and releasing every graduate to the free-agent pool with
`unattached_since` stamped (`teams/README.md`, *Claiming a team*; see *Youth
intake* and *Youth triage*, below, for the release path itself). Releasing a
team does not touch the squad.

**Youth intake (#33) populates the squad.** See *Youth intake*, below, for
what arrives, how often, and how a manager sees it. The corollary the
previous paragraph used to state — that no screen may promise riders the code
does not produce — is now the narrower rule the screen actually follows:
it describes the cadence and that a higher level improves the odds, and it
never states a percentage or promises an outcome for a single batch (spec, *In
scope* 9). `DevelopmentSquad.test.tsx` pins that rule for both states.

## Youth intake

Every open development squad receives a batch of young riders on a fixed
cadence, through `youth_intake.py` — the same file that decides *what* a
batch looks like; *when* it runs is `world/`'s decision (`world/README.md`,
*How a tick works*).

**Representation: `team = NULL` and `development_squad` set — never a flag on
top of a roster spot.** Every roster-shaped query in the codebase already
filters on `team` (wages, training focus, the roster cap, auctions, releases,
race squads, the roster GET), so a squad rider with `team = NULL` falls out
of all of them with no change to any of that code. The only thing a null
`team` pulls a rider into is the free-agent pool, which `free_agents()` and
`sign_free_agent` both exclude a squad rider from explicitly (see
*Free agents* in `transfers/README.md`). Keeping `team` set and adding an
`in_development_squad` flag was rejected: it would invert the surface, and
every one of those roster queries would need its own exclusion — the first
one forgotten pays a youth rider's wage or lets them race.

**Two database invariants**, `CheckConstraint`s on `Rider`:
`rider_not_on_roster_and_in_squad` (`team IS NULL OR development_squad IS
NULL`) and `retired_rider_not_in_squad` (`retired_at IS NULL OR
development_squad IS NULL`). Cheap, and they turn the likeliest future bug —
#34's promotion setting `team` and forgetting to clear the squad — into an
`IntegrityError` rather than a rider in two places at once.

**`intake_at`** (`DateTimeField`, null, never cleared) records the game time
a rider arrived through intake — always a `week.starts_at`, resolved through
`schedule.services.current_position` the same way `retired_at` resolves to a
season/week on the profile screen. It doubles as the idempotency key for a
batch (a squad can never get two batches dated to the same `intake_at`) and
as the "is this rider from the latest batch" marker the squad screen shows
(`is_new` in `api/README.md`).

**Cadence and batch size are constants**: `INTAKE_INTERVAL_WEEKS` (4) and
`INTAKE_BATCH_SIZE` (2). `is_intake_week(week_number)` is `week_number %
INTAKE_INTERVAL_WEEKS == 0`, giving weeks 4, 8 and 12 of a twelve-week
season — three batches, six riders, for a squad open the whole season.

**Generation is potential-first, not quality-first.** For a youth,
"hopeless or promising" is a statement about hidden `potential`, and the
squad's level has to bias exactly that trait — deriving potential from a
rolled quality the way ordinary generation does would only give the level an
indirect handle on it. `generate_youth_rider(level, *, rng)`:

1. Picks a potential band from `POTENTIAL_BANDS` — `(20, 35)` hopeless,
   `(36, 50)` journeyman, `(51, 65)` promising, `(66, 85)` gem — weighted by
   `BAND_WEIGHTS[level]`, and draws `potential` uniformly inside it.
2. Sets `quality = round(potential * uniform(*YOUTH_QUALITY_FRACTION))`
   (`YOUTH_QUALITY_FRACTION = (0.25, 0.40)`), clamped to at least 1 — a
   youth's starting ability sits well below their ceiling, "far below
   professional level" even for a gem.
3. Draws age uniformly from `INTAKE_AGE_RANGE` (17-19).
4. Calls `generation.generate_rider(quality=..., age=..., potential=...,
   rng=rng)` — the new optional `potential=` argument on `generate_rider`
   replaces `_roll_potential`'s own derivation, still floored at the rider's
   own best rolled attribute (`max(potential, best_attribute)`), the same
   young-rider rule that already holds without the override.

`BAND_WEIGHTS` is keyed by the same integers as `development_squad.LEVELS`,
and a test asserts the two key sets are equal so a fourth level cannot
silently skip intake. Three properties of the table are enforced by tests,
not just the numbers themselves: the share of promising-or-better rises
strictly with level, the bottom two bands are a majority at every level, and
every band has a non-zero weight at every level — even a Regional squad can
produce a gem, rarely.

**`run_intake(*, at, rng=None)` is the load-bearing function.** For every
team with an open squad, under the **same team lock `close_squad` takes**,
it re-reads the squad **by team** (not by the id listed earlier — a squad
closed and reopened between the listing and the lock still gets its batch),
skips a team whose squad has closed since, skips a batch already written for
this `(squad, intake_at)` pair (the second line of defence behind the
`WeekTransition` row's exactly-once guarantee), creates as many of
`INTAKE_BATCH_SIZE` youth riders as there are **free places**
(`free_places(squad)`), with `development_squad` set and `intake_at = at`,
then writes their baseline attribute snapshots (`record_initial_snapshots`).
The lock matters because a manager can close the squad *during* the tick —
without it, intake could insert riders pointing at a squad `close_squad` is
deleting, and the FK's `SET_NULL` would then leave them in the free-agent pool
with no `unattached_since` stamp, the exact bug D6 below exists to prevent by
another route.

**A full squad is turned away, not queued, and intake says so (#34).** Before
#34 the batch was created unconditionally and simply overfilled the squad;
now the shortfall is real and reported. `run_intake` returns an
`IntakeResult(created, turned_away)` per squad, `world/` sums both into its
`TickRun` counters, and the squad screen's next-intake payload carries
`arrivals_at_risk` — how much of the *next* batch would be lost if nothing
changes — so the warning arrives **before** the week rather than after it.
Discarding a prospect or promoting one into the senior roster frees a place,
which is why the figure is a projection rather than a promise.

**Closing releases the squad's *prospects*, and the release must stamp
`unattached_since` before the row disappears.** `close_squad(team, *, at)`
takes a required `at`: every **prospect** is stamped
`unattached_since = at` via the existing `mark_team_change(riders,
team_now=None, at=at)`, then has `development_squad` cleared, and only then
is the squad row deleted. A **graduate** is deleted rather than released
(*Youth triage*, below). Deleting first would let the FK's `SET_NULL` unlink
them silently with a null `unattached_since` — and a free agent with a null
`unattached_since` is never treated as long-unattached by the pool's expiry
rule (`transfers/README.md`, *Free agents*), so an unwanted 17-year-old would
sit in the market forever.

**Squad riders grow like any other rider, but draw no wage and get no
trainer focus.** Growth is free: `apply_weekly_growth` and
`apply_weekly_recovery` both iterate `Rider.objects.active()`, which a squad
rider is. Wages and training are free by construction, not by an exclusion
someone had to remember: `economy.services.charge_weekly_wages` sums
`Team.riders`, and `world.services._apply_training_week` iterates
`trainer.team.riders.all()` — both read the `team` FK, which is null for a
squad rider. A rider arriving in an intake week's own tick first grows at
the *following* week's boundary, because intake in the tick runs **after**
that week's growth, training and charges — otherwise a rider's baseline
snapshot and their first week of growth would land at the same instant, and
the attribute history would open with a jump that never happened.

## Youth triage

`youth_triage.py` (#34) is what makes a development squad a *decision* rather
than a queue. Before it, a youth rider simply accumulated in the squad until
someone closed it, and the interesting question — keep this one, sell that
one, drop the other — had no answer anywhere in the game.

**A squad has two kinds of member, and the partition is `graduated_at`.** An
**in-squad rider** is a prospect: `development_squad` set, `graduated_at` null,
occupying one of the level's `places`, and growing. A **graduate** keeps the
squad link but has `graduated_at` stamped — so they are still *the squad's to
decide about* while **occupying no place**, which is the whole point: the
squad's places exist for riders it is still developing, and holding a
finished rider in one would block the intake that replaces them.
`in_squad(squad)` and `graduates(squad)` are the two queries, `free_places(squad)`
is `places - in_squad.count()`, and `belongs_to(rider, team)` is the ownership
question both of them answer: true for a roster rider and for this team's
graduate, false for an in-squad rider and for another team's graduate.

**Squad riders develop faster than anyone else, scaled to a ceiling the player
never sees.** `squad_development_deltas(rider)` returns only the *extra* week
of movement on top of the ordinary age curve, and per attribute the total
wanted this week is

    min(gap, max(base + gap * SQUAD_GROWTH_FRACTION,
                 SQUAD_MIN_WEEKLY_GAIN if gap > 0 else 0))

where `gap = max(0, ceiling - current)` and the ceiling is the hidden
`potential` (`attribute_ceilings`). Three promises in three clauses: the term
is **proportional to the gap**, so watching the bars move is real evidence
about a ceiling that is never displayed; the **floor**
(`SQUAD_MIN_WEEKLY_GAIN = 0.8`, `SQUAD_GROWTH_FRACTION = 0.03`) is what makes
"every rider ends better than they arrived" true — without it the
proportional term alone leaves the weakest arrivals visibly flat, which the
age curve on its own does to roughly 17 arrivals in 4,000 over a full spell;
and the `min(gap, …)` **cap** is what makes "no rider passes their hidden
ceiling" true however generous the floor is. It never touches the database, so
the constants were tuned by simulating seeded riders in memory.

**The spell is 14 weeks; the decision window is 2.** `SPELL_WEEKS` and
`GRADUATE_WINDOW_WEEKS` are constants here, counted in *declared* weeks
through `schedule.services.weeks_opened_between` — never by dividing a
timedelta by seven — so a gap between seasons contributes nothing, which is
what makes a season boundary (a week-4 arrival graduating on week 18, six
weeks into the next season) fall out for free. `graduate(rider_ids, *, at)`
stamps `graduated_at` and does nothing to a rider who was already promoted.
`release_graduates(rider_ids, *, at)` is the other half: a graduate whose
window closed is stamped `unattached_since`, has the squad cleared and joins
the free-agent pool — **unless they are listed**, in which case the auction
decides (`world/README.md`, *How a tick works*).

**Promote and discard are the two decisions, and both take what they cannot
know.** `promote(team, rider_id, *, at, roster_cap)` moves a prospect *or* a
graduate onto the senior roster, setting `weekly_salary =
weekly_salary_for(rider)` and clearing `team` and `development_squad` in one
`save()` — two saves would put a rider in both places at once for the length of
a round trip and trip `rider_not_on_roster_and_in_squad`. It works on a
graduate too: deciding early is a choice a manager is entitled to make, and
the alternative the spec weighed — refusing it — has the worse consequences.
`discard(team, rider_id, *, check=None)` deletes the rider outright — they
leave the game rather than joining the pool — and takes a `check` callback, so
the API can refuse a rider with an open auction while `riders/` learns nothing
about the auction market.

**Both take their collaborator as an argument, never an import.**
`roster_cap` lives in `transfers/` and the listing check lives in `api/`, and
`riders -> core, teams` (`AGENTS.md`) is not negotiable — the same rule that
puts `charge` in `open_squad`'s signature. `lock_rider(rider_id)` is public for
a database reason rather than a design one: a squad row is nullable, so
`select_for_update()` on an outer join locks *every* table it touches unless
`of=("self",)` is given.

`development_squad.py` imports the triage module **inside** `close_squad`,
not at module scope: `youth_triage` imports `LEVELS` for `free_places`, so a
top-level import between them is a cycle. The lazy import keeps the dependency
real and breaks the loop, exactly as `teams/` does with `economy/`.

## Generation

`generation.generate_rider()` builds one unsaved, internally consistent
rider; `generate_roster(size, team=...)` builds a squad-sized group with a
deliberate spread of quality, not a population of near-clones.

**Speciality is chosen first, and everything else follows from it** — not
the reverse. `SPECIALITY_PROFILES` weights each of the five attributes per
speciality (a Climber's `climb` weight is 1.45, its `sprint` weight 0.55),
`BUILD_PROFILES` gives each speciality a height/weight mean, and
`FIRST_NAMES`/`LAST_NAMES` (keyed by nationality — only Spain exists today)
supply a name. This order matches `specs/archive/rider-attributes.md`'s decision
that speciality is innate, assigned from build, not derived after the fact
from rolled attributes — "94 climb / 38 sprint comes out a Climber" has to
be a guarantee, not a coincidence.

**Every `SPECIALITY_PROFILES` row sums to roughly the same total (~5.0).**
This is load-bearing: it is what stops one speciality being globally
stronger than the others. A row that sums higher would mean that
speciality's riders quietly win more races for a reason the player has no
way to see on the 0-10 roster page. Changing a profile's shape is fine;
changing its total is a balance decision, not a tuning tweak.

**Potential is derived from the rolled attributes, not from `quality`
alone.** A speciality's profile weight can push an attribute above
`quality` itself (a high-roll Climber's `climb` can exceed a `quality` of
70), so deriving potential from `quality` alone can produce a young rider
whose potential sits below an attribute they already have — a
contradiction the spec rules out explicitly. `generate_rider` derives
potential from `max(rolled attributes)` as well as `quality` and age to
avoid it.

**`generate_rider` takes an optional `potential=` override (#33).** When
given, it replaces the derivation above entirely: the rider's `potential` is
`clamp(max(potential, max(rolled attributes)), 1, 100)`, still floored at the
rider's own best rolled attribute so the young-rider rule ("cannot already
exceed their own ceiling") holds whether potential is rolled or supplied.
Every caller before #33 passes nothing, so behaviour is unchanged for
ordinary generation — the only caller that supplies it is youth intake's
`generate_youth_rider`, which rolls potential first from a squad level's
odds and derives `quality` from it (see *Youth intake*, above).

Every generation function takes an optional `rng: random.Random` so tests
(and anything that wants a reproducible roster) can seed it; callers that
do not care can omit it.

`generate_roster` has two callers: `reset_riders` below, and
`teams.services.claim_team` — a newly claimed team's roster is generated the
same way, with the same quality spread, as a full population reset. See
`teams/README.md`, *Claiming a team*.

## `reset_riders` — replacing the population

```bash
python manage.py reset_riders --yes [--per-team=12]
```

Deletes every `Rider`, plus every `RaceResult` and `RaceSquad` (and its
cascaded `RaceSquadRider` rows) that pointed at one, then generates
`--per-team` (default 12) riders for every team. Refuses to run without
`--yes`.

**This is destructive by design, not a safety gap to close.** Existing
riders are not backfilled with new attributes — they are replaced, and the
race history attached to them goes with them. `specs/archive/rider-attributes.md`
accepts this explicitly: this is a pre-launch world with no real players,
and inventing a scheme to detach historical results from deleted riders
would be protecting data nobody is attached to. Revisit this command's
behaviour if it is ever run against a world with real accounts in it.

Imports `racing.models` inside `handle()`, not at module scope — this
app's library code (`models.py`, `generation.py`, `display.py`) must never
import `racing/` (`AGENTS.md`: `riders -> core, teams`), but a management
command is an entry point, the same latitude
`schedule/management/commands/load_season.py` takes for the same reason.

## Future work / possible improvements

- **A second nationality.** `Rider.Nationality` and the name pools in
  `generation.py` are structured as one entry per country specifically so
  that adding one is a choices-list and name-pool edit, not a migration or
  a `generate_rider` signature change.
- **Attributing movement to growth vs training.** The "what moved" list is
  built — `staff.TrainingWeekReport` at each rollover, shown on the Training
  screen — but a change is the visible number moving, with no split of how
  much came from the age curve vs training. That split is deliberately not
  offered: growth and training settle through one ledger, and attributing
  them on a 0-10 scale would be false precision.
