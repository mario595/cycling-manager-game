# API tokens and API docs — Implementation Plan

**Spec:** `specs/api-tokens.md` · **Issue:** #130 · **Status:** proposed
**Apps touched:** `accounts/`, `api/`, `config/` (settings, urls), `requirements.txt`

## Context you need

Every endpoint lives in `api/` (`api/urls.py`, `api/views.py`), apart from
register, login and logout, which are in `accounts/` (`accounts/views.py`,
included at `/api/accounts/`). `config/settings/base.py`'s `REST_FRAMEWORK` sets
`SessionAuthentication` as the only authenticator and `IsAuthenticated` as the
default permission. An anonymous request gets a **403** today, and
`api/README.md`, *Authentication*, documents that. The SPA never tells 401 and
403 apart (`frontend/src/api.ts` throws on any non-2xx), but the backend tests
assert 403 for anonymous callers.

`accounts/` imports nothing (AGENTS.md, *Dependency direction*). The game-time
"last seen" stamp exists because of that: `User.last_seen_at` is written with
`world.services.now()`, but only `api/` may call that. So `api.views.LoginView`
subclasses `accounts.views.LoginView` and calls `api.services.touch_last_seen`
(`accounts/README.md`, *Last seen is game time*). `world.services._release_inactive`
releases a team whose manager's `last_seen_at` is ten or more in-season weeks
old. **An account with `last_seen_at = NULL` is exempt.** A token-only agent never
logs in, so today it would be exempt forever.

Most views are plain `APIView`s that validate input with a serializer from
`api/serializers.py` (`SquadWriteSerializer`, `PlaceBidSerializer`,
`SignOfferSerializer`, …) and build their response with another serializer or a
dict. No view declares `serializer_class`, so a schema generator can't infer any
request or response body without help.

`config/urls.py` ends with an SPA catch-all, `path("<path:unused>", …index.html)`,
which matches **any** path, including `/api/` paths that don't exist and `/api/`
paths missing their trailing slash. A token client that mistypes a URL gets
`200 text/html`.

No `CACHES` setting exists, so Django uses its default per-process `LocMemCache`.

## Goal

- A per-account, revocable, hashed API token, issued and revoked with management
  commands, accepted on every endpoint alongside the session.
- Token requests stamp `last_seen_at`, so the inactivity rule covers agents.
- Token requests are throttled per account at 60 a minute. Session requests are not.
- `/api/schema/` (OpenAPI 3) and `/api/docs/` (a rendered page), both for
  authenticated users only, with a game-terms summary and description on every
  operation, enforced by a test.
- Unknown `/api/…` paths return a JSON 404 instead of the SPA's HTML.
- The browser-assumption audit is written up in `api/README.md`.

## Design decisions (settled — implement these, do not substitute)

1. **Build a small hashed-key model, not DRF's `rest_framework.authtoken`.**
   `authtoken` stores the key in plain text, which breaks spec item 3: a token
   can't be recovered by anyone reading the database. Store `sha256(key)` as a
   hex string. Plain SHA-256 with no salt and no slow hash is correct here: the
   key is 32 random bytes, so there's nothing to brute-force, and a slow hash
   would add milliseconds to *every request*. Don't reach for `make_password`.
2. **One token per account is a `OneToOneField`.** Issuing a token deletes any
   existing row and creates a new one, in one transaction, so the old key stops
   working the moment the new one exists.
3. **The header is `Authorization: Bearer <key>`.** Subclass
   `rest_framework.authentication.TokenAuthentication` and set
   `keyword = "Bearer"`. `Bearer` is what generic HTTP and agent tooling sends by
   default. DRF's `Token` keyword is not accepted.
4. **Key format: `cm_` + `secrets.token_urlsafe(32)`.** The prefix makes a
   leaked key easy to recognise in a log or a secret scanner. Store the first
   eight characters after `cm_` as `prefix`, so the admin and the commands can
   show *which* token an account has without being able to reproduce it.
5. **Two authentication classes in two apps.** `accounts/authentication.py`
   (new) holds `ApiTokenAuthentication`, which looks the key up and checks the
   user is active. It imports only `accounts.models`. `api/authentication.py`
   (new) subclasses it as `GameTokenAuthentication` and stamps `last_seen_at`
   with `world.services.now()`. This is the same split as `LoginView`, for the
   same reason, and the settings name the `api/` class. **Do not** import
   `world` from `accounts/`.
