# Player accounts — Implementation Plan

**Spec:** `specs/archive/player-accounts.md` · **Issue:** #50 · **Status:** implemented
**Apps touched:** `accounts/`, `api/`, `frontend/`, `config/`

## Context you need

`accounts.User` already exists and is already `AUTH_USER_MODEL` (set in
`config/settings/base.py` before the first migration, deliberately). It
subclasses `AbstractUser` and adds one field, `display_name`. There is no
view, no URL, no serializer and no test in `accounts/` — `accounts/views.py`
is empty and `accounts/tests.py` is the `startapp` stub. There is no
`accounts/README.md`; this change adds one.

Because `User` subclasses `AbstractUser`, it inherits `username` (required,
unique), `email` (**not** unique, blank by default), `first_name`,
`last_name`, `is_staff`, `is_active`, `password`, and the rest. The spec
settles that **email is the login identifier**. That is a data-model
decision, not just a form decision — see D1.

Everything needed to authenticate is already configured and needs no new
dependency:

- `django.contrib.auth`, `django.contrib.sessions` in `INSTALLED_APPS`.
- `SessionMiddleware`, `CsrfViewMiddleware`, `AuthenticationMiddleware` in
  `MIDDLEWARE`, in the right order.
- DRF defaults in `base.py`: `SessionAuthentication` and `IsAuthenticated`.
- `AUTH_PASSWORD_VALIDATORS` — four validators, already on.
- The SPA is served same-origin by Django (`config/urls.py` catch-all), so
  session cookies work without CORS credentials juggling.

`api/` currently has four endpoints. Three (`ClockView`, `PositionView`,
`CalendarView`) are `AllowAny` and **stay that way** — the spec keeps world
data public. The fourth, `SquadView`, is `AllowAny` with the team id in the
URL (`/api/racing/races/<race_id>/squads/<team_id>/`); its docstring and
`api/README.md` both name #50 as what closes it. `frontend/src/screens/Race.tsx`
reads `?team=` from the URL, defaulting to `1`. Closing both is in scope
(spec item 11).

`teams.Team.manager` is a nullable `OneToOneField` to `accounts.User` with
`related_name="team"`, so `request.user.team` is the natural accessor — and
raises `Team.DoesNotExist` when the user manages none. That exception is
load-bearing; see D5.

Repo rules this work is bound by (from `AGENTS.md`): `accounts -> (nothing)`,
so `accounts/` must not import `teams/`. `api/` may import everything. A new
app would need a `README.md` — no new app here, but `accounts/` gets its
first `README.md` regardless. Tests are pytest, run with
`.venv/bin/python -m pytest`; `pyproject.toml` already lists `accounts` and
`api` in `testpaths`.

## Goal

When this is done:

1. `POST /api/accounts/register/` creates a user from email + password +
   display name and logs them in, in one request.
2. `POST /api/accounts/login/` and `POST /api/accounts/logout/` work against
   the session.
3. `GET /api/accounts/me/` tells the SPA who is logged in (or that nobody is)
   and whether they manage a team.
4. The SPA renders a logged-out view, a logged-in-with-no-team spectator
   view, and a logged-in-with-team view, and survives a page reload.
5. `SquadView` derives the team from `request.user`, requires authentication,
   and no longer takes a team id in the URL. `?team=` is gone from the SPA.
6. Clock, position and calendar stay public.

## Design decisions (settled — implement these, do not substitute)

**D1 — Email is the login identifier, and `username` is retired by making it
non-unique and auto-filled. Do not delete the field.**

`AbstractUser.username` is required and unique; `email` is neither. The spec
needs the opposite. Three ways to do this, and only one is cheap here:

- *Swap to `AbstractBaseUser`* — correct-looking, but it means rewriting the
  user model and a migration that Django's own admin, `createsuperuser` and
  `PermissionsMixin` all have opinions about. Too much for this ticket.
