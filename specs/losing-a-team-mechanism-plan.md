# Losing a team: the mechanism — Implementation Plan

**Spec:** `specs/losing-a-team-mechanism.md` · **Issue:** #62 · **Status:** proposed
**Apps touched:** `teams/`, `api/`, `frontend/`

## Context you need

Today a manager gets a team exactly one way and never loses it.
`teams.services.claim_team()` is the only writer of `Team.manager` — it picks
the lowest-`pk` unmanaged team under `select_for_update(skip_locked=True)`,
renames it, releases its riders, generates a fresh roster, and writes
`economy/` takeover rows (balance, fanbase, sponsorship) — all in one
transaction. Read `teams/README.md`, *Claiming a team*, before starting; the
atomicity rule there applies to this work too.

`Team.manager` is a `OneToOneField` to `accounts.User` with
`on_delete=SET_NULL, null=True, related_name="team"`. Null means AI-controlled
(`Team.is_ai_controlled`), which is the normal state for most teams —
`teams/models.py`. So "returning a team to the unmanaged pool" is, at the
model level, setting one column to NULL. Everything else in this plan exists
because that column going NULL has to leave a trace.

`api.views.team_for(user)` is how the rest of the codebase asks "does this
user manage a team" — it catches `Team.DoesNotExist` rather than using
`getattr`, deliberately. `GET /api/accounts/me/` (`MeView`) returns
`{authenticated, display_name, team}` and is the single call the SPA boots
from. In `frontend/`, `Layout.tsx` bounces an authenticated manager with no
team to `/claim`, and `ClaimTeam.tsx` renders the claim form. That redirect is
already the exact path an ex-manager will fall down — this feature adds a
message to it, not a new route.

**Repo rules this work is bound by:**

- **`accounts/` imports nothing** and sits at the root of `AGENTS.md`'s
  dependency graph. The new record model therefore lives in `teams/`, not
  `accounts/` — see Design decision 1.
- `teams/` may import `core`, `accounts`, `riders`, and `economy/` **only
  inside function bodies**.
- Tests are pytest: `.venv/bin/python -m pytest` (the worktree has no
  `.venv`; use `/home/mario/dev/cycling-manager/.venv/bin/python`).
- CI enforces an 85% backend coverage floor.

## Goal

When this is done:

1. `teams.services.release_team(team, *, reason, at)` clears `Team.manager`
   and writes a durable record of the spell that just ended, atomically.
2. Nothing else about the team changes — roster, balance, fanbase,
   sponsorship, results and standings are all untouched, so the team keeps
   racing as an ordinary unmanaged team.
3. The released team is claimable again through the unchanged `claim_team`
   path.
4. An ex-manager's next `GET /api/accounts/me/` tells the SPA they lost a
   team and which one, and `/claim` shows it once.
5. An operator can run `manage.py release_team <team>` to fire it by hand.

## Design decisions (settled — implement these, do not substitute)

### 1. The record model lives in `teams/`, not `accounts/`

The spec says "the ex-manager's account keeps a record". Do **not** read that
as a model in `accounts/`. `accounts/` imports nothing — that is the root of
the dependency graph and `accounts/README.md` states it explicitly. A model
there with a FK to `teams.Team` would invert the graph.

`teams.ManagerialSpell` carries FKs to both `accounts.User` and `teams.Team`,
which `teams/` is already allowed to import. The record is about a team's
history of managers; it is keyed *to* a user, not owned *by* one.

### 2. A spell is recorded on release, not on claim

The record is written by `release_team`, reading `started_at` from the team's
claim. That raises the question of where `started_at` comes from, because
nothing currently stores when a manager took a team.

**Decision: `claim_team` stamps `Team.managed_since`, and `release_team`
reads and clears it.** One nullable datetime on `Team`, set at claim, read at
release. Not a second row written at claim time — an open-ended spell row
that must later be found and closed is two writes, two failure modes, and a
row that means something different depending on whether one of its columns is
NULL.