6. **Order in `DEFAULT_AUTHENTICATION_CLASSES`: session first, then token.**
   DRF takes the 401-vs-403 choice from the *first* class's
   `authenticate_header`. Session first keeps every anonymous response a 403,
   as today and as the suite asserts, and a bad token is refused with
   `403 {"detail": "Invalid token."}`. That satisfies spec item 5 (a plain JSON
   refusal, never a redirect). Putting the token class first would turn every
   anonymous 403 in the suite into a 401 for no gain for players.
   *Load-bearing:* `SessionAuthentication` enforces CSRF only when it is the
   class that authenticated, so a token request carrying no session cookie
   needs no CSRF token (spec item 6). Don't add `csrf_exempt` anywhere.
7. **Stamp `last_seen_at` at most once per game hour.** Writing on every request
   would put an `UPDATE` on every read. Inactivity is counted in weeks, so an
   hour of resolution loses nothing. Stamp when `last_seen_at is None` or
   `abs(now - last_seen_at) >= LAST_SEEN_RESOLUTION` (`timedelta(hours=1)`).
   `abs` because `MockClock` can be set backwards in dev. Reuse
   `api.services.touch_last_seen`, which already uses `update_fields`.
8. **Throttle with a DRF `UserRateThrottle` subclass that only counts token
   requests.** `api/throttling.py` (new) has `TokenRateThrottle(UserRateThrottle)`
   with `scope = "token"`, and `allow_request` returns `True` straight away
   unless `isinstance(request.auth, ApiToken)`. Set
   `DEFAULT_THROTTLE_RATES = {"token": "60/min"}` and
   `DEFAULT_THROTTLE_CLASSES` project-wide. The cache key is the user id
   (`UserRateThrottle`'s default), so reissuing a token doesn't reset the
   count, as the spec requires. DRF's `Throttled` already sends `429`,
   `Retry-After` and "Expected available in N seconds". **No new cache
   backend:** the per-process `LocMemCache` means each worker counts
   separately, so the real ceiling is 60 × the number of workers. That is fine
   for protecting the server, and it's recorded under Risks. Don't add Redis.
9. **Use drf-spectacular for the schema** (named in the ticket). It is the
   only new runtime dependency. `SERVE_PERMISSIONS = IsAuthenticated` for
   both views. Serve the docs page with **Redoc** (`SpectacularRedocView`)
   rather than Swagger UI: the page is for reading, and Swagger's "try it"
   would fight the session's CSRF. Redoc loads its JS from jsDelivr, which is
   fine for an authenticated docs page.
10. **Descriptions live on the views, via `@extend_schema`.** Every operation
    gets a `summary` (a short imperative sentence: "Bid on an auction") and a
    `description` in game terms: what it changes, what it costs, when it's
    refused (the 400/403/404 cases), and which scale the numbers use. Give
    `request=` the serializer the view already validates with, and
    `responses=` the serializer it already returns, or an `inline_serializer`
    for a dict-built response. Global conventions go once, in
    `SPECTACULAR_SETTINGS["DESCRIPTION"]`, not on every endpoint: `Bearer`
    auth, `$` money as whole units, the 0–10 display scale, game time and the
    clock, "your team is always the caller's own", and the 60/min limit.
    `accounts/views.py` decorates its own three views. drf-spectacular is a
    library, not a game app, so this doesn't break `accounts/`'s
    "imports nothing" rule.
11. **A test enforces the descriptions.** One test generates the schema and
    fails if any operation lacks a non-empty `summary` or a `description`
    of at least 40 characters. Another runs
    `call_command("spectacular", "--validate", "--fail-on-warn")`. Together
    they make spec item 10 and the "an endpoint added later appears
    automatically" rule hard to break silently.
12. **A JSON 404 for unknown API paths.** Add a last pattern to `api/urls.py`:
    `re_path(r"^.*$", api_not_found)`, a plain Django view returning
    `JsonResponse({"detail": "No such API endpoint. API paths end with a slash."}, status=404)`.
    It sits inside the `api/` include, so it can't swallow the SPA's paths.
    Exclude it from the schema.
13. **Logout stays as it is.** `POST /api/accounts/logout/` with a token
    returns 204 and does nothing to the token. The docs say so, because the
    spec keeps browser logout and token revocation separate.

## Data model

`accounts/models.py`, new model `ApiToken`:

| Field | Type | Null/blank | Default | Notes |
|---|---|---|---|---|
| `user` | `OneToOneField(User, on_delete=CASCADE, related_name="api_token")` | no | — | One token per account |
| `key_hash` | `CharField(max_length=64, unique=True)` | no | — | `hashlib.sha256(key.encode()).hexdigest()`; the unique index is the lookup |
| `prefix` | `CharField(max_length=8)` | no | — | First eight characters after `cm_`, display only |
| `created_at` | `DateTimeField(auto_now_add=True)` | no | — | **Real** time. Operator metadata, not game state, so it does not use `world.now()` |

`__str__` returns `f"{self.user.email} cm_{self.prefix}…"`. Migration:
`accounts/migrations/0004_apitoken.py`.

## accounts/tokens.py (new)

```python
TOKEN_PREFIX = "cm_"

def hash_key(key: str) -> str: ...
def issue_token(user) -> str:
    """Replace any existing token and return the raw key. The only time it exists in clear."""
    with transaction.atomic():
        ApiToken.objects.filter(user=user).delete()
        key = TOKEN_PREFIX + secrets.token_urlsafe(32)
        ApiToken.objects.create(user=user, key_hash=hash_key(key), prefix=key[3:11])
    return key
def revoke_token(user) -> bool:  # True if there was one
def user_for_key(key: str) -> tuple[User, ApiToken] | None:
    # select_related("user"); None if unknown or user inactive
```

## accounts/authentication.py (new)

`ApiTokenAuthentication(TokenAuthentication)` with `keyword = "Bearer"`. Override
`authenticate_credentials(self, key)` to call `user_for_key` and raise
`AuthenticationFailed("Invalid token.")` on `None`. Return `(user, token)`, so
`request.auth` is the `ApiToken` row, which the throttle checks.

## api/authentication.py (new)

`GameTokenAuthentication(ApiTokenAuthentication)`, which overrides
`authenticate_credentials` to call `super()` and then `_maybe_touch(user)`
(decision 7). `LAST_SEEN_RESOLUTION = timedelta(hours=1)` is module-level.

## api/throttling.py (new)

`TokenRateThrottle(UserRateThrottle)`, `scope = "token"`, as in decision 8.

## Management commands (new, `accounts/management/commands/`)

- `issue_api_token <email>` prints the key on its own line plus one line of
  explanation ("shown once; issuing again replaces it"). `CommandError` if
  there's no user.
- `revoke_api_token <email>` prints "revoked" or "no token". `CommandError`
  if there's no user.

The email lookup is `email__iexact`, matching registration (`accounts/README.md`).

## accounts/admin.py

Register `ApiToken` as read-only: `list_display = (user, prefix, created_at)`,
no add permission, no change permission. Delete is allowed and means revoke.

## config/settings/base.py

- `THIRD_PARTY_APPS += ["drf_spectacular"]`
- `REST_FRAMEWORK`: authentication `[SessionAuthentication, "api.authentication.GameTokenAuthentication"]`;
  `DEFAULT_THROTTLE_CLASSES = ["api.throttling.TokenRateThrottle"]`;
  `DEFAULT_THROTTLE_RATES = {"token": "60/min"}`;
  `DEFAULT_SCHEMA_CLASS = "drf_spectacular.openapi.AutoSchema"`.
- `SPECTACULAR_SETTINGS`: `TITLE = "Cycling Manager API"`, `VERSION = "1"`,
  `DESCRIPTION` (the global conventions from decision 10, as Markdown),
  `SERVE_INCLUDE_SCHEMA = False`,
  `SERVE_PERMISSIONS = ["rest_framework.permissions.IsAuthenticated"]`,
  `COMPONENT_SPLIT_REQUEST = True`.
- drf-spectacular needs an `OpenApiAuthenticationExtension` for the custom class
  (`target_class = "api.authentication.GameTokenAuthentication"`, an HTTP bearer
  scheme). Put it in `api/schema.py` (new) and import it from `ApiConfig.ready()`.

`requirements.txt`: add `drf-spectacular>=0.27` under Runtime.

## api/urls.py

Add `schema/` → `SpectacularAPIView` (name `schema`) and `docs/` →
`SpectacularRedocView(url_name="api:schema")`. Then add the catch-all from
decision 12, **last**.

## Work items

### W1 — accounts: the `ApiToken` model, `tokens.py`, admin, two commands
Test, in `accounts/tests.py`: issuing returns a `cm_` key whose hash is stored
and whose text is not in any column. Reissuing replaces the old token, so the
old key's `user_for_key` is `None`. Revoking removes it. An inactive user's key
resolves to `None`. Both commands work by email, case-insensitively, and raise
`CommandError` for an unknown email.

### W2 — authentication, throttling and settings
`accounts/authentication.py`, `api/authentication.py`, `api/throttling.py`, the
settings. Tests in `api/tests.py`, under a new `class TestApiTokens` or a
`test_api_tokens` section:
- `GET /api/riders/` with `Authorization: Bearer <key>` returns 200 with the
  caller's roster.
- A `PUT` squad or `POST /api/staff/training/` with a token and **no CSRF token**
  succeeds (*load-bearing*: proves decision 6).
- A missing token, a garbage token, a revoked token and an old key after
  reissue each return a 403 with a JSON `detail`.
- An anonymous request still returns a 403 (regression).
- A token request stamps `last_seen_at` with the mock clock's time. A second
  request within the hour does not write: assert with
  `django_assert_num_queries` or by comparing the stamp after moving the clock
  thirty minutes. A request an hour later does stamp.
- The 61st token request in a minute returns a 429 with `Retry-After`, and
  session requests are never throttled. Add an autouse fixture,
  `cache.clear()`, so throttle state does not leak between tests.
- Integration with `world`: a token-only user who goes inactive for ten weeks
  is released by `tick`, and one still active is not. Drive it with
  `MockClock`, following the existing inactivity tests in `world/tests`.

### W3 — the schema, docs page and JSON 404
Add drf-spectacular, `api/schema.py`, the URLs and the catch-all. Tests:
`/api/schema/` and `/api/docs/` return 403 anonymously and 200 with a token or a
session. `/api/nope/` and `/api/riders` (no slash) return a 404 JSON. A non-API
path still gets the SPA.

### W4 — descriptions on every endpoint
Apply `@extend_schema` across `api/views.py` and `accounts/views.py`, plus
`inline_serializer`s where responses are dicts. Do it in one commit per group
if that's easier to review: world and schedule; racing; riders and transfers;
staff and development squad; economy; accounts and teams. Use `api/README.md`'s
*What exists* as the source for what each endpoint does. Tests: the
description-completeness test and the `spectacular --validate --fail-on-warn`
test from decision 11.

### W5 — documentation and archive
READMEs (below). Set both files' status to `implemented` and move them to
`specs/archive/`. Update the AGENTS.md table rows for `accounts/` and `api/`.

## Execution order

W1 → W2 → W3 → W4 → W5. W2 depends on W1's model. W3 before W4, so the
completeness test exists and fails, then goes green as W4 fills in the
descriptions. Commit after each item with the full suite green.

## Documentation update (required, not optional)

- `accounts/README.md`, new section *API tokens*: the model, the hashing and
  why not `authtoken`, the commands, and why `accounts/authentication.py`
  doesn't stamp last-seen. Also update the line "Tokens/JWT were not used" so it
  no longer contradicts this.
- `api/README.md`, *Authentication*: the two authenticators and their order
  (decision 6), `Bearer`, throttling and its per-process caveat, and last-seen
  on token use. A new section, *Schema and docs*: where they are, the rule that
  every new view needs `@extend_schema` with a game-terms description, and the
  test that enforces it. A new section, *Browser assumptions (audit)*:
  `MeView`'s CSRF cookie (harmless for tokens), register and login creating a
  session (harmless, ignore the cookie), logout not revoking a token, the race
  log's `Accept-Encoding` negotiation (send `br` or get plain NDJSON), and the
  SPA catch-all that used to answer `/api/` typos with HTML, now fixed.
- `world/README.md`: one line where inactivity is described, saying token use
  stamps last-seen, so token-only agents are no longer exempt.
- AGENTS.md: the table rows for `accounts/` and `api/`. Add `issue_api_token`
  to *Seeding a world for testing*, so a reviewer can try it.

## Verification

1. `.venv/bin/python -m pytest` stays green, with coverage at 85% or above.
2. By hand: `seed_user`, then `issue_api_token test@mail.com`, then
   `curl -H "Authorization: Bearer $KEY" localhost:<port>/api/riders/` returns
   JSON. `curl -X POST … /api/staff/training/ -d '{"focus": …}'`, with a token
   and no cookie, succeeds. `/api/schema/` with the token returns YAML that
   includes `bearerAuth`. `/api/docs/` in a logged-in browser renders.
3. **The likeliest failure** is CSRF still biting token writes, because a cookie
   jar sent a session along. Reproduce it with curl and no cookies. The W2
   no-CSRF test uses `APIClient(enforce_csrf_checks=True)`. Without that flag
   the test client skips CSRF and the test could never fail.

## Risks

| Risk | Mitigation |
|---|---|
| A test client that skips CSRF makes the no-CSRF test meaningless | Use `APIClient(enforce_csrf_checks=True)` in that test (W2) |
| Throttle counts leak across tests through `LocMemCache` | An autouse `cache.clear()` fixture in `api/tests.py` (W2) |
| With N workers the real limit is 60 × N | Accepted for the beta. Documented in `api/README.md`. A shared cache can come with the deploy work if it matters |
| Putting the token class first silently changes every anonymous 403 to a 401 | Decision 6. The anonymous regression test |
| Descriptions drift as endpoints are added | The completeness test (decision 11) fails the build |
| `--fail-on-warn` trips on views with no `serializer_class` | Every view method gets an explicit `@extend_schema(request=…, responses=…)`. That is the bulk of W4 |
| The race log endpoint returns bytes, not JSON | `responses={(200, "application/x-ndjson"): OpenApiTypes.BINARY}` with a description of the encoding |

## Open questions

None.
