# Riders — the roster asset

## What this app owns

`Rider` — persisted riders mirroring the race engine's attributes, plus
everything the engine does not know about: speciality, build, age, and a set
of hidden traits. Generation (`generation.py`), the display mapping
(`display.py`), the age curve (`services.py`), and the `reset_riders`
management command. Not squads or race results (`racing/`), not the race
simulation itself (`race_engine/`).

## Visible vs hidden

Every rider carries two kinds of attribute:

- **Visible**: `speciality`, `nationality`, `height_cm`, `weight_kg`, `age`,
  `freshness`, `weekly_salary`, and the five engine attributes (`climb`,
  `sprint`, `flat`, `resistance`, `positioning`). These are what
  `api.RiderSerializer` and `api.SquadRiderSerializer` ship to the player
  (`weekly_salary` is roster-only — see *Salary*, below).
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
longer a rider has been retired-in-all-but-name. Growth speed and decline
speed are governed by different hidden traits and must be tunable apart —
a rider's `potential` says nothing about how fast they fall once they're
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

**Decline has no floor, and there is no retirement.** A rider can decline
indefinitely toward the bottom of the range and sit on a roster, unusable,
forever — deliberately out of scope here. See *Future work*, below.

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

**Nothing serializes this.** #96 is the consumer, once it exists; there is no
API field, no admin surface beyond the default read-only list, and no
frontend today.

## Freshness

`freshness` is a rider's race readiness — a visible field, stored 1-100
(default, and ceiling, 100 — the same range as the engine attributes) and
mapped onto the 0-10 display scale for the player. `recovery_rate` (default
50, hidden) is how much of that ground a rested week wins back. The two
fields follow the same stored-1-100 / shown-0-10 convention as the engine
attributes; the recovery rate is a *rate of change*, so it has no display
scale and is never serialized ([#59](https://github.com/mario595/cycling-manager/issues/59)).

**Cost and recovery are fixed constants in `services.py`, not field-tuned.**
`RACE_FRESHNESS_COST` (25 stored points) is deducted from every finisher when
their race is simulated (`racing.services.simulate_race`); a week's recovery
is the rider's `recovery_rate` mapped linearly onto
`[RECOVERY_MIN, RECOVERY_MAX]` = [8, 20], applied once per week by the tick
to every rider who did **not** race that week. Because the recovery rate is
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
the finishers' stored freshness inside the same transaction that records
results. The weekly pass lives where the week lives: `world/services.py`
calls `apply_weekly_recovery` alongside `apply_weekly_growth`, excluding
riders who finished a race in the week being settled. This keeps the
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
  `free_agents()` is simply `team__isnull=True`.
- `world/` — `_expire_free_agents` ages `unattached_since` against `Week`
  rows (the same count schedule.services.weeks_opened_between uses for managers) to find free
  agents that have sat too long, then deletes them. See
  `transfers/README.md`, *Free agents*, and `world/README.md`, the tick.

The stamps are game time (same clock as salary/tick), never wall-clock time,
and are both null for riders generated teamless (generation creates riders
off the market; see `transfers/README.md` for what happens to pre-migration
rows whose `unattached_since` is null).

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
- **Retirement.** Decline has no floor and no exit today — a rider can
  fall indefinitely and stay on the roster, unusable, forever. Belongs to
  a dedicated retirement feature ([#42](https://github.com/mario595/cycling-manager/issues/42)),
  not to the age curve itself.
- **Attributing movement to growth vs training.** The "what moved" list is
  built — `staff.TrainingWeekReport` at each rollover, shown on the Training
  screen — but a change is the visible number moving, with no split of how
  much came from the age curve vs training. That split is deliberately not
  offered: growth and training settle through one ledger, and attributing
  them on a 0-10 scale would be false precision.