**Load-bearing:** `managed_since` is NULL for every team that exists today,
including any team currently managed. `release_team` must tolerate a NULL and
record the spell with `started_at = None` rather than crashing or refusing.
See Data model.

### 3. The team name is copied onto the record, not referenced

`ManagerialSpell.team_name` is a plain `CharField`, snapshotted at release.
The FK to `Team` is kept as well, but the *displayed* name comes from the
snapshot.

**Why:** #46 lets the next claimer rename the team. Rendering an ex-manager's
history through the live FK would silently rewrite their past the moment a
stranger renames it. The spec calls this out under *Rules and edge cases*.

Keep the FK (`on_delete=SET_NULL`, nullable) so the record survives a team
being deleted by `seed_teams --reset`, which only ever touches unmanaged
teams and could therefore delete a team someone once managed.

### 4. `reason` is a `TextChoices`, not free text

Three values now: `INACTIVITY`, `INSOLVENCY`, `ADMIN`. Only `ADMIN` is
reachable in this ticket — #63 and #27 supply the other two when they land.
Declaring all three now costs nothing and means neither of those tickets
needs a migration to add a choice.

Do **not** add a free-text note field. The spec's *Out of scope* keeps the
reason a fixed set so the player-facing message stays consistent.

### 5. Release changes the manager link and nothing else

No ledger entry, no fanbase row, no roster change, no sponsorship void.
`claim_team` already does all of that resetting *on the next claim*, and the
spec is explicit that release is not a reset. A manager who loses a team and a
team that was never managed must be indistinguishable to `#44`'s default squad
selection.

**Do not** mirror `claim_team`'s `economy/` calls here. That is the plausible
wrong move — release looks like it should be claim's inverse. It is not: claim
resets the present and inherits the past, and release does neither.

### 6. `release_team` takes a team, not a user

Signature is `release_team(team, *, reason, at)`. Both future triggers
identify a *team* (a team that cannot pay; a team whose manager went quiet),
and the operator command names a team. Passing a user would mean resolving
user → team inside the service, which is `team_for`'s job and lives in `api/`.

Releasing a team that already has no manager is a **no-op that returns
`None`** and writes nothing — spec, *Rules and edge cases*. Not an exception:
both triggers will be scanning sets of teams and racing each other, so
"already released" is an expected outcome, not an error.

### 7. The notification is a derived flag, not stored state

`MeView` reports an unacknowledged lost team by looking for the user's most
recent `ManagerialSpell` with `acknowledged_at IS NULL`. `/claim` shows it,
then `POST /api/teams/spells/<id>/acknowledge/` stamps `acknowledged_at` so
it is shown once.

**Why a column on the spell rather than a general notifications table:** the
spec's *Out of scope* rules out an inbox. One nullable datetime on a row that
already exists is the whole feature.

## Data model

### `teams.Team` — one new field

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `managed_since` | `DateTimeField` | `null=True, blank=True` | none | Game time the current manager claimed this team. NULL when unmanaged **and** for teams claimed before this migration. Set by `claim_team`, cleared by `release_team`. |

Migration: `teams/migrations/0003_team_managed_since.py` — `AddField`, no
data migration. Existing managed teams keep NULL; Design decision 2 covers
what that means at release.

### `teams.ManagerialSpell` — new model

A completed period during which one user managed one team.

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `manager` | `FK("accounts.User")` | not null | — | `on_delete=CASCADE`, `related_name="managerial_spells"`. A deleted account's history has no meaning. |
| `team` | `FK("teams.Team")` | `null=True, blank=True` | — | `on_delete=SET_NULL`, `related_name="managerial_spells"`. Nullable so the record survives `seed_teams --reset` deleting an unmanaged team. |
| `team_name` | `CharField(max_length=100)` | not null | — | Snapshot at release. This is what gets displayed — Design decision 3. |
| `team_code` | `CharField(max_length=3)` | not null | — | Snapshot at release, same reason. |
| `started_at` | `DateTimeField` | `null=True, blank=True` | none | Game time the spell began, from `Team.managed_since`. NULL for a team claimed before `managed_since` existed. |
| `ended_at` | `DateTimeField` | not null | — | Game time of the release. Supplied by the caller as `at`. |
| `reason` | `CharField(max_length=20, choices=Reason.choices)` | not null | — | See below. |
| `acknowledged_at` | `DateTimeField` | `null=True, blank=True` | none | Real time the ex-manager was shown the message. NULL means not yet shown. |

