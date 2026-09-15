# Claiming a team — Implementation Plan

**Spec:** `specs/claiming-a-team.md` · **Issue:** #46 · **Status:** proposed
**Apps touched:** `teams/` (new `services.py`, new `README.md`, new
`management/commands/seed_teams.py`), `api/`, `frontend/`

## Context you need

A player registers (`POST /api/accounts/register/`, built by #50) and is logged
in immediately. Nothing then happens: `teams.Team.manager` stays null and the
player manages nothing. Every team-scoped endpoint reacts to that by returning
403 — `api.views.team_for()` returns `None` and both `SquadView` and
`RiderListView` answer `{"detail": "You do not manage a team."}`. This feature
fills that hole: it turns a registered account into the manager of an existing
unmanaged team.

What already exists and must be used rather than rebuilt:

- **`riders.generation.generate_roster(size, *, team=None, rng=None)`** returns
  a list of **unsaved** `Rider` objects with a deliberate quality spread
  (`QUALITY_SPREAD` in `riders/generation.py`: ~15% weak, ~55% unremarkable,
  ~25% good, ~5% standout). This is exactly what the spec's item 8 asks for.
  Built by #57. Do not write a second generator.
- **`riders/management/commands/reset_riders.py`** is the house pattern for a
  world-mutating management command: `--yes` guard, one `transaction.atomic()`,
  `racing.models` imported *inside* `handle()`. Copy its shape.
- **`teams.Team`** already has `name` (unique), `code` (unique, exactly three
  uppercase letters via `team_code_validator`), `manager` (nullable
  `OneToOneField` to `accounts.User`), and two colour fields. `is_ai_controlled`
  is a property reading `manager_id is None`.
- **`api.views.team_for(user)`** is the single place that answers "what team
  does this user manage". It catches `Team.DoesNotExist` deliberately, not
  `AttributeError` — read its docstring before touching it.

Repo rules this work is bound by (from `AGENTS.md`):

- `teams -> core, accounts`. **This plan widens it to `teams -> core, accounts,
  riders`** — see Design decision 2, which also explains why that is safe and
  what the alternative would have cost.
- `accounts/` imports nothing. `accounts/README.md` states this explicitly and
  names #46 as the owner of "what a new account gets". Registration must not
  learn about teams.
- `api/` may import everything; nothing imports `api/`.
- Tests are pytest: `.venv/bin/python -m pytest`.

Two things the spec promises that **cannot be built yet**, and are correctly
absent from the work items below: inheriting classification position/points
(no `competitions/` app exists) and resetting money (no `economy/`). The spec
records both as decided-but-deferred. Do not invent a placeholder for either.

## Goal

When this is done:

1. A management command creates a world of unmanaged teams, each with a
   generated roster, so there is something to claim from a clean database.
2. A logged-in user with no team can claim one: they supply a team name and a
   three-letter code, and receive an assigned unmanaged team.
3. The claimed team keeps its identity-independent history (its `RaceResult`
   and `RaceSquad` rows are untouched) and takes the player's name and code.
4. Every rider the team had becomes a free agent (`team = None`); none is
   deleted.
5. The team receives a freshly generated 12-rider roster.
6. Claiming is atomic, single-use per user, and refuses cleanly when no
   unmanaged team is available.
7. The SPA prompts a team-less logged-in user to claim, and lands them on the
   dashboard afterwards.

## Design decisions (settled — implement these, do not substitute)

**1. The claim is its own endpoint, not part of registration.**
`POST /api/teams/claim/`, separate from `POST /api/accounts/register/`. The SPA
calls register, then claim.

*Why:* `accounts/` may import nothing (`AGENTS.md`, and `accounts/README.md`
says so in its own words). Folding the claim into `RegisterView` would force
`accounts/` to import `teams/` and `riders/`, inverting the dependency graph at
its root. #50 already set this precedent: register returns only
`{"display_name": ...}` and the SPA follows up with `GET /api/accounts/me/` for
the team, because that endpoint lives in `api/` — the one app allowed to know
about both.

*Do not* add a `create_team=True` flag to the register payload. It reads as a
convenience and is the same violation.

**2. The claim service lives in `teams/services.py` (new), and `teams/` gains
an import of `riders/`.**

*Why:* the claim writes `Team.manager`, `Team.name`, `Team.code`, and a new
`Rider.team` for twelve riders. `teams/` owns the first three. The alternative —
putting it in `world/`, which may import anything — was rejected: claiming is
not clock or tick orchestration, and `world/` would then be the only place that
knows how a team changes hands, away from the model that owns the relationship.

*The dependency change is real and must be recorded.* `AGENTS.md` currently says
`teams -> core, accounts`. Update that line to `teams -> core, accounts, riders`
in the same commit as W3. This does not create a cycle: `riders -> core, teams`
is a **model-level** reference by string (`"teams.Team"`), and
`riders/generation.py` imports only `riders.models`, so importing
`riders.generation` from `teams/services.py` pulls in no module that imports
`teams/` at runtime. Verify this holds by running the suite — a real cycle
surfaces as an `ImportError` at startup, not as a subtle bug.

**3. The old riders are released, not deleted — and the release is what makes
history survive.**

Set `Rider.team = None` on every rider currently on the team. Do **not** delete
them: `racing.RaceResult.rider` and `racing.RaceSquadRider.rider` are both
`on_delete=CASCADE`, so deleting a rider would silently erase the race history
the spec's items 2 and 6 promise to keep.

*Load-bearing:* `racing.services.previous_squad()` already filters members to
`m.rider.team_id == team.pk` and returns `None` when fewer than `SQUAD_SIZE`
survive, so the squad pre-fill degrades to `auto_pick_squad` on the new roster
by itself. No change is needed in `racing/` — and none should be made.

**4. Which team is claimed: the lowest-pk unmanaged team.**

`Team.objects.filter(manager__isnull=True).order_by("pk").first()`, selected
`for_update`. The spec settles that placement is assigned rather than chosen
(#14 owns *where* a player lands); this plan needs only a deterministic,
testable rule. Lowest-pk is deterministic, which random selection is not, and
mid-season placement logic belongs to #14.

**5. The whole claim is one transaction, and the team row is locked.**

Two players registering simultaneously must not be handed the same team.
`select_for_update()` on the candidate row inside `transaction.atomic()` is what
prevents it; `Team.manager` being a `OneToOneField` is the backstop that turns a
lost race into an `IntegrityError` rather than two managers on one team.

The naive version — filter, then save — is wrong under concurrency. Write it as:

```python
def claim_team(user, *, name: str, code: str, roster_size: int = ROSTER_SIZE) -> Team:
    """Assign an unmanaged team to `user`, rename it, release its riders and
    give it a freshly generated roster. One transaction: a half-claimed team
    (renamed but with no roster) must never be observable."""
    with transaction.atomic():
        team = (
            Team.objects.select_for_update(skip_locked=True)
            .filter(manager__isnull=True)
            .order_by("pk")
            .first()
        )
        if team is None:
            raise NoTeamAvailable("There are no teams available to claim.")

        team.manager = user
        team.name = name
        team.code = code
        team.full_clean(exclude=["manager"])
        team.save(update_fields=["manager", "name", "code", "updated_at"])

        team.riders.update(team=None)
        Rider.objects.bulk_create(generate_roster(roster_size, team=team))
    return team
```

`skip_locked=True` is deliberate: a concurrent claimer should take the *next*
free team rather than block on the locked one.

`full_clean(exclude=["manager"])` is what enforces the three-letter code rule —
`team_code_validator` is a field validator and **does not run on `.save()`**.
Excluding `manager` avoids a pointless uniqueness query on a field we just set.
`updated_at` is in `update_fields` because `core.TimeStampedModel` uses
`auto_now`, which only fires for fields listed explicitly.

**6. `name` and `code` are not checked for uniqueness at the product level, but
`Team.name` and `Team.code` are `unique=True` in the database today.**

This is the one place the spec and the schema disagree. The spec (items 5, and
*Decisions taken*) says a player is never told their choice is taken, and #56
handles display-time disambiguation. The model says otherwise.

**Resolution for this plan: drop `unique=True` from `Team.code` only, and keep
it on `Team.name`.** Migration in W3.

*Why this split:* the spec's reasoning for dropping uniqueness is specifically
about *codes* — a three-letter label with only ~17k combinations, where
uniqueness forces a player to guess what is free. It says nothing about names,
and a world with two teams both called "Mountain Goats" is a different and
worse problem (names are the primary identifier in every table and heading).
Names stay unique; a duplicate name returns a 400 with a field error, which the
SPA already renders (`errorMessageFrom` in `frontend/src/api.ts` prefers the
first field error).

*If this is wrong,* it is a product question, not a technical one — send it back
rather than resolving it in code.

**7. One claim per user, enforced by the existing relationship.**

`Team.manager` is a `OneToOneField`, so a second claim by the same user raises
`IntegrityError`. The view checks `team_for(request.user)` first and returns 409
with a clear message, so the happy path never relies on the exception.

**8. Roster size is a named constant, 12.**

`ROSTER_SIZE = 12` in `teams/services.py`, matching
`reset_riders.DEFAULT_RIDERS_PER_TEAM`. Do not import the command's constant —
a management command is an entry point, not a library.

## Data model

No new models. One migration on an existing field, plus nothing else:

| App | Change | Migration |
|---|---|---|
| `teams` | `Team.code` loses `unique=True`. Keeps `max_length=3` and `team_code_validator`. `null`/`blank` unchanged (both False). No default. | `teams/migrations/0002_team_code_not_unique.py` |

`Team.name` is unchanged and stays `unique=True` (Design decision 6).
`Rider` is unchanged — #57 already added every field this feature reads, and
the claim only writes `Rider.team`, which has existed since the first migration.

## teams/services.py (new)

```python
ROSTER_SIZE = 12

class ClaimError(Exception): ...
class NoTeamAvailable(ClaimError): ...
class AlreadyManaging(ClaimError): ...

def claim_team(user, *, name: str, code: str, roster_size: int = ROSTER_SIZE) -> Team: ...
```

Full body in Design decision 5 — implement it as written, including
`skip_locked=True`, `full_clean(exclude=["manager"])` and the `update_fields`
list.

`AlreadyManaging` is raised by the view, not the service: the service is called
only after the view has established the user manages nothing, and a service that
re-queries for that would duplicate `team_for()`.

## teams/management/commands/seed_teams.py (new)

```bash
python manage.py seed_teams [--count=16] [--per-team=12] [--reset]
```

Creates `--count` unmanaged teams, each with `--per-team` generated riders.
Without `--reset` it *adds* teams and refuses to touch existing ones; with
`--reset` it deletes every team that has no manager (and their riders) first.

- **Never deletes a managed team**, with or without `--reset`. A `--reset` that
  could orphan a real player's account is a footgun; filter on
  `manager__isnull=True`.
- Names and codes come from a module-level list of plausible team names with a
  derived three-letter code (e.g. `"Ardennes Racing"` → `"ARD"`). Keep the list
  in the command — it is seed data, not game logic. If `--count` exceeds the
  list length, suffix numerically (`"Ardennes Racing 2"` → `"AR2"`).
- Colours: pick from a small hard-coded palette so teams are visually distinct
  in the race player. `Team.primary_colour` defaults to `#1E88E5`; leaving every
  seeded team on the default makes the race player unreadable.
- Import `racing.models` inside `handle()` only if `--reset` needs it (it does,
  to clear squads/results for deleted riders) — same rule and same reason as
  `reset_riders`, which the docstring should cite.
- Wrap the work in one `transaction.atomic()`.

## api/serializers.py

Add:

```python
class ClaimTeamSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    code = serializers.CharField(min_length=3, max_length=3)

    def validate_code(self, value):
        return value.upper()
```

Uppercasing in `validate_code` is a convenience so a player typing `ard`
succeeds; the model validator then sees `ARD`. Do not also relax
`team_code_validator` — the stored value must still be exactly three uppercase
letters.

## api/views.py

Add `ClaimTeamView(APIView)`. Inherits the project default `IsAuthenticated` —
**do not add `AllowAny`**, and note the same warning already on `SquadView` and
`RiderListView`.

```python
class ClaimTeamView(APIView):
    def post(self, request):
        if team_for(request.user) is not None:
            return Response({"detail": "You already manage a team."}, status=409)

        serializer = ClaimTeamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            team = claim_team(
                request.user,
                name=serializer.validated_data["name"],
                code=serializer.validated_data["code"],
            )
        except NoTeamAvailable as exc:
            return Response({"detail": str(exc)}, status=409)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=400)
        except IntegrityError:
            return Response({"detail": "That team name is already taken."}, status=400)

        return Response(
            MeTeamSerializer({"id": team.pk, "name": team.name, "code": team.code}).data,
            status=201,
        )
```

Reuses `MeTeamSerializer` for the response so the shape matches the `team` key
of `GET /api/accounts/me/` exactly, and the SPA needs no second type.

409 for both "already managing" and "no team available": both mean *the request
is valid but the world's state refuses it*, which is what 409 is for. 400 is
reserved for a malformed name or code.

## api/urls.py

```python
path("teams/claim/", ClaimTeamView.as_view(), name="claim-team"),
```

## frontend/

- **`src/api.ts`** — add `claimTeam(name, code): Promise<MeTeam>` calling
  `writeJson('/api/teams/claim/', 'POST', {name, code})`. `MeTeam` already
  exists and is the exact response shape.
- **`src/screens/ClaimTeam.tsx`** (new) — a form with team name and code,
  built from the same `Card`/`Field`/`Button` primitives as
  `screens/Register.tsx`. Copy that file's structure; it is the closest
  sibling. On success call the auth context's refresh so `me.team` populates,
  then `<Navigate to="/" replace />`.
- **`src/useAuth.tsx`** — add `claim: (name, code) => Promise<void>` to
  `AuthState`, implemented exactly like the existing `register`/`login`:
  `await apiClaimTeam(name, code); setMe(await getMe())`. The refetch is
  load-bearing — the claim response alone does not update `me.team`, and every
  redirect added in W7 reads `me.team`.

  There is no exported refetch to reuse today: `AuthState` exposes only `me`,
  `loading`, `register`, `login` and `logout`, and `setMe(await getMe())` is
  inlined in each. Follow that shape rather than refactoring a shared
  `refresh()` out of it — a refactor here touches every auth screen for no gain
  in this feature.
- **`src/App.tsx`** — add `<Route path="/claim" element={<ClaimTeam />} />`
  alongside `/login` and `/register`, i.e. **not** in `SCREENS` and not a nav
  item.
- **Redirect the team-less state.** `screens/Register.tsx` currently does
  `if (me?.authenticated) return <Navigate to="/" replace />`, which after this
  feature sends a fresh registrant to a dashboard for a team they do not have.
  Change that redirect to `/claim` when `me.team === null`. Apply the same rule
  in `screens/Login.tsx`.

*Load-bearing:* a logged-in user with no team must not reach `/roster` or a
squad screen — both 403 and render an error. Gate them on `me.team` in
`components/Layout.tsx` (redirect to `/claim`) rather than handling the 403 in
each screen.

## Work items

### W1 — `teams/management/commands/seed_teams.py`: create a claimable world
New command per the section above, plus `teams/management/__init__.py` and
`teams/management/commands/__init__.py`. Nothing else depends on it, and it is
what makes every later item testable by hand.
**Test:** `teams/tests/test_seed_teams.py` — `test_creates_unmanaged_teams_with_rosters`
(count and per-team roster size correct, every team `manager is None`),
`test_reset_leaves_managed_teams_alone` (a team with a manager survives
`--reset`), `test_codes_are_three_uppercase_letters` (every seeded team passes
`full_clean()`).

### W2 — `teams/tests/` package
`teams/tests.py` today is the untouched `startapp` stub (an empty `TestCase`
import, no tests). Replace it with a `teams/tests/` package laid out like
`riders/tests/` — `__init__.py` plus a `conftest.py` providing a `team`
fixture — and delete the stub file.
**Test:** the package itself; W1's tests land in it. If W1 and W2 are done
together, commit W2 first so W1's tests have somewhere to go.

### W3 — `teams/migrations/0002`: drop `unique=True` from `Team.code`
Model change plus migration, and update the dependency line in `AGENTS.md`
(`teams -> core, accounts, riders`) in this same commit, since W4 relies on it.
**Test:** `teams/tests/test_models.py::test_two_teams_may_share_a_code` —
creating two teams with code `"ARD"` succeeds; and
`test_code_must_be_three_uppercase_letters` — `full_clean()` still rejects
`"ard"`, `"ARDE"` and `"A1D"`.
**Load-bearing:** the validator must keep working after uniqueness goes. A
migration that drops the whole field and re-adds it would lose the validator.

### W4 — `teams/services.py`: `claim_team`
The service per Design decision 5.
**Test:** `teams/tests/test_services.py` —
`test_claim_assigns_lowest_pk_unmanaged_team`,
`test_claim_renames_and_recodes`,
`test_claim_releases_old_riders_without_deleting` (old riders still exist,
`team is None`, count unchanged),
`test_claim_generates_a_full_roster` (exactly `ROSTER_SIZE` riders on the team,
and they are not the released ones),
`test_claim_raises_when_no_team_available`,
`test_claim_rejects_a_bad_code` (`full_clean` raises, and **nothing is
written** — assert the team is still unmanaged afterwards, which is what proves
the transaction rolls back),
`test_claim_preserves_race_results` (a `RaceResult` for a released rider still
resolves after the claim).

### W5 — `api/`: serializer, view, route
`ClaimTeamSerializer`, `ClaimTeamView`, the `urls.py` entry.
**Test:** `api/tests.py` — `test_claim_requires_authentication` (403/401 for
anonymous), `test_claim_returns_the_new_team`,
`test_claim_twice_is_409`, `test_claim_with_no_teams_available_is_409`,
`test_claim_lowercase_code_is_accepted_and_uppercased`,
`test_claim_duplicate_name_is_400`.

### W6 — `frontend/src/api.ts` + `screens/ClaimTeam.tsx`
The client function and the screen.
**Test:** no frontend test framework is configured in this repo, so this item
is proven by the Verification section's browser pass, not by a unit test. Say so
in the commit message rather than leaving it implied.

### W7 — `frontend/`: routing and the team-less redirect
`App.tsx` route, the `Register.tsx`/`Login.tsx` redirect change, and the
`Layout.tsx` gate.
**Test:** as W6 — browser verification.

### W8 — Documentation
Per the section below.
**Test:** none; prose.

## Execution order

W2 → W1 → W3 → W4 → W5 → W6 → W7 → W8.

W2 first so W1 has a test package. W1 second because a seeded world is what lets
you exercise everything after it by hand, and it touches nothing else. W3 before
W4 because `claim_team` writes a code and the uniqueness constraint would make
the second test team impossible. W4 before W5 so the service is proven before
anything calls it. W6 and W7 last: the backend is complete and verifiable via
`curl` before any UI exists, which keeps a frontend bug from being mistaken for
a service bug.

Commit after each work item. The suite must be green at every commit.

## Documentation update (required, not optional)

- **`teams/README.md` (new — the app has none today).** Required by
  `AGENTS.md`'s rule that a folder with real work in it carries a README.
  Sections: *What this app owns* (`Team`, the claim service, the seed command —
  and what it does not own: rosters are `riders/`, standings are the unbuilt
  `competitions/`); *Claiming a team* (the flow, that it is one transaction,
  why the team row is locked, and the one-claim-per-user rule);
  *Codes are not unique* (the decision, a pointer to #56 for display-time
  disambiguation, and the warning that `team_code_validator` does not run on
  `.save()` — hence `full_clean()`); *What `teams/` may import* (core, accounts
  and now riders, with Design decision 2's reasoning that this is not a cycle);
  *`seed_teams`* (usage, and that `--reset` never touches a managed team).
- **`AGENTS.md`** — the dependency block: `teams -> core, accounts, riders`.
  Land this in W3, not W8.
- **`api/README.md`** — add `POST /api/teams/claim/` to the endpoint list, with
  its 201/400/409 responses and the note that it inherits `IsAuthenticated`.
- **`accounts/README.md`** — it currently says what a new account gets is
  "`specs/claiming-a-team.md` / #46". Once this ships, point at
  `teams/README.md` instead, since the spec file gets deleted on close.
- **`frontend/README.md`** — the `/claim` route, and the rule that a logged-in
  user with no team is redirected there rather than to the dashboard.
- **`riders/README.md`** — one line under *Generation*: `generate_roster` now
  has a second caller, `teams.services.claim_team`.

Per `CLAUDE.md`, delete `specs/claiming-a-team.md` and
`specs/claiming-a-team-plan.md` before opening the PR.

## Verification

Backend, from a clean database:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_teams --count=4 --per-team=12
.venv/bin/python -m pytest
```

Then the end-to-end path, which is the only thing that proves the feature:

```bash
.venv/bin/python manage.py shell -c "
from accounts.models import User
from teams.models import Team
from teams.services import claim_team
u = User.objects.create_user(email='a@b.com', password='x', display_name='A')
before = Team.objects.filter(manager__isnull=True).order_by('pk').first()
old_ids = set(before.riders.values_list('pk', flat=True))
t = claim_team(u, name='Mountain Goats', code='MGO')
from riders.models import Rider
print('claimed:', t.name, t.code, 'manager:', t.manager.email)
print('roster size:', t.riders.count())
print('old riders still exist:', Rider.objects.filter(pk__in=old_ids).count(), 'of', len(old_ids))
print('old riders now free agents:', Rider.objects.filter(pk__in=old_ids, team__isnull=True).count())
print('new roster disjoint from old:', not (set(t.riders.values_list('pk', flat=True)) & old_ids))
"
```

**The likeliest failure mode is a partially applied claim** — the team renamed
and reassigned, but the roster generation failing, leaving a player managing an
empty team. The check that catches it: force a failure inside the transaction
(a deliberately invalid code, covered by W4's
`test_claim_rejects_a_bad_code`) and assert the team is *still unmanaged*
afterwards. A test that only asserts the exception was raised proves nothing
about the rollback.

**The second likeliest is two users claiming one team.** Prove the lock with two
concurrent shells, or accept W4's single-process test plus the
`OneToOneField` backstop and say which you did — a passing test in one process
does not exercise `select_for_update`.

Frontend, since there is no test framework:

```bash
.venv/bin/python manage.py runserver
```

Register a new account in the browser, confirm you land on `/claim` and not the
dashboard, submit a name and a lowercase code, confirm the code is stored
uppercase, and confirm `/roster` then shows twelve riders. Also confirm that a
logged-in user with no team who types `/roster` directly is redirected rather
than shown an error.

## Risks

| Risk | Mitigation |
|---|---|
| The reader deletes the old riders instead of releasing them, silently destroying race history via `CASCADE`. | Design decision 3 says so explicitly; W4's `test_claim_preserves_race_results` fails if they do. |
| `team_code_validator` is assumed to run on `.save()` and does not, so a bad code reaches the database. | `full_clean()` in `claim_team`, and W3's `test_code_must_be_three_uppercase_letters`. Called out in `teams/README.md`. |
| The claim is folded into `RegisterView` "to save a round trip", inverting the dependency graph. | Design decision 1, and `accounts/README.md` already states the rule. |
| Two simultaneous registrations claim the same team. | `select_for_update(skip_locked=True)` inside `atomic()`, with the `OneToOneField` as backstop. Noted in Verification as needing a concurrency check the unit test does not give. |
| Dropping `unique=True` from `Team.name` as well, because the spec says "names and codes are not checked". | Design decision 6 splits them deliberately and explains why. Only `code` loses uniqueness. |
| `seed_teams --reset` run against a world with real players, deleting their teams. | The command filters on `manager__isnull=True`; W1's `test_reset_leaves_managed_teams_alone` proves it. |
| A frontend change is assumed tested because the Python suite is green. | W6 and W7 state they have no unit test and are proven in the browser. |

## Open questions

None blocking. Two things are deliberately deferred to their own tickets and
must not be built here: classification/points inheritance (needs `competitions/`)
and the money reset (needs `economy/`). Team-code disambiguation within a Group
is [#56](https://github.com/mario595/cycling-manager/issues/56).