- *Keep username as the real identifier and ask for it at signup* —
  contradicts a settled spec decision.
- **Chosen:** keep `username` on the model, set `USERNAME_FIELD = "email"`,
  make `email` unique and required, and give `username` a value derived from
  the email at creation time so nothing that reads it breaks.

Concretely: `USERNAME_FIELD = "email"`, `REQUIRED_FIELDS = []`, `email` gains
`unique=True`, and `username` keeps `unique=True` but is populated by the
manager (see `accounts/models.py` below). **`createsuperuser` will now prompt
for email rather than username** — that is expected, not a bug.

**Load-bearing:** `REQUIRED_FIELDS` must be explicitly set to `[]`.
`AbstractUser.REQUIRED_FIELDS` is literally `["email"]` (verified), and
Django raises `ImproperlyConfigured` when `USERNAME_FIELD` also appears in
`REQUIRED_FIELDS`. Inheriting it unchanged is a startup crash, not a subtle
bug — which is the good outcome, but only if you know why.

Also verified: `AbstractUser.email` is `max_length=254, blank=True,
unique=False`. All three of those change except the length.

**D2 — Session authentication, hand-rolled against `django.contrib.auth`. No
new runtime dependency, and specifically not a third-party auth provider.**

Asked and answered during planning. `django.contrib.auth` +
`SessionAuthentication` is already fully configured; this feature is three
views and a serializer on top of it. A hosted provider (Clerk, Auth0) would
invert the data model — the provider owns the user record and
`accounts.User` becomes a webhook-synced mirror — which puts a network
boundary and an eventual-consistency gap directly underneath
`teams.Team.manager`, the ownership check this ticket exists to make
trustworthy. It also costs money per active user, and its headline features
(password reset, email verification, MFA) are exactly what the spec defers
to #51.

Do not reach for `django-allauth` or `dj-rest-auth` either. They are free and
fine, but they bring URL trees, templates and settings surface far wider than
four endpoints, and `allauth` in particular wants to own the signup flow. If
social login ever becomes a requirement, `django-allauth` is the thing to
revisit — that is the one case where hand-rolling genuinely hurts.

**D3 — Tokens/JWT are not used.** `SessionAuthentication` is already the DRF
default and the SPA is same-origin, so there is no cross-domain problem for a
token to solve. A JWT here would mean inventing refresh/revocation for no
gain.

**D4 — CSRF: the SPA must send `X-CSRFToken` on every unsafe request, and
this is new behaviour that will silently break `PUT` if missed.**

This is the single most likely thing to go wrong. Today `SquadView`'s `PUT`
works without a CSRF token *only because* the session is anonymous —
DRF's `SessionAuthentication` enforces CSRF for authenticated sessions only.
The moment login lands, the same `PUT` starts returning 403.

The fix is `ensureCsrfToken()` in `frontend/src/api.ts` (see that section).
Django sets the `csrftoken` cookie on any response from a view touched by
`CsrfViewMiddleware`; `GET /api/accounts/me/` is annotated `@ensure_csrf_cookie`
so the SPA reliably has one before it ever issues a write.

**D5 — `request.user.team` raises, it does not return `None`.** `manager` is
a `OneToOneField` with `related_name="team"`, so the reverse accessor is a
`ReverseOneToOneDescriptor` and raises `Team.RelatedObjectDoesNotExist` when
the user manages nothing. Catch it as `Team.DoesNotExist` — verified: the
raised class subclasses it.

**The trap:** that exception *also* subclasses `AttributeError` (its MRO is
`RelatedObjectDoesNotExist → DoesNotExist → ObjectDoesNotExist →
AttributeError`). So `getattr(user, "team", None)` swallows it and returns
`None` — which looks correct and is, by accident, for the wrong reason. It
would also swallow a genuine typo or a renamed relation, turning a crash into
a silent "you have no team". Use the explicit `try/except Team.DoesNotExist`
in `team_for()`; do not shorten it to `getattr`.

