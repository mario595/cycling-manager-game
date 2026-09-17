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
  and the five engine attributes (`climb`, `sprint`, `flat`, `resistance`,
  `positioning`). These are what `api.RiderSerializer` and
  `api.SquadRiderSerializer` ship to the player.
- **Hidden**: `potential`, `peak_age`, `decline_rate`, `injury_proneness`,
  `training_affinity`, `growth_debt`. **Never add one of these to a
  serializer.** The whole premise of the hidden-trait design is that the
  player cannot see them — a hidden trait leaking onto a screen is a
  defect, not a convenience for debugging. Look at them in Django admin
  instead.

`potential`, `peak_age` and `decline_rate` are live: `services.py` reads
them every week to grow or decline a rider's attributes, and `age`
advances once per season — see *The age curve*, below.
`injury_proneness` and `training_affinity` are still inert, waiting on
injuries ([#41](https://github.com/mario595/cycling-manager/issues/41))
and weekly training
([#36](https://github.com/mario595/cycling-manager/issues/36))
respectively. `growth_debt` is an implementation detail of the age curve,
not a game concept — see below.

The rule that *every hidden trait must be inferable* — a hidden value with
no observable consequence is an unfair dice roll, not depth — applies from
the point each trait goes live, not before. It is a bar #41 and #36 must
each clear when they land; growth/decline (#58) clears it now.

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
points), the band `specs/rider-growth-and-decline.md` promised before it
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

`riders/` knows nothing about weeks, seasons or the clock — `apply_weekly_growth(weeks)`
and `advance_ages()` are pure with respect to time; `world.services.tick()`
is what decides when to call them and how many weeks have passed. This
keeps the dependency direction in `AGENTS.md` intact: `riders/` may not
import `schedule/` or `world/`.

**Decline has no floor, and there is no retirement.** A rider can decline
indefinitely toward the bottom of the range and sit on a roster, unusable,
forever — deliberately out of scope here. See *Future work*, below.

## Generation

`generation.generate_rider()` builds one unsaved, internally consistent
rider; `generate_roster(size, team=...)` builds a squad-sized group with a
deliberate spread of quality, not a population of near-clones.

**Speciality is chosen first, and everything else follows from it** — not
the reverse. `SPECIALITY_PROFILES` weights each of the five attributes per
speciality (a Climber's `climb` weight is 1.45, its `sprint` weight 0.55),
`BUILD_PROFILES` gives each speciality a height/weight mean, and
`FIRST_NAMES`/`LAST_NAMES` (keyed by nationality — only Spain exists today)
supply a name. This order matches `specs/rider-attributes.md`'s decision
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
race history attached to them goes with them. `specs/rider-attributes.md`
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
- **A visible "what moved" summary.** Growth and decline currently surface
  only as changed numbers a player has to notice for themselves. Fold this
  into weekly training's ([#36](https://github.com/mario595/cycling-manager/issues/36))
  Training-page summary once it exists, so both weekly mechanisms report
  through one list rather than two.
