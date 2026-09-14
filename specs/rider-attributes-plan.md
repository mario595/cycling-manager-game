# Rider attributes — Implementation Plan

**Spec:** `specs/rider-attributes.md` · **Issue:** #57 · **Status:** proposed
**Apps touched:** `riders/`, `api/`, `frontend/`, `racing/` (test fixtures only)

**Amendment, during W3:** the original plan never addressed how
`generate_rider()` produces a `name` — `Rider.name` has no default, so
generation could not run without one. Stopped and asked. Decided: a small
first/last name pool in `generation.py`, combined randomly, plus a new
**`nationality`** field (real `TextChoices`, one value for now — Spain —
visible on the roster alongside speciality and age) so the name pool has
somewhere to hang and a second country is a choices-list edit later, not a
migration. This added a `nationality` row to *Data model*, a second migration
(`0003_rider_nationality.py`, added after `0002` rather than reopening it),
and `nationality`/`get_nationality_display` fields on `RiderSerializer` and
`SquadRiderSerializer`. Everything else in the plan is unchanged.

## Context you need

`riders.Rider` today is: `name`, `team` (nullable FK), `role`
(leader/support), and five `PositiveSmallIntegerField`s validated 1–100 —
`climb`, `sprint`, `flat`, `resistance`, `positioning`, listed in the module
constant `ENGINE_ATTRIBUTES`. That is the whole model. There is one migration
(`riders/migrations/0001_initial.py`) and no service layer, no generator, and
no management command — nothing outside tests has ever created a rider.

Three consumers read those five attributes and you must not disturb any of
them:

- `racing/adapters.py` — the **only** module allowed to import `race_engine`.
  `to_engine_rider` splats `ENGINE_ATTRIBUTES` into the engine's
  `RiderAttributes`. The engine is balanced against the 1–100 range across six
  audited courses; changing the stored range invalidates that.
- `racing/services.py` — `auto_pick_squad` sorts by `sum(getattr(r, name) for
  name in ENGINE_ATTRIBUTES)`.
- `api/serializers.py` — `SquadRiderSerializer` ships the five raw values to
  the squad screen.

On the frontend, `/race/:raceId` (`frontend/src/screens/Race.tsx`) is wired to
the API. `/roster` (`frontend/src/screens/Roster.tsx`) is **not** — it renders
entirely from `frontend/src/placeholderData.ts`, an invented eighteen-rider
fixture carrying fields this project has never had (`form`, `condition`,
`wage`, `value`, `status`, `years`) plus an `ovr` the spec explicitly cuts.
There is no rider endpoint in `api/urls.py`.

Repo rules this work is bound by (`AGENTS.md`):

- `riders -> core, teams`. `riders/` may not import `racing/`, `api/` or
  `world/`.
- `race_engine/` imports nothing from Django, and only `racing/adapters.py`
  imports the engine. **This feature does not touch the engine at all.**
- Postgres in dev and prod; tests are pytest, run
  `.venv/bin/python -m pytest`. Baseline before this work: **163 passing**.

## Goal

When this is done:

1. A `Rider` carries a speciality, height, weight, age, and five hidden
   traits, in addition to the five engine attributes it already has.
2. `riders.generation.generate_rider()` produces a coherent rider, and
   `generate_riders(n)` produces a deliberate spread of quality.
3. A management command replaces the existing rider population — and the race
   results and squads that pointed at it — with a generated one.
4. `GET /api/riders/?team=<id>` returns a team's roster.
5. `/roster` renders from that endpoint, showing ratings on a 0–10 scale,
   with speciality, age and build — and no overall rating anywhere.
6. The squad screen shows the same 0–10 scale.
7. The engine still receives 1–100 values and simulates exactly as before.

## Design decisions (settled — implement these, do not substitute)

1. **0–10 is a display mapping, not a stored range. Load-bearing.** The five
   attributes stay `PositiveSmallIntegerField` validated 1–100 in the
   database and stay 1–100 everywhere behind the API. The spec's "stores at a
   finer resolution than it displays" is satisfied by 1–100 stored / 0–10
   shown. **Do not add decimal columns, do not rescale the stored values, do
   not touch `ENGINE_ATTRIBUTES`.** Rescaling would invalidate the engine's
   audited six-course balance, which the spec forbids in *Out of scope*.