Inherits `core.models.TimeStampedModel`, like `Team` does.

```python
class Reason(models.TextChoices):
    INACTIVITY = "inactivity", "Manager inactive"
    INSOLVENCY = "insolvency", "Team insolvent"
    ADMIN = "admin", "Released by an operator"
```

`class Meta: ordering = ["-ended_at"]` — history reads newest-first
everywhere it is shown.

Index: `models.Index(fields=["manager", "acknowledged_at"])`. `MeView` runs
the unacknowledged lookup on **every** boot of the SPA for **every** user;
without the index that is a sequential scan on a growing table on the hottest
endpoint in the app.

No uniqueness constraint. A user may manage, lose, re-claim and lose the same
team any number of times, and each is a separate spell.

Migration: `teams/migrations/0004_managerial_spell.py`.

**`ended_at` is game time; `acknowledged_at` is real time.** They are not the
same clock and must not be compared. Game time comes from
`world.services.now()` via the caller (`teams/` must not import `world/` —
the same rule `claim_team`'s `at` parameter already follows);
`acknowledged_at` records when a person actually saw a screen, which is
`django.utils.timezone.now()`, like `TickRun.finished_at` in `world/`.

## `teams/services.py`

```python
class ReleaseError(Exception):
    """Base class for a release that cannot proceed."""


def release_team(team, *, reason: str, at) -> ManagerialSpell | None:
    """Return `team` to the unmanaged pool, recording the spell that just
    ended. Returns None if the team already has no manager.

    Clears Team.manager and Team.managed_since and writes one
    ManagerialSpell. Deliberately touches nothing else — not the roster, not
    the ledger, not the fanbase, not the sponsorship. Release is not claim's
    inverse: claim_team resets the present on the NEXT claim, and a released
    team must be indistinguishable from one that was never managed (#44).

    `at` is the game time the release is recorded at, supplied by the caller
    (world.services.now()) because teams/ must not import world/ — same rule
    as claim_team's `at`.
    """
    with transaction.atomic():
        locked = Team.objects.select_for_update().filter(pk=team.pk).first()
        if locked is None or locked.manager_id is None:
            return None

        spell = ManagerialSpell.objects.create(
            manager_id=locked.manager_id,
            team=locked,
            team_name=locked.name,
            team_code=locked.code,
            started_at=locked.managed_since,
            ended_at=at,
            reason=reason,
        )
        locked.manager = None
        locked.managed_since = None
        locked.save(update_fields=["manager", "managed_since", "updated_at"])
    return spell
```

**The row lock is load-bearing and is `select_for_update()` without
`skip_locked`.** `claim_team` uses `skip_locked` because it is *shopping* for
any free team and should move on rather than block. `release_team` is acting
on **one named team** and must not silently no-op because another transaction
holds the row — skipping there would return `None` and report "already
unmanaged" when it was nothing of the kind. Re-reading the row under the lock
is what makes the `manager_id is None` check honest; checking the passed-in
`team` instance would race against a concurrent release.

Also in this file: `claim_team` sets `managed_since`. Add it to the
assignment block and to `update_fields`:

```python
team.manager = user
team.managed_since = at
team.name = name
team.code = code
team.full_clean(exclude=["manager"])
team.save(update_fields=["manager", "managed_since", "name", "code", "updated_at"])
```

`full_clean(exclude=["manager"])` stays exactly as it is — `managed_since`
has no validator and excluding `manager` is load-bearing for the reason
`teams/README.md` gives.

## `teams/management/commands/release_team.py` (new)

```bash
python manage.py release_team <team-id-or-name> [--reason admin]
```

Resolves the team by pk if the argument is all digits, else by exact `name`.
Raises `CommandError` if no team matches, if the name is ambiguous (it cannot
be — `Team.name` is unique — but a missing team must not be a traceback), or
if the team has no manager. Reads game time itself via `world.services.now()`
**inside `handle()`**, never at module scope — the same entry-point rule
`seed_teams` follows for `racing.models`, and the reason `teams/`'s library
code takes `at` as a parameter.

Prints what it did: the team, the ex-manager's email, and the spell id.

`--reason` defaults to `admin` and accepts any `Reason` value, so a developer
can exercise the paths #63 and #27 will use before either exists.

## `api/serializers.py`

`MeSerializer` gains one nullable nested field:

```python
class LostTeamSerializer(serializers.Serializer):
    spell = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField()
    reason = serializers.CharField()        # the human-readable label
    ended_at = serializers.DateTimeField()


class MeSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    display_name = serializers.CharField(allow_null=True)
    team = MeTeamSerializer(allow_null=True)
    lost_team = LostTeamSerializer(allow_null=True)
```

`reason` serialises the **label** (`get_reason_display()`), not the stored
value — the SPA renders it directly and must not carry its own copy of the
choice list.

## `api/views.py`

`MeView.get` adds the lookup:

```python
lost = None
if user.is_authenticated and team is None:
    spell = (
        ManagerialSpell.objects.filter(manager=user, acknowledged_at__isnull=True)
        .order_by("-ended_at")
        .first()
    )
    if spell is not None:
        lost = {
            "spell": spell.pk,
            "name": spell.team_name,
            "code": spell.team_code,
            "reason": spell.get_reason_display(),
            "ended_at": spell.ended_at,
        }
```

**`team is None` guards the query.** A manager who lost a team and has already
claimed a new one is not shown the message, and — more importantly — the
common case (a logged-in manager with a team) does no extra query at all.
`MeView` is on the SPA's boot path; an unconditional query there is a cost
every user pays on every load for a message almost none of them have.

New view:

```python
class AcknowledgeSpellView(APIView):
    """Mark the ex-manager's lost-team message as seen, so it is shown once.

    404 for a spell that is not the caller's — never 403, which would
    confirm the row exists.
    """

    def post(self, request, spell_id: int):
        updated = ManagerialSpell.objects.filter(
            pk=spell_id, manager=request.user, acknowledged_at__isnull=True
        ).update(acknowledged_at=timezone.now())
        if updated == 0:
            return Response({"detail": "No such message."}, status=404)
        return Response(status=204)
```

The filtered `.update()` is deliberate: it is idempotent and atomic, so a
double-click cannot produce two writes or a lost-update race.

Route in `api/urls.py`: `teams/spells/<int:spell_id>/acknowledge/`.

`timezone.now()` here, not `world.services.now()` — Design decision 7 and the
Data model note explain why acknowledgement is real time.

## `frontend/`

- `api.ts` — add `lost_team` to the `Me` type (nullable), and
  `acknowledgeSpell(spellId: number)` issued through `writeJson` so it carries
  the CSRF token. A bare `fetch` 403s; `frontend/README.md`, *Writes need a
  CSRF token*.
- `useAuth.tsx` — expose `me.lost_team`; after a successful acknowledge,
  clear it in local state rather than re-fetching `me`.
- `ClaimTeam.tsx` — when `me.lost_team` is set, render a card above the claim
  form naming the team and the reason, and call `acknowledgeSpell` once on
  mount (guard with a ref so React 18 StrictMode's double-invoke does not
  fire two requests). The form itself is unchanged.

No new route. `Layout.tsx` already sends a team-less manager to `/claim`, and
that guard is untouched.

## Work items

### W1 — `teams/models.py`: `Team.managed_since` and `ManagerialSpell` ✅ done
Add the field and the model exactly as *Data model* specifies, plus both
migrations. No service changes yet.
**Test:** `teams/tests/test_models.py::test_managerial_spell_orders_newest_first`
and `::test_team_managed_since_defaults_to_null`.

### W2 — `teams/services.py`: `release_team`, and `claim_team` stamps `managed_since` ✅ done
Both halves together — `release_team` reads what `claim_team` writes, and
splitting them leaves a half-wired field.
**Load-bearing:** the `select_for_update()` re-read, and the fact that release
writes nothing to `economy/`.
**Tests:** `teams/tests/test_services.py::test_release_team_clears_manager_and_records_spell`,
`::test_release_team_on_unmanaged_team_is_a_noop`,
`::test_release_team_leaves_roster_and_ledger_untouched` (assert the rider
count and `LedgerEntry` count are identical before and after),
`::test_claim_team_stamps_managed_since`,
`::test_release_team_tolerates_null_managed_since`.

### W3 — `teams/tests/test_services.py`: released team is re-claimable ✅ done (built alongside W2 — same file, same commit)
Release a claimed team, then `claim_team` again, and assert the second claim
takes that team, renames it, and resets balance/fanbase — i.e. the existing
claim path is unchanged by W2.
**Test:** `::test_released_team_can_be_claimed_again`.

### W4 — `teams/management/commands/release_team.py`: the operator entry point ✅ done
The command as specified, `world.services.now()` imported inside `handle()`.
**Tests:** `teams/tests/test_release_team_command.py` (new) —
`::test_releases_by_id`, `::test_releases_by_name`,
`::test_unknown_team_raises_command_error`,
`::test_unmanaged_team_raises_command_error`.

### W5 — `api/`: `lost_team` on `me`, and the acknowledge endpoint ✅ done
Serializer, `MeView` lookup, `AcknowledgeSpellView`, URL.
**Tests:** `api/tests.py::test_me_reports_lost_team_for_teamless_ex_manager`,
`::test_me_omits_lost_team_once_acknowledged`,
`::test_me_omits_lost_team_when_user_has_claimed_again`,
`::test_acknowledge_spell_is_idempotent`,
`::test_acknowledge_another_users_spell_404s`.

### W6 — `frontend/`: show it once on `/claim` ✅ done (79 frontend tests pass via `npx vitest run`)
`api.ts`, `useAuth.tsx`, `ClaimTeam.tsx` as specified.
**Verification is manual** (see below) — this repo has no frontend test
runner.

### W7 — documentation
See *Documentation update*. Its own commit.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7, and the ordering is not arbitrary:

- **W1 before W2** because the service cannot be written against a model that
  does not exist, and landing the migration alone keeps the schema change
  reviewable on its own.
- **W2 before W3** — W3 is purely a test that W2 did not break claiming. It is
  separated because it is the regression that matters most and it should be
  obvious in the log that it was checked.
- **W4 before W5** because the command gives you a way to create a released
  team by hand, which is what makes W5 and W6 testable at all.
- **W5 before W6** — the SPA cannot render a field the API does not send.
- **W7 last**, when what was actually built is known.

Commit after every work item; each leaves the suite green.

## Documentation update (required, not optional)

- **`teams/README.md`** — the substantial one.
  - *Claiming a team*: note that the claim now stamps `managed_since`.
  - **New section, *Releasing a team*:** what `release_team` does and,
    emphatically, what it does not (Design decision 5). State that release
    is **not** claim's inverse and why. Document the `select_for_update()`
    without `skip_locked` and why it differs from `claim_team`'s lock.
  - **New section, *Managerial spells*:** the record, why it lives in
    `teams/` and not `accounts/` (Design decision 1), and why `team_name` is
    a snapshot (Design decision 3).
  - **Correct the existing "only writer" claim.** The file currently says
    `services.claim_team()` is "the only writer of that link". After this it
    is one of **two** writers, both in `teams/services.py`, both atomic. A
    reader trusting the old sentence is exactly the failure this ticket
    introduces.
  - *Future work*: the entry "What happens when a player abandons a team —
    nothing in the game can currently remove a manager from a team" is now
    **done**. Replace it with a pointer to the new sections, and note that
    the triggers (#63, #27) are still outstanding.
- **`api/README.md`** — `lost_team` on `GET /api/accounts/me/`, and the new
  `POST /api/teams/spells/<id>/acknowledge/` with its 404-not-403 rule.
- **`frontend/README.md`** — `/claim` shows the lost-team message once; note
  that `Layout.tsx`'s existing team-less redirect is what routes an
  ex-manager there, unchanged.
- **`accounts/README.md`** — one line under *Not here*: a user's managerial
  history is in `teams/`, because `accounts/` imports nothing.
- **`AGENTS.md`** — the `teams/` row's description mentions claiming; extend
  it to "claiming and releasing a team". No dependency-graph change: this
  adds no new edge.

## Verification

Backend:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python -m pytest teams api -q
/home/mario/dev/cycling-manager/.venv/bin/python -m pytest -q
```

End to end, in the worktree (its own database and port —
`python config/worktree.py` prints them):

```bash
.venv/bin/python manage.py seed_user
.venv/bin/python manage.py seed_teams --claim-for test@mail.com
.venv/bin/python manage.py load_season seasons/season-1.example.json
.venv/bin/python manage.py release_team "Test Team"
.venv/bin/python manage.py runserver
```

Then: log in as `test@mail.com` / `123456789`. You should be bounced to
`/claim` and see the lost-team message naming *Test Team* and "Released by an
operator". Reload — the message is gone, the form is not. Claim a new team;
the dashboard loads normally.

**The likeliest failure mode is that release quietly resets something.** The
temptation to mirror `claim_team`'s `economy/` calls is real (Design decision
5), and a passing "manager is None" assertion would not catch it. The check
that does:

```bash
.venv/bin/python manage.py shell -c "
from teams.models import Team
from economy.models import LedgerEntry
t = Team.objects.get(name='Test Team')
print(t.manager_id, t.riders.count(), LedgerEntry.objects.filter(team=t).count())
"
```

Record those three numbers **before** the release and again after. Rider count
and ledger count must be **identical**; only `manager_id` changes, to `None`.
`test_release_team_leaves_roster_and_ledger_untouched` asserts the same thing
in the suite — make sure it would fail if you added a ledger write, rather
than asserting something that is true either way.

Second failure mode worth a deliberate check: **the message must survive the
team being renamed.** After releasing, claim that same team under a different
name from a second account, then log in as the first account — the message
must still name *Test Team*. A live FK lookup passes every unit test and
fails this.

## Risks

| Risk | Mitigation |
|---|---|
| Implementer mirrors `claim_team`'s `economy/` resets in `release_team`, on the reasonable assumption that release is claim's inverse. | Design decision 5 states it and says what not to do; W2's `test_release_team_leaves_roster_and_ledger_untouched` and the shell check in *Verification* both catch it. |
| The record is put in `accounts/`, inverting the dependency graph. | Design decision 1. A FK from `accounts/` to `teams/` is the tell; `AGENTS.md`'s graph is the authority. |
| `select_for_update(skip_locked=True)` copied from `claim_team` into `release_team`, making a contended release silently report "already unmanaged". | Called out in the `teams/services.py` section; the lock difference is documented in `teams/README.md` per *Documentation update*. |
| `managed_since` is NULL on every pre-existing managed team, and `release_team` crashes or refuses on the first real release. | Design decision 2 marks it load-bearing; `test_release_team_tolerates_null_managed_since` covers it explicitly. |
| `MeView`'s new query runs on every SPA boot for every user. | Guarded by `team is None` so managers with a team never run it, and the `(manager, acknowledged_at)` index covers the case that does. |
| React StrictMode double-invokes the acknowledge call, or a double-click races it. | Ref guard in `ClaimTeam.tsx`, and the filtered `.update()` in `AcknowledgeSpellView` is idempotent regardless. |
| `teams/README.md`'s "only writer of that link" sentence goes uncorrected and misleads the next reader. | An explicit item in *Documentation update*, and W7 is its own commit so it cannot be lost in a squash. |

## Open questions

None.
