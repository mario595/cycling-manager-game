# Squad selection — Implementation Plan

**Spec:** `specs/squad-selection.md` · **Issue:** [#37](https://github.com/mario595/cycling-manager/issues/37) · **Status:** proposed
**Apps touched:** `racing/`, `api/`, `frontend/`, `race_engine/` (one validation move)

## Context you need

Today a race simulates **every rider in the database**, on both sides of the
seam. `racing/services.py:simulate_race` does this explicitly:

```python
db_riders = list(Rider.objects.select_related("team"))
# Every rider in the database races: there is no squad selection yet
# (#37) and no calendar to say who is entered. This is a deliberate
# placeholder, not an oversight.
```

This feature replaces that line. After it, a race's field is the union of every
team's four selected riders, and a rider not selected does not appear in the
log, the results, or the replay.

### What already exists

| Thing | Where | What it gives you |
|---|---|---|
| `Race` — `name`, `course` JSON, `starts_at`, `status`, `week` | `racing/models.py` | The race a squad is picked for. `status` is `scheduled` / `running` / `finished` / `failed`. |
| `Team` — `name`, `code`, `manager` (nullable), colours | `teams/models.py` | `manager is None` means AI-controlled; `Team.riders` is the reverse of `Rider.team`. |
| `Rider` — five engine attributes plus `team` and `role` | `riders/models.py` | `role` is `leader` / `support`, **persisted on the rider**. This feature makes that field redundant for racing; see decision 4. |
| `simulate_race(race, *, game_time)` | `racing/services.py` | Runs the engine, writes the log through Django storage, writes `RaceResult` rows, flips the race to `finished`. |
| `to_engine_rider` / `to_engine_course` / `to_team_codes` / `run_race_via_adapter` | `racing/adapters.py` | The **only** module allowed to import `race_engine`. |
| `tick()` | `world/services.py` | Claims due races and calls `simulate_race`. Untouched by this plan. |
| `/api/world/clock/`, `/api/schedule/position/`, `/api/schedule/calendar/` | `api/` | The three existing endpoints. All `AllowAny`. |
| `Calendar` screen, `useCalendar`, `raceStatusLabel` | `frontend/src/` | The list this feature's screen is reached from. |

### This plan assumes #7 has landed

[#7](https://github.com/mario595/cycling-manager/issues/7) (race calendar) is
**finished on the `worktree-race-calendar` branch but not merged to master**.
Do not start this until its PR is merged. The exact surface consumed here:

| From #7 | Used here for |
|---|---|
| `Race.race_day` and the `one_race_per_day_per_week` constraint | Nothing directly — but `racing/models.py` differs from master, so branch off the merged result, not master. |
| `GET /api/schedule/calendar/` returning `weeks[].races[]` with `id`, `name`, `starts_at`, `status` | The calendar rows this feature makes clickable. |
| `frontend/src/screens/Calendar.tsx`, `useCalendar.ts`, `raceStatus.ts` | The screen the race link is added to, and the status vocabulary reused. |

### Repo rules this work is bound by

- **`race_engine/` imports nothing from Django, ever.** `racing/adapters.py` is
  the only importer of the engine. `AGENTS.md`, and `racing/README.md`'s *The
  core rule*.
- **Dependency direction:** `racing -> riders, teams, race_engine, schedule`.
  `racing/` may **not** import `world/`; `api/` may import everything.
- **Postgres in dev and prod**, tests are pytest via `.venv/bin/python -m pytest`.
- **Race logs are records, not build output.** Nothing here regenerates one.
- Frontend styling is **inline `style={{}}`**, colours from `src/theme.ts`,
  never hex literals in components.

## Goal

When this is done:

1. A `RaceSquad` row records, per `(race, team)`, exactly four riders and
   exactly one leader among them.
2. A manager can read and replace their team's squad for any `scheduled` race
   over the API, and does so from a new race screen in the SPA.
3. Opening a race with no squad yet returns a pre-filled suggestion — the
   team's last used squad, or a naive auto-pick when there is none.
4. `simulate_race` races **only** the riders in the race's squads, with each
   rider's role taken from the squad row and not from `Rider.role`.
5. A team with no squad when the race starts gets one auto-picked at claim
   time, so it still starts.
6. A `running` or `finished` race's squads are readable but not writable.

## Design decisions (settled — implement these, do not substitute)

### 1. One row per rider per race per team, not a JSON list on a squad row

`RaceSquad` is `(race, team)` and holds nothing but the pair; `RaceSquadRider`
is `(squad, rider, is_leader)`. Four rows per team per race.

**Do not** store the four rider ids as a JSON array on `RaceSquad`. The
selection is joined against on the hot path — `simulate_race` needs every
selected rider for a race with their attributes in one query — and a JSON array
of ids means either N+1 lookups or a manual `id__in` reassembly. Rows also give
you the `UniqueConstraint` that stops the same rider being entered twice, which
JSON cannot express.

**Load-bearing:** the leader flag lives on the *join row*, not on `RaceSquad` as
a `leader = FK(Rider)`. A leader FK pointing at a rider who is not in the squad
is representable and would have to be validated separately; `is_leader` on the
membership row cannot be.

### 2. Exactly-four and exactly-one-leader are enforced in a service, not by a database constraint

Postgres cannot express "this parent has exactly four children" without a
trigger or a denormalised counter. Both are more machinery than this earns.

`racing/services.py:set_squad(race, team, rider_ids, leader_id)` is the **only**
sanctioned writer. It validates, then replaces the whole squad inside one
`transaction.atomic()`. The admin gets an inline that can violate the rule —
accepted, documented in `racing/README.md`, and the reason the *simulation* also
checks (decision 6) rather than trusting the data.

**Do not** make this a `Model.clean()` on `RaceSquad`: `clean()` runs before the
children exist on a fresh insert, so it can only ever see a squad that is
already saved. The rule is about a set of rows, so it belongs to the operation
that writes the set.

### 3. Replace-whole-squad, never partial edits

The writer deletes every existing `RaceSquadRider` for that `(race, team)` and
inserts the new four. There is no "add rider" or "swap rider" endpoint: the
screen holds the whole selection in local state and PUTs it. A partial API
would need a validity story for exactly the intermediate states the spec says
cannot be saved — three riders, two leaders — so it does not exist.

### 4. `Rider.role` stays, but the simulation stops reading it

`Rider.role` is the rider's *default* disposition and stays on the model: it is
what the naive auto-pick sorts on, what the admin shows, and what the roster
screen displays. **The engine's per-race role now comes from
`RaceSquadRider.is_leader`.**

`racing/adapters.py:to_engine_rider` therefore takes an explicit role:

```python
def to_engine_rider(rider: DBRider, *, role: str | None = None) -> EngineRider:
    ...
    role=role if role is not None else rider.role,
```

The default keeps the existing three adapter tests passing unchanged.

**Do not** delete `Rider.role` or migrate it away. It is not dead — it is the
seed for the auto-pick, and removing it means the auto-pick has nothing to
prefer.

### 5. The auto-pick is deliberately naive, and it is one function used by three callers

`racing/services.py:auto_pick_squad(team) -> tuple[list[int], int]` returns four
rider ids and the leader's id. The rule, in full:

> Order the team's riders by `role == leader` first, then by the sum of the five
> engine attributes descending, then by `pk` ascending. Take the first four. The
> leader is the first of those four.

The `pk` tiebreak is what makes it deterministic, which is what makes it
testable. No course awareness — the spec's *Out of scope* assigns that to #45,
and the whole point of item 9 is that a deliberate choice beats this one.

Three callers: the pre-fill when a team has no previous squad, the API's
suggestion, and the claim-time fallback. **One function**, and that is
load-bearing beyond this ticket: `specs/roadmap.md`'s Phase 3 states that
[#44](https://github.com/mario595/cycling-manager/issues/44) and
[#39](https://github.com/mario595/cycling-manager/issues/39) "are one mechanism,
not two … two implementations will disagree, and the disagreement surfaces
mid-race", with this feature's manager choice as the interesting path and the
default as the fallback. `auto_pick_squad` and `ensure_squads` are that
mechanism. When #44 and #39 land, they replace the *rule inside*
`auto_pick_squad` — they do not add a second entry point beside it.

### 6. The engine's one-leader-per-team rule moves out of `config.py` and is applied on the Django path too

`race_engine/config.py:_validate_team_leaders` today runs only from
`load_config` — i.e. only for standalone JSON runs. The Django path builds
`EngineRider`s in `adapters.py` and **never calls it**, so a malformed field
reaches `run_race`, where a team with two leaders has undefined role-scaled
tactics and a team with none has nobody to protect.

Move it to `race_engine/models.py` — it takes `list[Rider]` and raises, with no
config parsing in it — and call it from **both** `load_config` and `run_race`.
Existing callers catch `ConfigError`, which lives in `config.py`, so define a
plain `ValueError` subclass in `models.py` and have `ConfigError` subclass it.

In `race_engine/models.py`:

```python
class RaceSetupError(ValueError):
    """A field of riders the simulation cannot run — e.g. a team without
    exactly one leader. Raised by run_race, and by load_config via
    ConfigError, which subclasses this."""


def validate_team_leaders(riders: list[Rider]) -> None:
    ...  # body moved verbatim from config._validate_team_leaders,
         # raising RaceSetupError instead of ConfigError
```

and in `race_engine/config.py`:

```python
class ConfigError(RaceSetupError):
    ...
```

**This is still Django-free.** It is a pure-Python change inside the engine, and
it is the load-bearing one in this plan: without it, an invalid squad reaching
the simulation produces a silently wrong race rather than a failure.

### 7. A team with no squad at claim time gets one, and it is written down

`simulate_race` calls `ensure_squads(race)` before building the field. For every
team that has riders but no `RaceSquad` for this race, it writes one from
`auto_pick_squad`. Rows, not an in-memory list — the spec's item 10 says a
finished race shows who rode, forever, and that only works if the auto-picked
squad is as real as a chosen one.

A team with **fewer than four riders** is skipped, with a warning logged. The
spec calls a roster below four "a broken game state" and places the fix on
whichever ticket lets riders leave a roster — so this must not crash the tick
for every other team in the race.

### 8. Identity is deferred to #50: the team id goes in the URL

`GET|PUT /api/racing/races/<race_id>/squads/<team_id>/`, `AllowAny`, matching
every other endpoint in `api/`.

**This is a known, deliberate hole: anyone can edit anyone's squad.** Squad
selection is inherently per-manager, but there is no login flow in the SPA and
no way for it to know which team is "mine" — `api/README.md`'s *Authentication*
already records the symptom.

The fix has a ticket: [#50](https://github.com/mario595/cycling-manager/issues/50)
(register, log in, log out). `specs/roadmap.md` places it in **Phase 4, two
phases after this one**, and gives the reason: registration ends in *claiming an
unmanaged team*, so #50 depends on #44 and #46 existing first. The roadmap is
explicit that "the phases before this run fine on a superuser account. That is
not a compromise — a single-manager world is exactly what Phases 1–3 are
testing."

So the hole is not a stopgap awaiting an imminent fix; it is the deliberate
shape of the game until Phase 4. That argues *for* the team-in-the-URL form
rather than against it — anything more elaborate would be building against
requirements #46 has not settled yet. What changes when #50 lands:

- `<team_id>` becomes `request.user.team`; the URL loses a segment.
- `permission_classes` drops back to the project default `IsAuthenticated`.
- The frontend's `?team=` query parameter disappears.

Nothing else about these views, the serializers or the services moves. Do not
anticipate #50 further than that — its open questions (username or email, open
or invite-only, what a claim hands over) are unanswered, and guessing at them
here produces work that has to be undone.

**CSRF:** DRF's `SessionAuthentication` enforces CSRF only for *authenticated*
sessions, so an anonymous `PUT` from the SPA passes `CsrfViewMiddleware`
untouched. Do not add a CSRF token dance to the frontend; do not add
`@csrf_exempt` either. #50 lists "CSRF handling for the SPA needs settling" as a
parked technical concern — this is the first write endpoint that makes it
concrete, so record it in `api/README.md` next to the identity hole. Both close
in #50.

### 9. The screen builds only what the spec covers

The design export (`design/Cycling Manager UI.dc.html`, *Race day* screen) shows
a squad panel with things this feature does not have:

| In the design | Status here |
|---|---|
| 8 riders per squad | **No** — the spec fixes four. Use four. |
| Per-rider suitability score, sorted by it | **No** — course-aware assessment is #45. Sort by the same order `auto_pick_squad` uses. |
| `INJURED` / `FATIGUED` notes and disabled rows | **No** — injuries are #41. Every rider is selectable. |
| Terrain, temperature, wind, rain, climb count, tier, winner points facts | **No** — none of these exist on `Race`. Show name, date, distance and status. |
| Course profile SVG | **No** — not in this spec. `frontend/src/courseProfile.ts` exists but is fed placeholder data. |
| Final classification table for a past race | **No** — results rendering is not in this spec. |
| Checkbox rows, ★-to-set-leader, a leader summary block, an `n/N selected` count, a CTA disabled until valid | **Yes** — this is the spec's items 3, 4 and the widget itself. Take the interaction and the visual language from the design and drop the data it depends on. |

Reuse `color`, `font`, `radius` from `src/theme.ts` and the `Card`,
`CardHeader`, `PageBody`, `PageHeading`, `Button` primitives. Do not add hex
literals.

## Data model

Two new models in `racing/models.py`, one migration:
`racing/migrations/0005_racesquad.py`.

### `RaceSquad(TimeStampedModel)`

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `race` | `FK(Race, on_delete=CASCADE, related_name="squads")` | no | — | Deleting a race deletes its squads; a race's squads have no meaning without it. |
| `team` | `FK("teams.Team", on_delete=CASCADE, related_name="race_squads")` | no | — | String reference, so `racing/models.py` gains no import of `teams/` — same convention as `Race.week`. |
| `is_auto_picked` | `BooleanField` | no | `False` | True when written by `ensure_squads` or `auto_pick_squad`, false when a manager saved it. Read by nothing yet; it is what makes "did the manager actually choose?" answerable for #39 and for balance work. |

```python
class Meta:
    constraints = [
        models.UniqueConstraint(fields=["race", "team"], name="one_squad_per_team_per_race"),
    ]
    indexes = [
        models.Index(fields=["team", "race"], name="squad_team_race_idx"),
    ]
```

The index is for the "previous squad" lookup, which filters by team and orders
by the race's `starts_at`.

### `RaceSquadRider(models.Model)`

Not a `TimeStampedModel`: these rows are written and deleted as a set by
`set_squad`, never individually amended, so per-row audit columns are noise —
the same reasoning `schedule.Week` records.

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `squad` | `FK(RaceSquad, on_delete=CASCADE, related_name="members")` | no | — | |
| `rider` | `FK("riders.Rider", on_delete=CASCADE, related_name="squad_entries")` | no | — | String reference, as above. |
| `is_leader` | `BooleanField` | no | `False` | Exactly one per squad — enforced in `set_squad`, not by the database (decision 2). |

```python
class Meta:
    constraints = [
        models.UniqueConstraint(fields=["squad", "rider"], name="unique_rider_per_squad"),
    ]
```

`SQUAD_SIZE = 4` is a module-level constant in `racing/models.py`. It is
imported by the services, the serializers and the tests, so the number appears
once. Do not inline `4`.

### What is *not* added

No field on `Race` for "squads locked" — lockedness is `Race.status != scheduled`,
derived, the same way `schedule/` refuses to store a "current season" pointer.

## racing/models.py

Add `SQUAD_SIZE`, `RaceSquad`, `RaceSquadRider` as above. No change to `Race`,
`RaceLog` or `RaceResult`.

## racing/services.py

`SquadError` plus five functions, and a rewrite of the field-building lines
in `simulate_race`.

```python
class SquadError(ValueError):
    """An invalid squad: wrong size, a rider from another team, or not
    exactly one leader. Raised by set_squad and turned into a 400 by the
    API."""


def auto_pick_squad(team: Team) -> tuple[list[int], int]:
    """Four rider ids and the leader's id, chosen naively.

    Leaders first, then by total engine attributes descending, then by pk
    ascending — the pk tiebreak is what makes this deterministic and so
    testable. Deliberately course-blind: see specs/squad-selection.md,
    Out of scope, and #45.

    Raises SquadError if the team has fewer than four riders.
    """


def previous_squad(team: Team, before: Race) -> tuple[list[int], int] | None:
    """The riders and leader from this team's most recent squad in a race
    starting before `before`, or None if there is not one.

    "Most recent" is by the race's starts_at, descending. Riders no longer
    on the team are dropped, so a squad short of four after filtering
    returns None and the caller falls back to auto_pick_squad.
    """


def suggested_squad(race: Race, team: Team) -> tuple[list[int], int]:
    """What to pre-fill a manager's screen with: their existing squad for
    this race if they have one, else their previous squad, else an
    auto-pick. Reads only; writes nothing."""


def set_squad(race: Race, team: Team, rider_ids: list[int], leader_id: int) -> RaceSquad:
    """Replace `team`'s squad for `race`. The public writer — everything a
    manager does goes through here.

    Refuses a race that is not SCHEDULED, then delegates to _write_squad.
    Raises SquadError for that and for every validation failure below.
    """
```

### The writer is split in two, and this is the trap in the plan

`set_squad` refuses a race that is not `SCHEDULED` — the spec's item 10. But
`ensure_squads` (decision 7) runs *inside* `simulate_race`, by which point the
tick has already flipped the race to `RUNNING`. So the guard and the write have
to be separable:

- **`_write_squad(race, team, rider_ids, leader_id, *, auto)`** — validation and
  the write, no status check.
- **`set_squad(...)`** — the status check, then `_write_squad`. The public
  writer; everything a manager does goes through it.
- **`ensure_squads`** calls `_write_squad` directly.

**Do not** solve this with a `force=True` flag on `set_squad`. A flag that
disables the one rule protecting a started race is a flag someone will pass by
mistake, and the mistake is invisible.

`_write_squad`'s body, where getting it wrong is likely:

```python
def _write_squad(race, team, rider_ids, leader_id, *, auto):
    ids = list(dict.fromkeys(rider_ids))
    if len(ids) != len(rider_ids):
        raise SquadError("a rider cannot be entered twice")
    if len(ids) != SQUAD_SIZE:
        raise SquadError(f"a squad is exactly {SQUAD_SIZE} riders, got {len(ids)}")

    riders = list(Rider.objects.filter(pk__in=ids, team=team))
    if len(riders) != SQUAD_SIZE:
        raise SquadError("every rider in a squad must be on the team")
    if leader_id not in ids:
        raise SquadError("the leader must be one of the selected riders")

    with transaction.atomic():
        squad, _ = RaceSquad.objects.update_or_create(
            race=race, team=team, defaults={"is_auto_picked": auto},
        )
        squad.members.all().delete()
        RaceSquadRider.objects.bulk_create([
            RaceSquadRider(squad=squad, rider=r, is_leader=r.pk == leader_id)
            for r in riders
        ])
    return squad
```

**Load-bearing:** `filter(pk__in=ids, team=team)` does the "on the team" check
and the "exists" check in one query. Fetching by `pk__in` alone and comparing
`rider.team_id` afterwards is the version that misses a rider id that does not
exist at all.

### `ensure_squads`, called at the top of `simulate_race`

```python
def ensure_squads(race: Race) -> None:
    """Give every team with enough riders a squad for this race, if it has
    not got one. Called from simulate_race so a team whose manager never
    chose still starts — specs/squad-selection.md, in scope item 8.

    A team with fewer than SQUAD_SIZE riders is skipped with a warning, not
    an exception: that is a broken roster (see the spec's Rules and edge
    cases) and it must not stop every other team racing.
    """
    have = set(RaceSquad.objects.filter(race=race).values_list("team_id", flat=True))
    for team in Team.objects.exclude(pk__in=have):
        try:
            rider_ids, leader_id = auto_pick_squad(team)
        except SquadError as exc:
            logger.warning("no squad for %s in %s: %s", team, race, exc)
            continue
        _write_squad(race, team, rider_ids, leader_id, auto=True)
```

`racing/` has no logger today — add `logger = logging.getLogger(__name__)` at
module scope. It also does not import `teams/` yet; `from teams.models import
Team` is new here and allowed (`racing -> teams` is in `AGENTS.md`'s graph).

### The change inside `simulate_race`

Replacing the `db_riders` block and its "every rider in the database races"
comment:

```python
    ensure_squads(race)

    members = list(
        RaceSquadRider.objects
        .filter(squad__race=race)
        .select_related("rider", "squad__team")
    )
    if not members:
        raise ValueError("no squads to race")

    db_riders = [m.rider for m in members]
    engine_riders = [
        to_engine_rider(m.rider, role="leader" if m.is_leader else "support")
        for m in members
    ]
    teams = list({m.squad.team.pk: m.squad.team for m in members}.values())
```

Everything downstream — `by_pk`, `finishers`, the `RaceResult` rows — is
unchanged, because `db_riders` still holds exactly the riders the engine saw.

## racing/adapters.py

One signature change, per decision 4:

```python
def to_engine_rider(rider: DBRider, *, role: str | None = None) -> EngineRider:
```

with `role=role if role is not None else rider.role` in the constructed
`EngineRider`. Update the module docstring's note about roles if it has one; it
does not today.

## race_engine/models.py and race_engine/config.py

Per decision 6. Move `_validate_team_leaders` to `models.py` as
`validate_team_leaders`, add `RaceSetupError`, call it from `run_race` before
`RaceState.create_initial_state`, and make `ConfigError` subclass
`RaceSetupError`. `config.load_config` keeps calling it — import the moved
function rather than keeping a copy.

The engine's 49 tests must still pass, and `race_engine/README.md`'s *Config
format* section says the rule is a `load_config` rule — that sentence needs
widening to say it now also applies to any direct `run_race` call.

## racing/admin.py

Register `RaceSquad` with a `RaceSquadRider` inline, read-mostly. Add a comment
saying the admin can create an invalid squad and that `set_squad` is the
sanctioned writer — the admin exists for inspection, not for play.

## api/serializers.py

```python
class SquadRiderSerializer(serializers.Serializer):
    """One rider as the squad screen needs them: identity, the five engine
    attributes for the manager to compare on, and whether they are in the
    squad and leading it."""
    id = serializers.IntegerField()
    name = serializers.CharField()
    role = serializers.CharField()          # the rider's default, not the squad's
    climb = serializers.IntegerField()
    sprint = serializers.IntegerField()
    flat = serializers.IntegerField()
    resistance = serializers.IntegerField()
    positioning = serializers.IntegerField()
    selected = serializers.BooleanField()
    is_leader = serializers.BooleanField()


class SquadSerializer(serializers.Serializer):
    race = serializers.IntegerField()
    race_name = serializers.CharField()
    race_status = serializers.CharField()
    starts_at = serializers.DateTimeField(allow_null=True)
    distance_km = serializers.FloatField()
    team = serializers.IntegerField()
    team_name = serializers.CharField()
    editable = serializers.BooleanField()
    saved = serializers.BooleanField()      # False when this is a suggestion
    squad_size = serializers.IntegerField()
    candidates = SquadRiderSerializer(many=True)


class SquadWriteSerializer(serializers.Serializer):
    rider_ids = serializers.ListField(child=serializers.IntegerField())
    leader_id = serializers.IntegerField()
```

`candidates` is the team's **whole roster**, each flagged `selected` /
`is_leader`: one request gives the screen everything it draws. A `PUT` returns
the same shape as the `GET`, so the screen re-renders from what it got back.

`distance_km` repeats `_race_payload`'s `sum(s["length"] for s in race.course)
/ 1000` from #7's calendar view — factor it into a shared helper in
`api/views.py` rather than writing it twice.

## api/views.py

```python
class SquadView(APIView):
    """A team's squad for one race — read it, replace it.

    Public and team-id-in-the-URL, deliberately: there is no login flow in
    the SPA, so anyone can edit anyone's squad. See api/README.md,
    *Authentication*. When login lands, <team_id> becomes request.user.team
    and this gains IsAuthenticated; nothing else here moves.
    """

    permission_classes = [AllowAny]

    def get(self, request, race_id: int, team_id: int):
        ...   # 404 via get_object_or_404 on both; then suggested_squad

    def put(self, request, race_id: int, team_id: int):
        ...   # validate the body, call set_squad, catch SquadError -> 400,
              # then return the same payload the GET returns
```

The `SquadError` → 400 translation is the whole reason `SquadError` is its own
class rather than a bare `ValueError`: a bare one would also catch
`simulate_race`'s `"already finished"` and turn a bug into a validation
message.

## api/urls.py

```python
path("racing/races/<int:race_id>/squads/<int:team_id>/", SquadView.as_view(), name="squad"),
```

Placed with the others, above the SPA catch-all — which is `config/urls.py`'s
job and already correct.

## frontend/src/api.ts

`Squad`, `SquadRider` types mirroring the serializers, plus:

```ts
export async function getSquad(raceId: number, teamId: number): Promise<Squad>
export async function putSquad(
  raceId: number, teamId: number, riderIds: number[], leaderId: number,
): Promise<Squad>
```

`putSquad` sends `Content-Type: application/json` and no CSRF token — see
decision 8. On a non-2xx it throws with the response's `detail` when there is
one, so the screen can show why a save was refused.

## frontend/src/useSquad.ts (new)

```ts
export function useSquad(raceId: number, teamId: number): {
  squad: Squad | null
  loading: boolean
  error: boolean
  save: (riderIds: number[], leaderId: number) => Promise<void>
  saving: boolean
  saveError: string | null
}
```

Same lifecycle shape as `useCalendar` / `useSeason`, but **no polling**: this
screen holds unsaved local edits, and a 60-second refetch would silently
overwrite what the manager is in the middle of picking. Fetch once on mount and
on `raceId`/`teamId` change; refresh from the `PUT` response.

## frontend/src/screens/Race.tsx (new)

Route `/race/:raceId`. Registered in `App.tsx` — note that `SCREENS` there is
keyed by nav path and generates one route per nav item, so a parameterised route
does not fit that map. Add it as an explicit `<Route path="/race/:raceId" ...>`
alongside the generated ones, before the `path="*"` catch-all, and leave the
nav's plain `/race` item on its placeholder.

Layout, following the design's *Race day* upcoming state within the limits of
decision 9:

- `PageHeading` — status chip (reuse `raceStatusLabel` / `raceStatusTone` from
  #7), race name, and a meta line of date and distance.
- A `Card` of race facts: distance, date, status. Three tiles, not the design's
  eight.
- The **Select squad** panel: header with an `n/4 selected` count, a `LEADER`
  summary block, one row per roster rider (checkbox, name, the five attributes,
  a ★ that sets the leader and is only visible on selected rows), and a CTA
  reading `Confirm squad` when valid or `Select N more` when not, disabled while
  invalid.
- When `editable` is false, render the same panel read-only: the four who rode,
  the leader marked, no checkboxes and no CTA. That is the spec's item 10.

The team id comes from `?team=<id>` on the URL, defaulting to the first team the
calendar knows about. **Ugly on purpose** — it is the visible edge of decision
8, and it should read as obviously temporary. It disappears in
[#50](https://github.com/mario595/cycling-manager/issues/50).

## frontend/src/screens/Calendar.tsx

Make each race row a `<Link to={/race/${race.id}}>`. No other change.

## Work items

### W1 — `racing/models.py`, `racing/migrations/0005_racesquad.py`: the two models ✅

`SQUAD_SIZE`, `RaceSquad`, `RaceSquadRider`, both constraints, the index.
Register both in `racing/admin.py` with the inline and the comment.

**Test:** `racing/tests.py::test_a_team_cannot_have_two_squads_for_one_race` and
`::test_a_rider_cannot_appear_twice_in_a_squad` — both assert `IntegrityError`
inside `pytest.raises`, each in its own `transaction.atomic()` block so the
first does not poison the test's connection.

### W2 — `race_engine/models.py`, `race_engine/config.py`: leader validation applies to `run_race` ✅

Move `_validate_team_leaders` → `models.validate_team_leaders`, add
`RaceSetupError`, make `ConfigError` subclass it, call it from `run_race`.

**Load-bearing** — this is what turns an invalid squad into a failure instead of
a silently wrong race.

**Test:** `race_engine/test_team_tactics.py::test_run_race_rejects_a_team_with_two_leaders`
and `::test_run_race_rejects_a_team_with_no_leader`. Confirm the existing
config-level tests for the same rule still pass unchanged — that is what proves
the move did not narrow the rule.

### W3 — `racing/services.py`: `auto_pick_squad` and `previous_squad` ✅

Pure reads, no writers yet. `SquadError` lands here.

**Test:** `racing/tests.py::test_auto_pick_prefers_leaders_then_strength`
(a team of six with a known attribute spread — assert the exact four ids and the
leader, which is what the `pk` tiebreak makes possible),
`::test_auto_pick_refuses_a_team_of_three`, and
`::test_previous_squad_ignores_riders_who_left_the_team`.

### W4 — `racing/services.py`: `_write_squad`, `set_squad`, `suggested_squad`

The validation and the replace-in-one-transaction write.

**Test:** `::test_set_squad_replaces_the_previous_selection` (save four, save a
different four, assert exactly four rows remain), plus one test per `SquadError`
branch: wrong size, duplicate rider, a rider from another team, a leader not in
the squad, a race that has already started.
`::test_suggested_squad_falls_back_from_saved_to_previous_to_auto` covers the
three-way fallback in one test with three assertions.

### W5 — `racing/adapters.py`, `racing/services.py`: the simulation races only the squads

The `to_engine_rider(role=...)` parameter, `ensure_squads`, and the rewritten
field-building block in `simulate_race`.

**Load-bearing** — this is the item that makes the feature real, and the
regression it risks is subtle: `by_pk` maps engine ids back to rows, so if
`db_riders` and `engine_riders` ever stop being built from the same `members`
list, results attach to the wrong riders.

**Test:** `::test_only_selected_riders_appear_in_the_results` — two teams of six,
squads of four each, assert exactly eight `RaceResult` rows and that no
unselected rider has one. `::test_the_squad_leader_races_as_leader_regardless_of_rider_role`
— select a rider whose `Rider.role` is `support` as the squad leader and assert
the `EngineRider` handed over has `role == "leader"`.
`::test_a_team_with_no_squad_gets_one_at_race_time` — no squads at all, run,
assert `RaceSquad` rows exist afterwards with `is_auto_picked=True`.
`::test_a_team_of_three_is_skipped_rather_than_crashing_the_race`.

### W6 — `api/serializers.py`, `api/views.py`, `api/urls.py`: the squad endpoint

`SquadSerializer`, `SquadRiderSerializer`, `SquadWriteSerializer`, `SquadView`,
the route, and the shared `distance_km` helper.

**Test:** `api/tests.py::test_squad_endpoint_returns_a_suggestion_for_an_unpicked_race`
(assert `saved is False` and four candidates flagged `selected`),
`::test_putting_a_squad_saves_it_and_returns_it` (assert `saved is True` and the
rows exist), `::test_putting_five_riders_is_a_400`,
`::test_putting_a_squad_for_a_finished_race_is_a_400`, and
`::test_unknown_race_or_team_is_a_404`.

### W7 — `frontend/src/api.ts`, `useSquad.ts`: the client

Types, `getSquad`, `putSquad`, the hook. No polling.

**Test:** none — this repo has no frontend test setup, and adding one is not
this ticket's job. W8's manual verification covers it.

### W8 — `frontend/src/screens/Race.tsx`, `App.tsx`, `Calendar.tsx`: the screen

The screen, the parameterised route, the calendar link.

**Test:** manual, per *Verification* below. State explicitly in the PR that
this item is not unit-tested and why.

### W9 — documentation

Per *Documentation update* below. Its own commit, last.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9, and that is the order for a reason:

- **W1 first** because everything else stores or reads these rows.
- **W2 before W5**, not after. W5 is the item that can hand the engine an
  invalid field, and W2 is the check that catches it. Landing them the other way
  round means W5's tests pass against an engine that would have accepted
  anything, and the check arrives with nothing left to prove itself against.
- **W3 before W4** because `set_squad`'s tests want a plausible squad to save,
  and `auto_pick_squad` is the cheapest source of one.
- **W5 before W6** because it proves the data flow end to end — squads in, a
  correct field out — with no HTTP layer in the way. If the model shape is
  wrong, W5 is where it shows, and reworking it costs one commit instead of
  four.
- **W6 before W7/W8** so the screen is built against an endpoint that already
  answers.
- **W9 last** so it documents what was built, not what was planned.

Commit after each item. Every one of W1–W6 leaves the full suite green on its
own; W7 and W8 change no Python.

## Documentation update (required, not optional)

| File | What it must say |
|---|---|
| `racing/README.md` | A new **Squads** section: the two models and why membership is rows rather than JSON (decision 1); that `set_squad` is the only sanctioned writer and the four/one-leader rule is a service rule, not a constraint, with the admin's ability to violate it called out (decision 2); that `ensure_squads` runs inside `simulate_race` so an absent manager still starts, and that a team under four riders is skipped rather than raising (decision 7). Update the *What lives here* table with both models. Update *Simulating a race* — the "every rider in the database races" placeholder is gone. |
| `race_engine/README.md` | *Config format* currently states the one-leader-per-team rule as a `load_config` rule. Widen it: the rule is enforced by `run_race` too, and `ConfigError` now subclasses `RaceSetupError`. |
| `api/README.md` | Add the endpoint to *What exists*. Extend *Authentication* with the deferred-identity decision **and the CSRF consequence** (decision 8): this endpoint is `AllowAny` with the team in the URL, anyone can edit anyone's squad, and both that and the SPA's CSRF story close in [#50](https://github.com/mario595/cycling-manager/issues/50). Name the issue — the section currently describes the workaround with nothing pointing at its fix. |
| `frontend/README.md` | Add `/race/:raceId` to the route table. Note that it is the first parameterised route and so is registered explicitly rather than through `SCREENS`. Note the `?team=` query parameter as the temporary stand-in for identity, and that it goes away in #50. Update *Relationship to `design/`*: the *Race day* screen is now **partly** built, and say which parts of the mockup were deliberately not built and why (decision 9's table). |
| `design/README.md` | The re-exported mockup adds the race screen with 8-rider squads, suitability scores and injury states. Record that the game's squad size is **four** and that the export's eight is not the spec — so the next person reconciling the export does not "fix" the app to match it. |
| `AGENTS.md` | The `racing/` row still reads as the engine seam, which is still true — no change needed. Check the `transfers/` row's parenthetical about roster concerns is still accurate; it is. |

Then, per `AGENTS.md`'s closing convention, **delete `specs/squad-selection.md`
and `specs/squad-selection-plan.md`** before opening the PR.

## Verification

Unit tests first:

```bash
.venv/bin/python -m pytest
```

All of it, not just `racing/` — W2 touches the engine, whose 49 tests are the
guard that the move did not change behaviour.

Then end to end, which is the part that actually proves it. **There is no
seeding command in this repo**, and `seasons/season-1.example.json` declares no
races, so build the world by hand.

A season file with one race, saved as `seasons/squad-check.json` (the `races`
key and its shape come from #7 — see `schedule/README.md`, *The `races` list*):

```json
{
  "number": 1,
  "starts_at": "2027-03-01T00:00:00Z",
  "races": [
    {
      "week": 1,
      "day": "sunday",
      "time": "14:00",
      "name": "Squad Check Classic",
      "course": [
        { "length": 40000, "gradient": 0.0 },
        { "length": 12000, "gradient": 5.0 }
      ]
    }
  ]
}
```

Two teams of six riders each, created in the shell:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py shell -c "
from teams.models import Team
from riders.models import Rider
for code, name in [('ALP', 'Team Alpha'), ('BET', 'Team Beta')]:
    t, _ = Team.objects.get_or_create(code=code, defaults={'name': name})
    for i in range(6):
        Rider.objects.get_or_create(
            name=f'{code} Rider {i}', team=t,
            defaults=dict(role='leader' if i == 0 else 'support',
                          climb=50 + i * 5, sprint=50, flat=50,
                          resistance=50, positioning=50),
        )
print(Rider.objects.count(), 'riders')
"
.venv/bin/python manage.py load_season seasons/squad-check.json --replace
```

Then run against the mock clock, positioned inside week 1 but before the race:

```bash
export GAME_CLOCK_CLASS=world.clocks.MockClock
.venv/bin/python manage.py mock_clock set 2027-03-03T09:00
.venv/bin/python manage.py runserver
```

Open `/calendar` — the race is in week 1. Click it. Pick a squad for **ALP**
that is deliberately *not* the auto-pick (choose the four weakest, and make a
`support` rider the leader), save, and reload: the selection persists. Leave
**BET** untouched. Then, in another shell with the same env var:

```bash
.venv/bin/python manage.py mock_clock advance --to-next
.venv/bin/python manage.py tick
```

**The check that matters:** the race has **eight** `RaceResult` rows, not
twelve.

```bash
.venv/bin/python manage.py shell -c "
from racing.models import Race, RaceResult
r = Race.objects.latest('pk')
print(r.status, RaceResult.objects.filter(race=r).count(), 'results')
for s in r.squads.select_related('team'):
    print(s.team.code, 'auto' if s.is_auto_picked else 'chosen',
          [(m.rider.name, m.is_leader) for m in s.members.select_related('rider')])
"
```

Reading the output:

- **Twelve results** — the field-building block in `simulate_race` is still
  reaching for every rider in the database. W5 is not done.
- **Four results** — only ALP's squad was built; `ensure_squads` did not fire
  for BET. Item 8 of the spec is broken.
- **Eight results**, ALP `chosen` with the four you picked, BET `auto` with
  four, and **exactly one `True` leader in each** — the pass.

Then check the role actually reached the engine, which the result count alone
does not prove:

```bash
grep -m1 '"role"' "$(.venv/bin/python manage.py shell -c '
from racing.models import RaceLog
print(RaceLog.objects.latest("pk").file.path)')" | head -c 400
```

The rider you nominated must appear with `"role": "leader"` even though their
`Rider.role` is `support`. If it says `support`, `to_engine_rider` is still
reading the model field and decision 4 is not implemented.

Finally reload the race screen: it reads `Result in`, and the panel shows the
four who rode with no checkboxes and no CTA — the spec's item 10.

**Evidence that proves nothing:** a test that saves a squad and reads it back.
That exercises the serializer and the model and never touches the thing this
feature is actually about, which is the field the engine receives. The tests
that count are `test_only_selected_riders_appear_in_the_results` and
`test_the_squad_leader_races_as_leader_regardless_of_rider_role`.

## Risks

| Risk | Mitigation |
|---|---|
| **The reader "fixes" the app to match the design's eight riders and suitability scores.** The mockup is far ahead of the spec and looks authoritative. | Decision 9's table is explicit, item by item. `design/README.md` gains the same note in W9, so the next reconciliation does not reintroduce it. |
| **Results attach to the wrong riders** because `db_riders` and `engine_riders` drift apart. `by_pk` maps engine ids back to rows and will silently mismatch. | Both are built from the same `members` list in one block. `test_only_selected_riders_appear_in_the_results` asserts on rider identity, not just row count. |
| **An invalid squad reaches the engine** and produces a plausible-looking but meaningless race. | W2 — `validate_team_leaders` moves into `run_race`. This is why W2 comes before W5. |
| **`ensure_squads` deadlocks or races with a concurrent tick.** It writes rows for a race the tick has already claimed. | The claim is exactly-once (`world/README.md`), so only one tick ever holds a given race — `ensure_squads` runs single-threaded per race by construction. Do not add locking. |
| **`set_squad`'s status guard blocks `ensure_squads`**, because the tick has already flipped the race to `RUNNING`. This is the trap in this plan. | `_write_squad` holds the write, `set_squad` adds the guard, `ensure_squads` calls `_write_squad`. Do not add a `force=` flag to `set_squad`. |
| **Anyone can edit anyone's squad.** | Accepted and documented (decision 8). A single-manager world is what `specs/roadmap.md` says Phases 1–3 are deliberately testing, and [#50](https://github.com/mario595/cycling-manager/issues/50) (Phase 4) is the named ticket that closes it — recorded in `api/README.md` so it is picked up there rather than discovered later. |
| **A team with fewer than four riders crashes a race for everyone.** | `ensure_squads` skips and warns. Tested. The real fix belongs to whichever ticket lets riders leave a roster — the spec says so. |
| **#7 is not merged when this starts**, and `racing/models.py` conflicts. | #7 already adds `0004_race_race_day.py`, so W1's is `0005`. Run `ls racing/migrations/` after the merge and let `makemigrations` name it rather than hand-numbering. |

## Open questions

None.