Do not "fix" this by making the accessor nullable either — that means a
migration on `teams/` this ticket does not need.

**D6 — Registration is one request, not two.** The spec says registering logs
the player in immediately. `RegisterView` calls `django.contrib.auth.login()`
itself after creating the user. Do not make the SPA chain register → login;
that is two round trips and two failure modes for one user action.

**D7 — Login failures are deliberately vague; registration failures are
not.** The spec settles this: a wrong password and an unknown email both
return the same "email or password is wrong" (no account enumeration), but a
duplicate registration says plainly that the email is taken. That asymmetry
is intentional — registration cannot hide the collision and still be usable.

**D8 — `SquadView`'s URL loses `<team_id>` entirely.** Not "keeps it and
checks it" — removes it. A URL that carries a team id the server then
overrides is a lie, and the next reader will wire something to it. New path:
`/api/racing/races/<int:race_id>/squad/` (singular — it is now *your* squad,
not an arbitrary team's).

**D9 — `accounts/` must not import `teams/`.** `AGENTS.md` puts `accounts` at
the root of the dependency graph. The "does this user have a team" question
is therefore answered in `api/` (which may import everything), never in
`accounts/serializers.py`. This is why `MeView` lives in `api/`, not in
`accounts/`.

## Data model

No new models. One changed model and one new manager.

### `accounts.User` (changed)

| Field | Change | Type | Null/blank | Default | Constraint |
|---|---|---|---|---|---|
| `email` | **changed** | `EmailField` | `null=False`, `blank=False` | none | `unique=True` |
| `username` | unchanged on paper | `CharField(150)` | `null=False`, `blank=False` | none | `unique=True`, auto-filled |
| `display_name` | unchanged | `CharField(50)` | `blank=True` | `""` | — |

Class attributes added: `USERNAME_FIELD = "email"`, `REQUIRED_FIELDS = []`,
`objects = UserManager()`.

**Migration:** `accounts/migrations/0002_email_login.py` — `AlterField` on
`email` (unique, non-blank), plus `AlterModelManagers`. `USERNAME_FIELD` and
`REQUIRED_FIELDS` are not database state, but Django records them via
`AlterModelOptions` in some versions; let `makemigrations` decide rather than
hand-writing it.

**The existing-rows problem.** `unique=True` on a column where every existing
row is `""` fails the moment there is more than one user. Today the only
users are superusers created by hand, and dev databases are disposable — but
the migration must still be safe to run. Include a data migration step ahead
of the `AlterField` that fills blank emails with a placeholder derived from
the primary key:

```python
def backfill_emails(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(email=""):
        user.email = f"user{user.pk}@invalid.local"
        user.save(update_fields=["email"])
```

`.invalid` is reserved by RFC 2606 and can never be a real address, so a
backfilled row is obvious and unroutable. Pair it with a no-op reverse so the
migration is reversible.

## `accounts/models.py`

Add a manager. `AbstractUser`'s default `UserManager.create_user` insists on a
username; ours derives one.

```python
class UserManager(BaseUserManager):
    """Creates users keyed on email. `username` is still a required, unique
    column inherited from AbstractUser, so it is derived rather than asked
    for — see specs/archive/player-accounts-plan.md, D1."""

    use_in_migrations = True

    def _derive_username(self, email: str) -> str:
        base = slugify(email.split("@")[0])[:30] or "player"
        candidate = base
        suffix = 1
        while self.model.objects.filter(username=candidate).exists():
            suffix += 1
            candidate = f"{base}{suffix}"
        return candidate

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        extra.setdefault("username", self._derive_username(email))
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)
```

**Load-bearing:** the `while` loop is not decoration. Two players registering
as `mario@a.com` and `mario@b.com` both derive `mario`, and the second
`INSERT` would violate the unique constraint. There is a race here under
concurrent signups; it is acceptable (the loser gets a 500 and retries, at
playtest scale) and noted under Risks rather than solved with a lock.

`User` gains `USERNAME_FIELD`, `REQUIRED_FIELDS`, `objects`, and `email` is
redeclared as `models.EmailField(unique=True)`.

## `accounts/serializers.py` (new)

```python
class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    display_name = serializers.CharField(max_length=50)

    def validate_email(self, value): ...   # normalised, case-insensitive uniqueness check
    def validate_password(self, value): ...  # runs django.contrib.auth.password_validation
    def create(self, validated_data): ...    # User.objects.create_user(...)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
```

`validate_email` must compare case-insensitively (`User.objects.filter(
email__iexact=value).exists()`) and return `normalize_email(value)`. Postgres
`unique=True` is case-*sensitive*, so without this `Mario@x.com` and
`mario@x.com` are two accounts that look identical to a human.

`validate_password` calls `django.contrib.auth.password_validation.validate_password`
and re-raises `DjangoValidationError` as DRF's `ValidationError`. The four
validators are already configured in `base.py`; this is what actually invokes
them — a serializer that skips this accepts `"1"` as a password.

## `accounts/views.py`

Three views. All `AllowAny` — you cannot require authentication to log in.

```python
class RegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request): ...   # serializer -> create_user -> login() -> 201


class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request): ...   # authenticate() -> login() -> 200, or 400


class LogoutView(APIView):
    permission_classes = [AllowAny]
    def post(self, request): ...   # logout() -> 204
```

`authenticate(request, username=email, password=password)` — **use the
`username=` keyword**, even though `USERNAME_FIELD` is `email`.

Both spellings happen to work: `ModelBackend.authenticate` (verified against
the installed Django 6.1.1) takes `username=None` positionally and falls back
to `kwargs.get(UserModel.USERNAME_FIELD)` when it is `None`, so `email=...`
resolves too. Use `username=` anyway — it is the parameter in the backend's
signature, it keeps working if a second backend is ever added that does not
implement the fallback, and it is what every piece of Django documentation
shows. Do not rely on the kwargs path.

On failure, return `{"detail": "Email or password is wrong."}` with 400 for
both the unknown-email and wrong-password cases (D7). Do not branch.

`login()` cycles the session key, which is the CSRF-relevant part: the SPA
must re-read the `csrftoken` cookie after login. Handled in `api.ts`.

`LogoutView` is `AllowAny` and idempotent — logging out when already logged
out is 204, not an error.

## `accounts/urls.py` (new)

```python
app_name = "accounts"
urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
```

Included from `api/urls.py` as `path("accounts/", include("accounts.urls"))`,
so the SPA sees `/api/accounts/…`. `config/urls.py` is untouched — it already
routes `/api/` above the SPA catch-all, and adding a second top-level include
would risk landing below it.

## `api/views.py`

**`MeView` (new).** Lives here, not in `accounts/`, because it answers a
question about teams and `accounts/` may not import `teams/` (D9).

```python
def team_for(user):
    """The user's team, or None. `Team.manager` is a OneToOneField, so the
    reverse accessor raises rather than returning None — see D5."""
    if not user.is_authenticated:
        return None
    try:
        return user.team
    except Team.DoesNotExist:
        return None


class MeView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request): ...
```

Returns, for an anonymous visitor:

```json
{"authenticated": false, "display_name": null, "team": null}
```

and for a logged-in player:

```json
{"authenticated": true, "display_name": "Mario",
 "team": {"id": 3, "name": "Movistar", "code": "MOV"}}
```

with `"team": null` when they manage none. One endpoint answers both "who are
you" and "do you have a team", so the SPA needs one request on boot, not two.

`@ensure_csrf_cookie` is load-bearing (D4): this is the request that
guarantees the SPA holds a CSRF token before any write.

**`SquadView` (changed).** Signature drops `team_id`:

```python
class SquadView(APIView):
    # permission_classes removed -> falls back to the project default,
    # IsAuthenticated. Do not re-add AllowAny.

    def get(self, request, race_id: int): ...
    def put(self, request, race_id: int): ...
```

Both methods start with:

```python
team = team_for(request.user)
if team is None:
    return Response({"detail": "You do not manage a team."}, status=403)
```

403 rather than 404: the caller is authenticated, they just have nothing to
act on. Everything downstream of `team` is unchanged — `suggested_squad`,
`set_squad`, `_squad_payload` and the serializers all keep working as-is.

**`ClockView`, `PositionView`, `CalendarView` — unchanged.** Their `AllowAny`
stays. Update only the docstring reason: no longer "there is no login flow
yet" but "world data is public by design". A reader who sees the old wording
after this ships will assume it is a leftover and lock them down.

## `api/urls.py`

```python
path("accounts/", include("accounts.urls")),
path("accounts/me/", MeView.as_view(), name="me"),
path("racing/races/<int:race_id>/squad/", SquadView.as_view(), name="squad"),
```

The old `…/squads/<int:team_id>/` path is **removed**, not aliased (D8).

## `frontend/src/api.ts`

Add CSRF handling and the account calls. The existing `getClock`/`getPosition`/
`getCalendar` are unchanged (all `GET`, no token needed).

```ts
function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`))
  return match ? decodeURIComponent(match[2]) : null
}