2. **The mapping is `round(value / 10)`, applied in the serializer, not the
   database or the frontend.** One function, `riders.display.to_display_scale`,
   called by every serializer that ships an attribute. Putting it in the
   frontend would mean two implementations (roster and squad screen) drifting
   apart; putting it in the model would hide the true value from
   `auto_pick_squad`, which must keep sorting on full precision. Note `1..4 →
   0`: a rider genuinely can show `0`, and the spec's scale is `0–10`, so this
   is correct, not a bug to clamp away.

3. **Speciality is a `TextChoices` on the model, generated from build.** Five
   values matching the frontend's existing `Speciality` union exactly:
   `Climber`, `Sprinter`, `Rouleur`, `Puncheur`, `Domestique`. Stored as the
   lowercase key, labelled with the capitalised name.

4. **Hidden traits are plain columns with no API exposure. Load-bearing.**
   `potential`, `peak_age`, `decline_rate`, `injury_proneness`,
   `training_affinity` exist on the model and are **never** added to any
   serializer. The spec's whole premise is that the player cannot see them. Do
   not add them to `RiderSerializer` "for debugging" — Django admin is where
   you look at them.

5. **`training_affinity` is a `JSONField`, not five columns.** It is a
   per-attribute weighting (`{"climb": 1.4, "sprint": 0.7, ...}`), read only by
   #36 which does not exist yet. Five columns would be five migrations to
   change when #36 discovers it wants a different shape.

6. **Generation lives in `riders/generation.py`, seeded and deterministic.**
   Every function takes an optional `rng: random.Random`. Tests pass a seeded
   instance; callers that do not care pass nothing. Without this the spread
   requirement (spec item 11) is untestable — you cannot assert on a spread you
   cannot reproduce.

7. **Attributes are generated from speciality, not the other way round.**
   Pick a speciality, pick a quality level, then draw the five attributes from
   that speciality's profile. The spec's *Rules and edge cases* says speciality
   is "a consequence of their build" and innate. Deriving speciality from
   rolled attributes would make "94 climb / 38 sprint comes out a Climber" an
   accident rather than a guarantee.

8. **Population replacement is a management command, not a data migration.
   Load-bearing.** `python manage.py reset_riders` deletes and regenerates. A
   data migration would run automatically on every deploy and on every fresh
   test database, silently destroying data; a command is explicit, requires
   `--yes` to proceed, and can be re-run. It deletes `RaceResult` and
   `RaceSquad` rows too, per the spec's *Replacing the existing population is
   destructive*.

9. **`riders/` must not import `racing/` — the command deletes through the
   reverse relations.** `Rider.objects.all().delete()` cascades to
   `RaceResult` and `RaceSquadRider` (both `on_delete=CASCADE`), and
   `RaceSquad` rows are cleaned up separately. The command is a management
   command, which `AGENTS.md` treats as an entry point — the same latitude
   `schedule/management/commands/load_season.py` takes, importing `racing`
   inside `handle()` rather than at module scope. **Import `racing.models`
   inside `handle()`, never at the top of the file.**

10. **The roster endpoint is `AllowAny`, like the squad endpoint.** Same
    reason, recorded in `api/README.md`: there is no login flow, so
    `IsAuthenticated` would make the screen invisible. It takes `?team=<id>`
    for the same reason the squad screen does. Both close in #50.

