# Riders — the roster asset

## What this app owns

`Rider` — persisted riders mirroring the race engine's attributes, plus
everything the engine does not know about: speciality, build, age, and a set
of currently-inert hidden traits. Generation (`generation.py`), the display
mapping (`display.py`), and the `reset_riders` management command. Not
squads or race results (`racing/`), not the race simulation itself
(`race_engine/`).

## Visible vs hidden

Every rider carries two kinds of attribute:

- **Visible**: `speciality`, `nationality`, `height_cm`, `weight_kg`, `age`,
  and the five engine attributes (`climb`, `sprint`, `flat`, `resistance`,
  `positioning`). These are what `api.RiderSerializer` and
  `api.SquadRiderSerializer` ship to the player.
- **Hidden**: `potential`, `peak_age`, `decline_rate`, `injury_proneness`,
  `training_affinity`. **Never add one of these to a serializer.** The
  whole premise of `specs/rider-attributes.md` is that the player cannot
  see them — a hidden trait leaking onto a screen is a defect, not a
  convenience for debugging. Look at them in Django admin instead.

As of this ticket ([#57](https://github.com/mario595/cycling-manager/issues/57))
the hidden traits are generated and stored, but **nothing reads them yet**.
They exist so a rider generated today does not need regenerating when a
later feature starts reading one:

- `potential`, `peak_age`, `decline_rate` become live in growth/decline
  ([#58](https://github.com/mario595/cycling-manager/issues/58)).
- `injury_proneness` becomes live in injuries
  ([#41](https://github.com/mario595/cycling-manager/issues/41)).
- `training_affinity` becomes live in weekly training
  ([#36](https://github.com/mario595/cycling-manager/issues/36)).

`specs/rider-attributes.md`'s rule that *every hidden trait must be
inferable* — a hidden value with no observable consequence is an unfair
dice roll, not depth — applies from the point each trait goes live, not
before. It is a bar #58/#41/#36 must each clear, not one this ticket claims
to meet.

## Display scale: stored 1-100, shown 0-10

The five engine attributes are stored 1-100 — the same range the engine
validates and the same range its six bundled courses are balanced against.
**That range never changes.** What the player sees is coarser: `display.
to_display_scale(value)` maps it onto 0-10 with `round(value / 10)`, and it
is the **only** place that mapping happens. Every serializer that ships an
attribute calls it; nothing else should reimplement it.

This is deliberate lossiness, not a rounding bug: two riders at 71 and 74
both show 7, so the roster cannot offer a meaningful sort on a raw attribute
number, and growth (once #58 lands) arrives as an occasional visible jump
rather than a number that visibly creeps every week. See
`specs/rider-attributes.md`, *Display scale*.

**Do not rescale the stored values to make display simpler.** A stored
range change invalidates the verified realism balance across all six
bundled courses (`race_engine/README.md`) and requires re-deriving it —
that cost is exactly why the display scale exists as a read-time mapping
instead.

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

- **Role assignment.** `generate_rider` never sets `role`; every generated
  rider defaults to `Rider.Role.LEADER`. Squad selection
  (`racing.services.auto_pick_squad`) still works — it sorts on total
  attributes, not on this field — but a generated roster reading as "twelve
  leaders" is not addressed by this ticket. Revisit if it turns out to
  matter in play.
- **A second nationality.** `Rider.Nationality` and the name pools in
  `generation.py` are structured as one entry per country specifically so
  that adding one is a choices-list and name-pool edit, not a migration or
  a `generate_rider` signature change.
