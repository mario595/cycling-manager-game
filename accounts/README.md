# Accounts — player identity

## What this app owns

`accounts.User` — the custom user model, swapped in as `AUTH_USER_MODEL`
before the first migration since doing that later is painful in Django —
and the three endpoints that make it reachable: register, log in, log out.
Not team ownership (`teams.Team.manager` owns that relationship — see
*What `accounts/` may import*, below) and not anything about *what* a new
account gets (an unmanaged team to claim, a starting roster) — that is
`specs/claiming-a-team.md` / #46.

## Email as the login identifier

Login is by email, not username. `User` still subclasses `AbstractUser` and
still has a `username` column — dropping it would mean rewriting onto
`AbstractBaseUser`, more than this needed — but nothing asks a player for
one. `UserManager.create_user` derives it from the email's local part
(`slugify`d, deduplicated with a numeric suffix on collision) so the column
stays populated and unique without a form field for it.

`USERNAME_FIELD = "email"` and `REQUIRED_FIELDS = []` on the model. One
consequence worth knowing: **`createsuperuser` now prompts for an email
address, not a username.** That is expected, not a bug.

`email` is unique, case-sensitively, because Postgres unique constraints are
case-sensitive and Django's own `normalize_email` only lowercases the
domain half (RFC 5321 treats the local part as case-sensitive). Comparing
`email__iexact` at registration is what actually stops `Mario@x.com` and
`mario@x.com` from being two accounts — the database constraint alone
would not catch it.

## What `accounts/` may import

Nothing — `AGENTS.md` puts this app at the root of the dependency graph,
and that still holds after this feature. `RegisterView`, `LoginView` and
`LogoutView` only ever touch `accounts.models`/`accounts.serializers`; they
have no idea whether the user they just logged in manages a team.

That is why **`GET /api/accounts/me/` lives in `api/`, not here** — it is
the one place allowed to import both `accounts` and `teams`, and answering
"does this user have a team" needs both. Register and login mirror this:
they confirm only the display name in their own response, and the SPA
follows up with a `me` fetch for the team (see `api/README.md`,
*Authentication*, and `frontend/README.md`).

## Session authentication, hand-rolled

`django.contrib.auth` plus DRF's `SessionAuthentication` — both already
configured project-wide before this feature existed — are all this uses.
No new runtime dependency.

A hosted provider (Clerk, Auth0) was considered and rejected: it would make
`accounts.User` a webhook-synced mirror of an external record, putting a
network boundary and an eventual-consistency gap directly under
`teams.Team.manager` — the exact relationship a squad request's
authorisation depends on (see `api/README.md`). It also bills per active
user, against a stated frugality constraint, and its headline features
(password reset, email verification, MFA) are precisely what `specs/
player-accounts.md` deferred to #51.

`django-allauth` / `dj-rest-auth` were also passed over — free, but far
wider in scope (URL trees, templates, settings surface) than three
endpoints need. **The one case where hand-rolling would start to hurt is
social login** (Google, Discord); if that becomes a real requirement,
`django-allauth` is the thing to reach for then, not before.

Tokens/JWT were not used either: the SPA is served same-origin by Django,
so there is no cross-domain problem for a token to solve, and inventing
refresh/revocation would buy nothing.

## Login failures are vague; registration failures are not

A wrong password and an unknown email both return the same "email or
password is wrong" — the view does not branch on which case it was, so
there is nothing to leak about whether an email is registered. Registering
with an email already in use says so plainly instead: the collision cannot
be hidden and still be usable, so the asymmetry is deliberate, not an
oversight.

## Not here

Password reset, change password, change email, delete account — split into
#51 from the start. A player who can register and log in can play; losing
a password today is a dead end (a new account), not a missing feature this
app forgot.