11. **`ovr`, `form`, `condition`, `wage`, `value`, `status` and `years` leave
    the frontend entirely.** The spec cuts OVR outright; the rest describe
    features that do not exist (freshness is #59, contracts and wages are
    `economy/`/`transfers/`, injury status is #41). Keeping them as fixtures
    on a screen that is now real would show the player invented numbers beside
    true ones. The roster's sort options shrink to what the data supports.

12. **`Bar` and `barColor` take 0–100 and must not be fed 0–10.
    Load-bearing.** `frontend/src/components/primitives.tsx` renders `Bar` as
    a percentage width, and `frontend/src/theme.ts`'s `barColor` thresholds at
    80/60. Passing a 0–10 value gives every rider a 10%-wide grey bar. Bars
    keep receiving `value * 10`; only the printed number uses the 0–10 figure.

## Data model

All changes are to `riders.Rider`. One migration, `riders/migrations/0002_rider_attributes.py`,
plus a second, `riders/migrations/0003_rider_nationality.py`, added when W3
turned up that `generate_rider()` has no way to name a rider without one (see
*Amendment* below).

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `speciality` | `CharField(max_length=12, choices=Speciality.choices)` | not null, not blank | `Speciality.ROULEUR` | Default exists only so the migration can apply to existing rows; generation always sets it explicitly. |
| `height_cm` | `PositiveSmallIntegerField` | not null | `178` | Validators 150–210. |
| `weight_kg` | `PositiveSmallIntegerField` | not null | `70` | Validators 45–100. |
| `age` | `PositiveSmallIntegerField` | not null | `25` | Validators 18–40. Static in this ticket; #58 advances it. |
| `potential` | `PositiveSmallIntegerField` | not null | `70` | Validators 1–100. Hidden. Ceiling attributes grow toward (#58). |
| `peak_age` | `PositiveSmallIntegerField` | not null | `27` | Validators 22–34. Hidden. |
| `decline_rate` | `PositiveSmallIntegerField` | not null | `50` | Validators 1–100. Hidden. Higher = falls away faster. |
| `injury_proneness` | `PositiveSmallIntegerField` | not null | `50` | Validators 1–100. Hidden. Read by #41. |
| `training_affinity` | `JSONField` | not null | `dict` (callable) | Hidden. `{attribute_name: float}` over `ENGINE_ATTRIBUTES`. Read by #36. |
| `nationality` | `CharField(max_length=2, choices=Nationality.choices)` | not null, not blank | `Nationality.SPAIN` | **Added by amendment, not in the original plan** — see below. Visible: shown alongside speciality/age. One value today (`ES`); the choices class exists so a second country is a choices-list + name-pool edit, not a migration surprise. |

`Speciality` is a `TextChoices` inner class on `Rider`, alongside the existing
`Role`:

```python
class Speciality(models.TextChoices):
    CLIMBER = "climber", "Climber"
    SPRINTER = "sprinter", "Sprinter"
    ROULEUR = "rouleur", "Rouleur"
    PUNCHEUR = "puncheur", "Puncheur"
    DOMESTIQUE = "domestique", "Domestique"
```

No new indexes and no new constraints. Nothing queries on these yet; adding an
index for a filter that does not exist is speculative. The roster endpoint
filters on `team`, which is already indexed as a foreign key.

Defaults are deliberately present on every field so the migration applies to
existing rows without a `RunPython` step. Those defaulted rows are then thrown
away by `reset_riders` (W6) — the defaults are migration scaffolding, not
meaningful values.

## `riders/models.py`

Add the `Speciality` choices class and the nine fields above. Extend the
module docstring note on `ENGINE_ATTRIBUTES` to say the new fields are
deliberately *not* in it.

Add one module constant beside `ENGINE_ATTRIBUTES`:

```python
#: Attributes the player sees, mapped 1-100 -> 0-10 for display only.
#: The stored value stays 1-100; see specs/rider-attributes-plan.md, decision 1.
DISPLAY_MAX = 10
```

No methods on the model. `to_display_scale` is a free function in
`riders/display.py` so that serializers can call it on a raw integer without
instantiating anything.

## `riders/display.py` (new)

```python
def to_display_scale(value: int) -> int:
    """Map a stored 1-100 attribute onto the 0-10 scale the player sees.

    Deliberately lossy: two riders at 71 and 74 both show 7. That is the
    point — see specs/rider-attributes.md, *Display scale*.
    """
```

One function. `round(value / 10)` — Python's banker's rounding is fine here;
nothing depends on the tie-break direction.

## `riders/generation.py` (new)

The heart of the feature. Four public functions:

```python
def generate_rider(
    *,
    speciality: Rider.Speciality | None = None,
    quality: int | None = None,
    age: int | None = None,
    rng: random.Random | None = None,
) -> Rider:
    """Build an unsaved, internally consistent Rider.

    `quality` is 1-100 and sets the overall level the five attributes are
    drawn around. All arguments are optional; anything omitted is rolled.
    Returns unsaved so callers can bulk_create.
    """

def generate_roster(
    size: int,
    *,
    team: Team | None = None,
    rng: random.Random | None = None,
) -> list[Rider]:
    """A squad-sized group with a deliberate spread of quality.

    Draws quality from QUALITY_SPREAD so the group contains riders worth
    building around and riders worth selling — spec item 11, and the
    property #46 depends on.
    """
```

Module-level tables, not magic numbers inline:

```python
#: Per-speciality attribute weighting. A value of 1.0 means "this rider's
#: quality, unmodified"; 0.5 means "half of it". Each row sums to roughly 5.0
#: so no speciality is globally stronger than another — only differently
#: shaped. Load-bearing: if one row sums higher, that speciality's riders win
#: races for no reason the player can see.
SPECIALITY_PROFILES: dict[str, dict[str, float]] = {...}

#: Per-speciality (height_cm, weight_kg) means. Climbers light and short,
#: sprinters heavy and tall — spec item 4.
BUILD_PROFILES: dict[str, tuple[int, int]] = {...}

#: Quality levels drawn for a generated roster, as (weight, low, high).
#: Skewed so most riders are unremarkable: a spread, not a bell curve
#: centred on "good".
QUALITY_SPREAD: list[tuple[int, int, int]] = {...}
```

Two rules the implementation must honour, both load-bearing:

- **Attributes are clamped to 1–100 after weighting.** The engine's validators
  reject anything outside that, and a `quality` of 95 times a profile weight
  of 1.4 overflows. Clamp, do not let the validator raise.
- **`potential >= max(attribute)` for a young rider, and `potential` may be
  below current attributes for an old one.** A 22-year-old whose potential is
  below where they already are is a contradiction; a 34-year-old past their
  peak having declined below their potential is exactly right. Derive
  `potential` from `quality` and `age` together, not independently.

## `api/serializers.py`

Add `RiderSerializer` — the roster's shape. Attributes pass through
`to_display_scale`; hidden traits do not appear at all:

```python
class RiderSerializer(serializers.Serializer):
    """One rider as the roster screen needs them. Attributes are the 0-10
    display scale, never the stored 1-100 — see riders/display.py. Hidden
    traits (potential, peak age, decline rate, injury proneness, training
    affinity) are deliberately absent: the player must not see them."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    role = serializers.CharField()
    speciality = serializers.CharField(source="get_speciality_display")
    nationality = serializers.CharField(source="get_nationality_display")
    age = serializers.IntegerField()
    height_cm = serializers.IntegerField()
    weight_kg = serializers.IntegerField()
    climb = serializers.SerializerMethodField()
    # ... one per ENGINE_ATTRIBUTES
```

Change `SquadRiderSerializer` the same way: its five attribute fields become
`SerializerMethodField`s through `to_display_scale`, and it gains `speciality`
and `age` so the squad screen can show them too. Its docstring's "the five
engine attributes for the manager to compare on" needs updating to say the
values are the display scale.

Generate the five method fields with a loop rather than writing five
near-identical methods by hand — `ENGINE_ATTRIBUTES` already exists to stop
the list being spelled out twice.

## `api/views.py`

```python
class RiderListView(APIView):
    """A team's roster. AllowAny with ?team=<id> for the same reason
    SquadView is — see api/README.md, *Authentication*. Closes with #50."""

    permission_classes = [AllowAny]

    def get(self, request):
        # ?team=<id> required; 400 if absent or not an integer.
        # 404 if no such team.
        # Returns riders ordered by the model's Meta.ordering (name).
```

Route in `api/urls.py`, **above** the SPA catch-all (already handled — the
whole of `api/urls.py` is included above it):

```python
path("riders/", RiderListView.as_view(), name="riders"),
```

## `frontend/src/api.ts`

Add the `Rider` interface matching `RiderSerializer`, and `fetchRiders(teamId)`.
Extend the existing `SquadRider` interface with `speciality` and `age`.

Note the name collision: `placeholderData.ts` already exports an interface
called `Rider` with a different shape. The placeholder one is being deleted
(W9), so the collision is transient — but do W9 in the same commit as the
screen rewrite to avoid a window where both exist.

## `frontend/src/useRoster.ts` (new)

Follows `useCalendar.ts` exactly, including its discipline: **render nothing
while loading or on error, never a fabricated roster.** A screen showing
invented riders mid-fetch is indistinguishable from a real roster with a bug
in it — the reasoning `frontend/README.md` records for `useSeason.ts`.

## `frontend/src/screens/Roster.tsx`

Rewrite to read from `useRoster`. What changes:

- `SQUAD`, `WAGE_BILL`, `SORT_OPTIONS`, `SPEC_FILTERS` and the `Rider` type all
  come from the API or move into this file; the `placeholderData` import goes.
- Stat tiles: `SQUAD SIZE` and `AVG AGE` stay (both derivable). `AVG OVERALL`
  and `WAGE BILL` go — decision 11.
- `RiderCard`: the 40px `ovr` badge goes. Replace it with the rider's
  speciality initial, or drop the badge and let name/speciality/age carry the
  card — implementer's choice, but no numeric overall.
- `RiderCard`'s bottom row (`FRM`/`CND` bars, contract years, wage) goes
  entirely. Replace with height/weight.
- Attribute cells print `to_display_scale`'d values but pass `value * 10` to
  `Bar` — decision 12.
- `RiderPanel`'s `facts` list loses Contract, Wage, Market value, Form,
  Condition and Overall. It gains Age, Height, Weight, Speciality.
- Sort options become: Name, Age, and the five attributes. Not "Overall".
- The speciality filter chips stay, now driven by the API's speciality values.

## `frontend/src/screens/Race.tsx`

The squad screen's attribute columns now receive 0–10 values. Check its
`ATTR_KEYS` rendering for the same `Bar`/`barColor` trap as decision 12 — if
it passes attribute values to a bar or a colour threshold, scale them.

## Work items

### W1 — `riders/models.py` + migration: the new fields — done
Add `Speciality`, the nine fields, `DISPLAY_MAX`. Generate
`riders/migrations/0002_rider_attributes.py` with `makemigrations`. Update the
`Rider` docstring.
**Test:** `riders/tests.py::test_rider_has_speciality_and_hidden_traits` — create a
`Rider` with only the old fields and assert the new ones take their defaults;
assert `speciality` rejects a value outside the choices via `full_clean`.
Suite stays green because every new field has a default.

### W2 — `riders/display.py`: the 0–10 mapping — done

*Note: the plan named `riders/tests.py` for W2's test but `riders/tests/test_generation.py`
and `riders/tests/test_reset_riders.py` for W3/W4/W6 — Django cannot have both
`riders/tests.py` and `riders/tests/`. Resolved by converting to a `tests/`
package in W2, matching `world/`'s existing convention, with a shared
`conftest.py` for the `team`/`rider` fixtures. Actual location:
`riders/tests/test_display.py::test_to_display_scale`.*

**Test:** `riders/tests.py::test_to_display_scale` — table-driven:
`1 → 0`, `4 → 0`, `5 → 0` *(banker's rounding — assert whatever the
implementation actually does and write it down)*, `50 → 5`, `94 → 9`,
`100 → 10`. **Load-bearing:** assert `71` and `74` both give `7`, which is the
spec's "two riders can look identical" property.

### W3 — `riders/generation.py`: `generate_rider`
Profiles, build, age, quality, hidden traits, clamping.
**Tests:** `riders/tests/test_generation.py` —
`test_generated_rider_is_valid` (`full_clean()` passes on 200 seeded riders —
this is the clamping test),
`test_climber_climbs_and_is_light` (a forced `CLIMBER` has `climb` as its
highest attribute and `weight_kg` below the sprinter mean),
`test_generation_is_deterministic` (same seed, identical riders),
`test_young_rider_potential_is_above_current` (a forced age of 21 never has
`potential` below its best attribute).

### W4 — `riders/generation.py`: `generate_roster`
**Tests:** `test_roster_has_a_spread` — generate 12 seeded riders and assert
the gap between best and worst total-attributes exceeds a threshold, so the
group is not clones. **This is the test that protects #46's requirement**; if
it is weak, #46 inherits a flat roster. `test_roster_size_and_team` — all
riders get the team, count matches.

### W5 — `riders/admin.py`: show the new fields
`list_display` gains speciality and age; `list_filter` gains speciality;
hidden traits go in a collapsed fieldset so they are inspectable without being
prominent.
**Test:** none — admin config with no logic. Say so in the commit message
rather than writing a test that asserts a tuple's contents.

### W6 — `riders/management/commands/reset_riders.py` (new): population replacement
Requires `--yes`. Deletes `RaceResult`, `RaceSquad` (and cascaded
`RaceSquadRider`) and all `Rider` rows, then generates a roster per team.
`--per-team` defaults to 12, matching #46. Imports `racing.models` **inside
`handle()`** — decision 9.
**Tests:** `riders/tests/test_reset_riders.py` —
`test_refuses_without_yes` (no rows deleted, non-zero exit),
`test_replaces_population` (old riders gone, each team has `--per-team`
riders, old `RaceResult` rows gone).

### W7 — `api/serializers.py`: `RiderSerializer`, and `SquadRiderSerializer` on the display scale
**Tests:** `api/tests.py::test_rider_serializer_uses_display_scale` (a rider
with `climb=94` serializes to `9`), `test_rider_serializer_hides_traits`
(**load-bearing** — assert `potential`, `peak_age`, `decline_rate`,
`injury_proneness`, `training_affinity` are all absent from the payload
keys), and an update to the existing squad-endpoint tests for the new scale.

### W8 — `api/views.py` + `api/urls.py`: `GET /api/riders/?team=<id>`
**Tests:** `api/tests.py::test_rider_list_returns_team_roster`,
`test_rider_list_requires_team_param` (400), `test_rider_list_unknown_team`
(404).

### W9 — `frontend/`: roster screen on real data, placeholder rider data deleted
`api.ts`, `useRoster.ts`, `Roster.tsx`, and the removal of the rider half of
`placeholderData.ts` (`Rider`, `RiderSeed`, `RIDER_SEEDS`, `SQUAD`,
`SPEC_FILTERS`, `SortKey`, `SORT_OPTIONS`, `WAGE_BILL`). **`Roster.tsx` is the
only consumer of those symbols** — verified: `Dashboard.tsx` imports
`DASHBOARD`, `FORM_WATCH`, `HEADLINE_STATS`, `INBOX`, `LEAGUE_TABLE`,
`NEXT_RACE` and `RESULTS`, none of which touch `SQUAD` (`FORM_WATCH` is its own
literal list), and `Layout.tsx`/`Sidebar.tsx` import only `TEAM`. So the
deletion is contained; the rest of `placeholderData.ts` stays.
**Test:** `npm run build` and the browser verification below. There is no
frontend test runner in this project; do not add one as part of this ticket.

### W10 — `frontend/src/screens/Race.tsx`: squad screen on the display scale
Whatever W7 changed under it, plus the `Bar`/`barColor` scaling check.
**Test:** browser verification.

## Execution order

W1 → W2 → W3 → W4 before anything else: the model and the generator are what
everything downstream needs, and they are testable with no API and no
frontend. W3 before W4 because a roster is a loop over riders — proving one
rider is coherent is a smaller failure surface than proving twelve have a
spread.

W5 and W6 next. W6 needs W4, and it is the first point where you can look at
real generated riders in the admin — do that before building an API on top of
them. **Commit here and run `reset_riders` against your dev database**; every
screen from this point needs real rows to render.

W7 → W8: serializer before view, so the view's tests are asserting on a shape
that is already proven.

W9 → W10 last. Both are frontend-only and neither can be verified until the
endpoint exists.

Commit after every work item. The suite stays green throughout — W1's
defaults are what make that true for the migration.

## Documentation update (required, not optional)

- **`riders/README.md` — new file, and `AGENTS.md`'s table updated to mark
  it.** The app currently has none. It must cover: what `Rider` holds and the
  visible/hidden split; why 1–100 is stored and 0–10 displayed, and that
  `to_display_scale` is the single mapping; why the hidden traits exist while
  nothing reads them (pointing at #58, #41, #36); how generation works and
  why speciality precedes attributes; that `SPECIALITY_PROFILES` rows sum to
  roughly the same total and why; and `reset_riders` being destructive by
  design, including what it deletes.
- **`AGENTS.md`** — the Game Domains table's `riders/` row changes from
  "**built** (model only)" to "**built**, `README.md`", and its description
  drops "Generation, aging, form, injury still to come" in favour of naming
  what is now there and what #58/#59 still own.
- **`api/README.md`** — *What exists* gains the riders endpoint, with the same
  `AllowAny`/`?team=` caveat the squad endpoint carries and a pointer to #50.
- **`frontend/README.md`** — the route table's `/roster` row changes from
  "fixture data" to API-backed; *Where the data comes from* must say
  `placeholderData.ts` no longer holds riders, and that the Dashboard is now
  the main fixture consumer.
- **`racing/README.md`** — only if W7's squad-screen change alters anything
  documented under *Squads*. Check; do not edit reflexively.

## Verification

```bash
.venv/bin/python -m pytest                      # expect > 163 passing
.venv/bin/python manage.py makemigrations --check --dry-run   # no drift
.venv/bin/python manage.py reset_riders --yes
cd frontend && npm run build
```

Then, with the dev server running, in the browser:

1. `/roster` — riders render with speciality, age, height/weight. **Every
   attribute number is 0–10 and every bar is proportional.** A page of bars
   all pinned near-empty is decision 12's failure, visible at a glance.
2. `/roster` — no "Overall" anywhere: not the badge, not the sort chips, not
   the detail panel.
3. `/race/:raceId` — the squad screen's attributes are also 0–10, and picking
   and saving a squad still works.
4. `curl 'localhost:8000/api/riders/?team=1' | python -m json.tool` — confirm
   with your own eyes that `potential`, `peak_age`, `decline_rate`,
   `injury_proneness` and `training_affinity` are **not** in the payload.

**The likeliest failure mode is the hidden traits leaking into the API** —
`RiderSerializer` is the one place where a `ModelSerializer` with
`fields = "__all__"` would be the natural shortcut and would expose every
hidden trait at once. W7's `test_rider_serializer_hides_traits` is the test
that catches it, and step 4 above is the manual check. A test asserting the
visible fields are present would pass in the leaking case and prove nothing —
assert on **absence**.

Second likeliest: `makemigrations --check` drifting because `JSONField`'s
default must be the callable `dict`, not `{}`. Django flags a mutable default
and the migration will not be stable until it is a callable.

## Risks

| Risk | Mitigation |
|---|---|
| Hidden traits exposed through a `ModelSerializer` shortcut | Explicit `serializers.Serializer` with fields listed one by one (decision 4); W7 asserts absence, not presence |
| 0–10 values fed to `Bar`/`barColor`, which expect 0–100 | Decision 12; browser step 1 catches it immediately — the whole page looks wrong |
| Someone "fixes" the display by rescaling stored values, breaking the engine's audited balance | Decision 1 states it and `riders/README.md` records it; `racing/` tests would fail but the reason would be non-obvious, hence the doc |
| Speciality profiles that do not sum evenly, making one speciality quietly superior | Stated as load-bearing in `generation.py`'s docstring and in `riders/README.md`; keep rows summing to ~5.0 |
| `reset_riders` run against real data later, when there is some | `--yes` required, and the command's help text and README entry both say it is destructive. Revisit when #50 ships real accounts |
| Attribute values escaping 1–100 after profile weighting | Clamp in `generate_rider`; W3's `test_generated_rider_is_valid` runs `full_clean()` over 200 riders |
| Frontend `Rider` name collision between `api.ts` and `placeholderData.ts` | W9 does the rewrite and the deletion in one commit |

## Open questions

None blocking. Two things deliberately settled rather than asked:

- The spec's open question about **where the player learns how ageing works**
  does not block this ticket — nothing ages yet. It belongs with #58 and the
  rider detail screen.
- **`age` is a plain integer, not a birth date.** #58 will advance it once per
  season. A birth date would need a game-calendar epoch to be meaningful and
  `schedule/` does not expose one; an integer is what the spec describes and
  is trivially incrementable.