/** Django sets `csrftoken` on any CsrfViewMiddleware-touched response;
 *  GET /api/accounts/me/ is @ensure_csrf_cookie so one call guarantees it. */
async function ensureCsrfToken(): Promise<string> {
  let token = readCookie('csrftoken')
  if (token) return token
  await fetch('/api/accounts/me/')
  token = readCookie('csrftoken')
  if (!token) throw new Error('no CSRF token available')
  return token
}

async function post<T>(url: string, body: unknown): Promise<T> { ... }
```

`post` sets `X-CSRFToken`, `Content-Type: application/json`, and
`credentials: 'same-origin'`. Every write goes through it.

`putSquad` must be changed to use the same token path — it currently issues a
bare `PUT` and will start 403ing (D4).

New functions: `getMe()`, `register(email, password, displayName)`,
`login(email, password)`, `logout()`. `getSquad`/`putSquad` lose their
`teamId` parameter and call `/api/racing/races/${raceId}/squad/`.

New types: `Me`, `MeTeam`.

## `frontend/src/useAuth.tsx` (new)

A context, not a hook-per-component — the sidebar, the race screen and the
route guard all need the same answer, and three independent `getMe()` calls
on boot is three round trips for one fact.

```tsx
interface AuthState {
  me: Me | null          // null while the first fetch is in flight
  loading: boolean
  register: (email: string, password: string, displayName: string) => Promise<void>
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export function AuthProvider({ children }: { children: React.ReactNode }): JSX.Element
export function useAuth(): AuthState
```

`AuthProvider` calls `getMe()` once on mount — that call is what satisfies
spec item 6 (login survives a reload): the session cookie is already in the
browser, so the SPA re-learns who it is without the player retyping anything.

`register`/`login`/`logout` each refresh `me` from their own response rather
than re-fetching, except `logout`, which sets `me` to the anonymous shape
directly.

**While `loading` is true, render nothing auth-dependent** — the same
discipline `useCalendar` already follows. A sidebar that flashes "Log in" for
200ms before showing the player's name looks broken.

## `frontend/src/screens/Login.tsx`, `Register.tsx` (new)

Two small forms. Inline styles from `theme.ts`, per `frontend/README.md`
conventions — no CSS framework, no colour literals.

Each renders: the fields, a submit button disabled while in flight, and the
server's error message on failure. Register additionally shows the
password-validation messages, which arrive as a list from DRF.

A player who is already logged in and lands on either route is redirected to
`/` (spec: both screens are a no-op for them).

## `frontend/src/screens/Race.tsx`

Remove `useSearchParams` and the `teamId` line entirely, plus the comment
block explaining the stand-in. `useSquad(Number(raceId))` — one argument.

Add the no-team case: if `me.team` is null, the screen says the player does
not manage a team rather than rendering an empty squad picker.

## `frontend/src/components/Layout.tsx` and `Sidebar.tsx`

`Layout` currently reads `TEAM` from `placeholderData`. Replace with
`useAuth()`: show the real team name when there is one, the player's display
name and a log-out control when logged in, and log-in / register links when
not.

`placeholderData.TEAM` stays in the file — other screens (Dashboard, Roster)
still read it and are out of scope for this ticket.

## `frontend/src/App.tsx`

Wrap `<BrowserRouter>` contents in `<AuthProvider>`. Register `/login` and
`/register` as explicit routes **outside** the `SCREENS` map — like
`/race/:raceId`, they are not nav items and must not appear in the sidebar.

## Work items

### W1 — `accounts/models.py` + migration: email as the login identifier ✅
Add `UserManager`, `USERNAME_FIELD`, `REQUIRED_FIELDS`, redeclare `email` as
unique. Write `0002_email_login.py` with the backfill (see Data model) ahead
of the `AlterField`.
**Test:** `accounts/tests.py::test_create_user_derives_a_username_from_the_email`,
`::test_create_user_rejects_a_duplicate_email`,
`::test_derived_usernames_do_not_collide` (two emails with the same local
part), `::test_create_superuser_is_staff_and_superuser`.
**Load-bearing:** the collision loop. The third test is the one that proves it.

### W2 — `accounts/serializers.py`: register and login serializers ✅
`RegisterSerializer` with case-insensitive email uniqueness and
`validate_password` wired to Django's validators; `LoginSerializer`.
**Test:** `accounts/tests.py::test_register_serializer_rejects_a_weak_password`,
`::test_register_serializer_rejects_a_duplicate_email_case_insensitively`.

### W3 — `accounts/views.py` + `accounts/urls.py`: register, login, logout ✅
Three views, wired into `api/urls.py` under `accounts/`.
**Test:** `accounts/tests.py::test_register_creates_a_user_and_logs_them_in`,
`::test_login_succeeds_with_correct_credentials`,
`::test_login_fails_identically_for_unknown_email_and_wrong_password` (assert
the two response bodies are equal — that is what proves D7),
`::test_logout_ends_the_session`.

### W4 — `api/views.py`: `MeView` and `team_for` ✅
The endpoint plus the helper. `@ensure_csrf_cookie` on the `GET`.
**Test:** `api/tests.py::test_me_reports_anonymous_for_a_visitor`,
`::test_me_reports_the_logged_in_player_and_their_team`,
`::test_me_reports_null_team_for_a_player_without_one` (the D5 case — this
test fails with `Team.DoesNotExist` if `team_for` is written naively),
`::test_me_sets_the_csrf_cookie`.

### W5 — `api/views.py` + `api/urls.py`: `SquadView` derives the team ✅
Drop `team_id` from both methods and the URL, drop `AllowAny`, add the
`team_for` guard. Remove the old path.
**Test:** `api/tests.py::test_squad_requires_authentication` (403 anonymous),
`::test_squad_returns_the_callers_own_team`,
`::test_squad_put_saves_for_the_callers_own_team`,
`::test_squad_forbids_a_player_with_no_team`.
**Load-bearing:** the first test is the regression guard for the hole this
ticket exists to close.

**This item breaks existing tests, and updating them is part of it.** There
are already squad tests in `api/tests.py` — around lines 186–230 at time of
writing — that call the old `…/squads/<team_id>/` path with a bare
`APIClient()`. Every one of them needs the new path and
`client.force_authenticate(user=...)` with a user whose `team` is
`squad_team`. The `squad_team` fixture (line 162) should gain a manager for
this. Do **not** make them pass by re-adding `AllowAny`.

Suite size is 163 before this work; expect it to grow, never shrink. A
shrinking count means a test was deleted rather than updated.

### W6 — `api/views.py`: restate the public-endpoint docstrings ✅
Docstring-only change on `ClockView`, `PositionView`, `CalendarView`: the
reason for `AllowAny` becomes "world data is public by design".
**Test:** none — no behaviour changes. Covered by the existing endpoint tests
continuing to pass anonymously.

### W7 — `frontend/src/api.ts`: CSRF plumbing and account calls ✅
`readCookie`, `ensureCsrfToken`, `post`. `getMe`, `register`, `login`,
`logout`. `getSquad`/`putSquad` lose `teamId` and route to the new path;
`putSquad` goes through the token path.
**Test:** none (no frontend test harness in this repo). Proven in
Verification.

### W8 — `frontend/src/useAuth.tsx`: the auth context ✅
Provider + hook, `getMe()` on mount.

### W9 — `frontend/src/screens/Login.tsx` + `Register.tsx` + `App.tsx` ✅
The two forms, `AuthProvider` wrapping the router, two explicit routes.

### W10 — `frontend/src/screens/Race.tsx` + `components/Layout.tsx` ✅
Drop `?team=`, drop `placeholderData.TEAM` from the layout, render the real
identity and the no-team state. Also touched `Sidebar.tsx` and `useSquad.ts`
(the design section for this item covers both; `useSquad.ts` needed its
signature updated to match D8's `getSquad`/`putSquad` change) — not named in
the work-item heading but required by it. Verified end to end in the browser:
register → immediate login → reload preserves the session → no-team
spectator message on a race screen → assigning a team and saving a squad
succeeds (the CSRF path, D4) → logout returns to the spectator view.

### W11 — Documentation ✅
`accounts/README.md` (new), `api/README.md`, `frontend/README.md`. See below.
Also updated `AGENTS.md`'s domain table and project-structure tree to mark
`accounts/` as having a `README.md` now, per the project's own convention.

## Execution order

W1 → W2 → W3 land the backend auth in dependency order; each leaves the suite
green on its own. **Commit after W3** — that is the first point where the
feature exists end to end at the API level and can be exercised with `curl`.

W4 before W5 because `team_for` is defined in W4 and consumed in W5, and
because `MeView` is the simpler consumer to debug it in. W5 is where the
existing squad tests will break (they pass a team id); fixing them is part of
W5, not a follow-up. **Commit after W5.**

W6 is trivial and independent — fold it in anywhere after W5.

W7 before W8–W10: every frontend piece calls through `api.ts`, and doing it
first means the rest is wiring rather than wiring-plus-plumbing. W10 last
because it is the only item that touches screens other people's tickets also
touch. **Commit after W10.**

W11 last, once what actually got built is known.

## Documentation update (required, not optional)

**`accounts/README.md` — new.** The app has never had one. Sections: what the
app owns (the `User` model and the three auth endpoints); *Email as the login
identifier* (D1 — why `username` still exists and is derived, and that
`createsuperuser` now prompts for email); *What `accounts/` may import*
(nothing — and why `MeView` therefore lives in `api/`, per D9); *Session
authentication* (D2/D3, including why no third-party provider and the
`django-allauth` note for social login); *Not here* (password reset et al →
#51).

**`api/README.md`.** Rewrite the *Authentication* section wholesale — it
currently describes the `AllowAny` workaround and the squad hole as open,
both of which this closes. It must now say: the project default is
`IsAuthenticated`; clock/position/calendar are `AllowAny` **by design**
because world data is public; the squad endpoint derives the team from
`request.user`; and the CSRF story is settled (authenticated sessions enforce
it, the SPA sends `X-CSRFToken`). Add `/api/accounts/…` and
`/api/accounts/me/` to *What exists*, and update the squad endpoint's path —
the documented URL changes.

**`frontend/README.md`.** The `?team=` paragraph and the "no login flow to
derive it from yet" note are both now false — replace with how the SPA learns
identity (`useAuth`, `getMe` on mount) and the CSRF requirement for writes.
Add `/login` and `/register` to the route table, noting they are explicit
routes outside `SCREENS` like `/race/:raceId`. Note that `placeholderData.TEAM`
is no longer what the layout reads.

## Verification

```bash
docker compose up -d
.venv/bin/python manage.py migrate
.venv/bin/python -m pytest
```

The suite must be green, and the new tests in W1–W5 must be tests that could
have failed — in particular `test_squad_requires_authentication`, which fails
loudly against today's `AllowAny`.

End to end, with the SPA built and served by Django (the way it ships — the
Vite dev server proxies `/api` and would mask a same-origin cookie problem):

```bash
npm --prefix frontend run build && .venv/bin/python manage.py runserver
```

Then, in a browser:

1. Visit `/` logged out. The calendar renders. No login wall. *(spec 10)*
2. Register. You land logged in, without a second login step. *(spec 2)*
3. **Reload the page.** You are still logged in. *(spec 6 — the check most
   likely to be skipped, and the one that catches a session cookie that was
   never actually set.)*
4. With no team, open a race from the calendar. The screen says you manage no
   team; it does not render an empty picker or throw. *(spec 7, D5)*
5. Assign yourself a team (`manage.py shell`: set `team.manager`), reload,
   open the same race, change the squad and **save**. This is the CSRF check
   (D4) — if `X-CSRFToken` is missing this returns 403 and nothing else in
   the flow reveals it.
6. Log out. The calendar still renders; the team name is gone.

**The likeliest failure mode is D4** — everything above passes except step 5,
because `GET` never needed a token. A `PUT` that 403s with
`"CSRF Failed: CSRF token missing"` in the response body is the signature.

**The second likeliest is the `email` unique migration** against a database
that already holds more than one hand-made superuser with a blank email.
Signature: `migrate` fails with a duplicate-key violation on
`accounts_user_email_key`, before any of the above runs. The backfill step in
W1 is what prevents it; a dev who wrote the `AlterField` without it will hit
this immediately.

## Risks

| Risk | Mitigation |
|---|---|
| Authenticated `PUT` starts failing CSRF (D4) — the flagship regression, and invisible to every `GET`-only check | `ensureCsrfToken()` in `api.ts`; `@ensure_csrf_cookie` on `MeView`; Verification step 5 exercises a real save |
| `authenticate()` called with the wrong keyword | Less dangerous than it looks — `ModelBackend` falls back to `USERNAME_FIELD` (verified on Django 6.1.1), so both spellings work today. Use `username=` per `accounts/views.py` above so it survives a second backend; `test_login_succeeds_with_correct_credentials` covers it either way |
| `request.user.team` raises `Team.DoesNotExist` instead of returning `None` (D5) | `team_for()` helper; `test_me_reports_null_team_for_a_player_without_one` |
| The `email` unique migration fails on a database with several blank-email users | Backfill data migration ahead of the `AlterField`, using `@user<pk>.invalid` |
| Derived usernames collide under concurrent signup | Accepted at playtest scale — the loser gets a 500 and retries. Do not add a lock for this; revisit if signup volume ever justifies it |
| `REQUIRED_FIELDS` left containing `"email"` → `ImproperlyConfigured` at startup | Flagged load-bearing in D1; the whole suite fails immediately, so it cannot ship |
| Case-variant emails become two accounts | `validate_email` compares `email__iexact` and stores `normalize_email` |
| W5 breaks existing squad tests and they get "fixed" by re-adding `AllowAny` | Execution order puts the test update inside W5; `test_squad_requires_authentication` makes the regression explicit |

## Open questions

None. The spec's `Open questions` section is empty, and every technical
decision this needed is settled above.
