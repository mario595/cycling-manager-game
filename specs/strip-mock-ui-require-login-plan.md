# Strip the mock UI and require login — Implementation Plan

**Spec:** `specs/strip-mock-ui-require-login.md` · **Issue:** #73 · **Status:** in progress
**Apps touched:** `frontend/`, `api/`

## Context you need

The SPA (`frontend/`) is a React + TypeScript app served by Django, built with
Vite. Read `frontend/README.md` first — it is accurate about what exists today,
and several of its stated decisions are **deliberately reversed** by this work
(see D1 and the documentation section). `api/README.md` is likewise accurate and
likewise partly reversed.

What exists today, concretely:

- `frontend/src/navigation.ts` declares `NAV_SECTIONS`: six sections, sixteen
  items, two of which carry a `badge` string. `NAV_ITEMS` flattens it, and
  `App.tsx` generates one route per nav item.
- `frontend/src/App.tsx` maps six paths to real screens via `SCREENS` and sends
  everything else — plus a `path="*"` catch-all — to `screens/Placeholder.tsx`.
- `frontend/src/placeholderData.ts` holds every invented value, including
  `TEAM`, which is still imported by `Sidebar.tsx` (for `TEAM.season` as a clock
  fallback and `TEAM.tier`) and `Layout.tsx`.
- `frontend/src/screens/Dashboard.tsx` renders almost entirely from
  `placeholderData.ts` plus `courseProfile.ts`.
- `frontend/src/useAuth.tsx` fetches `GET /api/accounts/me/` once on mount and
  exposes `{ me, loading, … }`. **`loading` already exists and is already
  correct** — no change needed to make the race condition fixable; the guard
  simply has to respect it.
- `frontend/src/components/Layout.tsx:53` implements the team-less guard via
  `TEAM_LESS_ALLOWED_PATHS`. There is no not-logged-in guard.
- `api/views.py` has four `AllowAny` views: `ClockView`, `PositionView`,
  `CalendarView` and `MeView`.

Data hooks that already exist and return exactly what the new Dashboard needs:
`useSeason` (season + week), `useStandings` (ranked table), `useCalendar`
(twelve weeks of races with `status`), `useAuth` (manager name, team). Each
follows the same shape — `{ data, loading, error }`, polling every 60s. **No new
endpoint and no new hook is required for the Dashboard**, with one exception
noted in D4.

Repo rules this work is bound by: `AGENTS.md`'s dependency direction (untouched
here — `api/` may import everything, and nothing new is imported); tests are
pytest via `.venv/bin/python -m pytest`; styling is inline `style={{}}` with
colours from `src/theme.ts`, never hex literals in components.

## Goal

When this is done:

1. The sidebar has six items, in sections, with no badges, and every one opens a
   built screen.
2. `screens/Placeholder.tsx` and `placeholderData.ts` do not exist, and nothing
   imports them.
3. The Dashboard shows five real things and nothing else, rendering nothing —
   not a skeleton — for any part still loading.
4. No route in the SPA is reachable without a session except `/login` and
   `/register`; a guarded visit returns to its original destination after login.
5. The clock, season position and calendar endpoints require authentication.
6. The frontend has a test runner, and the guards and Dashboard states are
   covered by it.

## Design decisions (settled — implement these, do not substitute)

**D1. The route guard lives in `Layout.tsx`, beside the existing team guard —
not in a new `<RequireAuth>` wrapper component.**

The team-less guard is already there and the two must compose in a defined
order. Putting the session guard in a separate wrapper component means two
files deciding redirects, and the ordering becomes an emergent property of how
they nest rather than something a reader can see. Add the session check
immediately above the existing team check in the same early-return block.

*Do not* create `components/RequireAuth.tsx`. *Do not* move the team guard out.

**D2. `loading` gates both guards, and is checked first.**

```tsx
const { me, loading } = useAuth()

if (loading) return null          // identity not yet established — redirect nothing
if (!me?.authenticated && !ANON_ALLOWED_PATHS.has(pathname)) {
  return <Navigate to="/login" replace state={{ from: pathname }} />
}
if (me?.authenticated && !me.team && !TEAM_LESS_ALLOWED_PATHS.has(pathname)) {
  return <Navigate to="/claim" replace />
}
```

**This ordering is load-bearing.** `useAuth` starts with `me === null, loading
=== true`. Without the `loading` guard first, `!me?.authenticated` is true on
the very first render for *everyone*, including a logged-in manager refreshing
the page — they would be bounced to `/login` before `getMe()` returns. This is
the single failure the spec names as unacceptable (item 14), and it is the
mistake a reader will make if they write the checks in the obvious order.

Note `useAuth`'s `.catch()` sets `loading = false` but leaves `me === null`, so
a failed `getMe()` correctly falls through to the login redirect rather than
hanging.

**D3. The post-login destination travels in router location state, not a query
parameter.**

`<Navigate state={{ from: pathname }} />`, read in `Login.tsx` via
`useLocation()`. A query parameter (`/login?next=/league`) would work, but it
puts a user-controlled path in the URL, and every consumer then has to validate
it is a relative path before navigating — an open-redirect shape for no benefit.
Location state is in-memory, cannot be typed by hand, and needs no validation.

The consequence, which is correct: someone who navigates *directly* to `/login`
has no `from`, and lands on `/` after logging in. Spec item 10 says exactly this.

**D4. The Dashboard's "is the squad set" line uses the existing squad endpoint,
via a new `useNextRaceSquad` hook — but only when there is a next race.**

`GET /api/racing/races/<id>/squad/` already returns a `saved: boolean` that
means precisely "this team chose a squad, rather than it being auto-picked".
That is the flag the spec's nudge depends on, and no new endpoint is needed.

The hook takes `raceId: number | null` and fetches nothing when null, because
the next race is derived from the calendar and is not known on first render.
*Do not* extend the calendar endpoint to carry squad status — that would make a
per-team fact part of a world-data payload, and the calendar is consumed by a
screen that does not need it.

**D5. "Next race" is computed on the client from the calendar already being
fetched.**

The first race, scanning weeks in order and races within a week by `starts_at`,
whose `status` is not `finished` and not `failed`. No new endpoint. Put it in
`frontend/src/nextRace.ts` as a pure function so it is testable without
rendering anything:

```ts
export function nextRace(calendar: Calendar | null): CalendarRace | null
```

`status` is one of `scheduled | running | finished | failed`. A `running` race
is still "next" — it is the one the manager cares about. `failed` is skipped
because it will never produce a result.

**D6. Every `AllowAny` comes off except `MeView`'s.**

`MeView` must stay public: it is how the SPA learns *that nobody is logged in*,
and the guard depends on that answer. Making it `IsAuthenticated` would 403 the
one request that tells the app to show the login screen, and the app would never
boot for a visitor. Its `@ensure_csrf_cookie` is also load-bearing for writes.

The three that change — `ClockView`, `PositionView`, `CalendarView` — simply
drop their `permission_classes` line and fall back to the project default
(`IsAuthenticated` in `config/settings/base.py`). Their docstrings currently
argue for being public and must be rewritten, not just edited around.

`accounts/views.py`'s three `AllowAny` views (`RegisterView`, `LoginView`,
`LogoutView`) are untouched and must stay public — you cannot log in if the
login endpoint requires being logged in.

**D7. The sidebar keeps `NAV_SECTIONS` and loses the `badge` field from the
`NavItem` type entirely.**

Not "set to undefined" — removed from the interface, so the rendering branch in
`Sidebar.tsx:166–183` is deleted and a future badge is a deliberate re-addition
rather than filling in a blank that was left waiting.

**D8. `TEAM.tier` goes with the rest of `placeholderData.ts`; the sidebar shows
nothing in its place.**

`Sidebar.tsx:99` renders `TEAM.tier` ("CONTINENTAL · DIV 2") for a manager with
a team and `'SPECTATING'` otherwise. There is one Division and no tier concept,
so the tier is invented. Remove the element. `'SPECTATING'` also goes — with the
guard in place, nobody without a team reaches the sidebar at all.

**D9. `TEAM.season` as the clock's loading fallback goes; the clock renders
nothing while loading.**

`Sidebar.tsx:44` falls back to `TEAM.season` ("SEASON 3 · WK 14") when the clock
has not arrived. That is a fabricated season number shown as fact — exactly what
this ticket removes — and `frontend/README.md` already flags it as the one
surviving fake. Render an empty string instead, consistent with the discipline
`useCalendar`/`useRoster` already follow.

**D10. Vitest + React Testing Library + jsdom, as dev dependencies only.**

Chosen over Jest because the project already builds with Vite and Vitest reuses
`vite.config.ts` — no second transform pipeline, no Babel config. Three dev
dependencies (`vitest`, `@testing-library/react`, `jsdom`) plus
`@testing-library/jest-dom` for matchers. No runtime dependency is added, and
`npm run build` is unchanged.

Tests live beside the code as `*.test.ts`/`*.test.tsx`, matching the flat
`src/` layout rather than introducing a `__tests__/` tree.

## Data model

No model, field or migration changes. This feature is a frontend change plus
three permission-class removals.

## `api/views.py`

Three edits, each removing one line and rewriting a docstring.

```python
class ClockView(APIView):
    """The game's current time. Requires a session: the game exposes nothing
    to a visitor who is not logged in — see api/README.md, *Authentication*."""

    def get(self, request):
        ...
```

Same shape for `PositionView` and `CalendarView`. Remove the now-unused
`AllowAny` import **only if** no view in the file still uses it — `MeView` does,
so the import stays. Verify with `grep -n AllowAny api/views.py` after editing;
it must show the import and `MeView` only.

## `frontend/src/navigation.ts`

Remove the `badge` field from `NavItem`. Reduce `NAV_SECTIONS` to:

| Section | Items |
|---|---|
| HOME | Dashboard `/` |
| TEAM | Roster `/roster`, Staff `/staff` |
| RACING | Calendar `/calendar`, Results `/results` |
| COMPETITION | League table `/league` |

MARKET and CLUB disappear entirely (every item removed). `NAV_ITEMS` and
`titleForPath` are unchanged in shape.

## `frontend/src/App.tsx`

Delete the `Placeholder` import and both its uses. `SCREENS` now covers every
nav item, so the `?? Placeholder` fallback becomes a plain lookup — but keep the
map rather than hand-writing six `<Route>`s, since `navigation.ts` is still the
single source of truth.

Replace the catch-all:

```tsx
<Route path="*" element={<Navigate to="/" replace />} />
```

It stays **inside** the `<Route element={<Layout />}>` block, so an unknown path
still passes through the guards — a logged-out visitor typing `/transfers` must
reach `/login`, not `/`. Putting it outside Layout would bypass the guard and
send them to a dashboard they cannot see.

## `frontend/src/components/Layout.tsx`

Add `ANON_ALLOWED_PATHS` beside the existing `TEAM_LESS_ALLOWED_PATHS`:

```tsx
/** The only routes a visitor with no session may reach. Registration must be
 * here or a new player could never get an account. */
const ANON_ALLOWED_PATHS = new Set(['/login', '/register'])
```

Insert the guard block from D2. Remove the `TEAM` import; `teamName` already
reads from `me` and needs no fallback.

## `frontend/src/components/Sidebar.tsx`

- Remove the `TEAM` import and both its uses (D8, D9).
- Delete the badge branch (D7).
- `dateLabel` becomes `now && !error ? formatGameDate(now) : ''`.

## `frontend/src/screens/Login.tsx`

Read the intended destination and use it on the existing authenticated redirect:

```tsx
const location = useLocation()
const from = (location.state as { from?: string } | null)?.from

if (me?.authenticated) {
  return <Navigate to={me.team ? (from ?? '/') : '/claim'} replace />
}
```

A manager with no team still goes to `/claim` regardless of `from` — the team
guard would bounce them there anyway, and skipping the extra hop is clearer.

`Register.tsx` is unchanged: a newly registered user has no team, so `from` can
never apply to them.

`ClaimTeam.tsx` is **already correct** — `ClaimTeam.tsx:17-18` already redirects
an anonymous visitor to `/login` and a manager who has a team to `/`. Spec item
12 needs no code change. Confirm it, and cover it with a test rather than
rewriting it.

## `frontend/src/screens/Dashboard.tsx`

Rewritten from scratch. It composes `useAuth`, `useSeason`, `useStandings`,
`useCalendar` and the new `useNextRaceSquad`, and renders:

- **Heading** — eyebrow: season label from `seasonLabel(position)`; title:
  `Good morning, {me.display_name}.`; subtitle: the team name.
- **Standings row** — the manager's own rank and points, found by matching
  `entry.team.id` against `me.team.id`. When the team is not in the table yet, or
  the season has not started, show nothing rather than a zero-filled row.
- **Next race card** — name, `starts_at` formatted, and one of two lines: "Squad
  set" or "No squad chosen — one will be picked for you", linking to
  `/race/{id}`. When `nextRace()` returns null, the card says the season has no
  races left.

Each block renders `null` while its own hook is loading — independently, so a
slow standings fetch does not blank the whole page. **Do not** add a single
combined `if (loading) return null` over the whole screen: the spec asks for
per-piece absence, and one combined gate means the fastest fetch waits for the
slowest.

Delete `ActionCards`, `LastNightsRaces`, `DivisionTable`, `FormWatch`, `Inbox`
and the course-profile SVG entirely.

## `frontend/src/nextRace.ts` (new)

Pure function per D5. No React import.

## `frontend/src/useNextRaceSquad.ts` (new)

```ts
export function useNextRaceSquad(raceId: number | null): {
  saved: boolean | null
  loading: boolean
}
```

Fetches `getSquad(raceId)` when `raceId` is non-null; resets to
`{ saved: null, loading: false }` when null. Unlike the other hooks it does not
poll — squad status changes only when the manager changes it, and they change it
on another screen and come back, which remounts this. A 403 (no team) or any
error yields `saved: null`, which the Dashboard renders as nothing.

## Files deleted

- `frontend/src/screens/Placeholder.tsx`
- `frontend/src/placeholderData.ts`
- `frontend/src/courseProfile.ts`

After deleting, `grep -rn "placeholderData\|courseProfile\|Placeholder" frontend/src`
must return nothing. `theme.ts`'s `inboxTag` and `formColor` become unused —
remove them too, and check `grep -rn "inboxTag\|formColor" frontend/src` is
empty.

## Work items

### W1 — `frontend/`: add the test runner — **done**

Add `vitest`, `@testing-library/react`, `@testing-library/jest-dom` and `jsdom`
to `devDependencies`; add `"test": "vitest run"` to scripts; add a `test` block
to `vite.config.ts` (`environment: 'jsdom'`, `globals: true`, a setup file
importing `@testing-library/jest-dom`).

**Test:** `frontend/src/nextRace.test.ts` — a trivial case proving the runner
executes. Lands first so every later item has somewhere to put its tests.

### W2 — `frontend/src/nextRace.ts`: derive the next race — **done**

New pure module per D5.

**Test:** `frontend/src/nextRace.test.ts` — `returns the first scheduled race`,
`skips finished races`, `treats a running race as next`, `skips failed races`,
`returns null when every race has finished`, `returns null for a null calendar`,
`orders races within a week by starts_at`.

### W3 — `api/views.py`: close the three public endpoints — **done**

Remove `permission_classes = [AllowAny]` from `ClockView`, `PositionView` and
`CalendarView`; rewrite their docstrings per D6.

**Load-bearing:** `MeView` keeps `AllowAny`. A reader tidying "all the AllowAny
in this file" breaks the app's ability to boot for a visitor.

**Test:** `api/tests.py` — replace `test_calendar_is_public` with
`test_calendar_requires_login`; add `test_clock_requires_login` and
`test_position_requires_login`, each asserting 403 for `APIClient()` and 200 for
a logged-in client. Keep `test_me_reports_anonymous_for_a_visitor` passing
unchanged — it is the regression test for D6's exception.

### W4 — `frontend/src/components/Layout.tsx`: the session guard — **done**

Add `ANON_ALLOWED_PATHS` and the D2 guard block. Remove the `TEAM` import.

**Load-bearing:** the `loading` early return comes first. See D2.

**Test:** `frontend/src/components/Layout.test.tsx` — `renders nothing while
auth is loading`, `redirects an anonymous visitor to /login`, `does not redirect
an anonymous visitor already on /login`, `allows /register anonymously`,
`redirects a team-less manager to /claim`, `does not bounce a logged-in manager
mid-load` (the race condition: render with `loading: true, me: null` and assert
no navigation occurred), `passes the attempted path in location state`.

### W5 — `frontend/src/screens/Login.tsx`: return to the attempted page — **done**

Read `location.state.from` per D3.

**Test:** `frontend/src/screens/Login.test.tsx` — `sends an authenticated
manager to the page they attempted`, `sends them to / when there is no attempted
page`, `sends a team-less manager to /claim even with an attempted page`.

### W6 — `frontend/src/navigation.ts` + `Sidebar.tsx`: six items, no badges — **done**

Reduce `NAV_SECTIONS` per the table; drop `badge` from `NavItem`; delete the
badge rendering; remove `TEAM.tier` and the `TEAM.season` fallback per D8/D9.

**Test:** `frontend/src/navigation.test.ts` — `every nav item has a screen`
(asserting each `NAV_ITEMS` path is a key of a fixture list of built routes),
`no section is empty`, `no item declares a badge`.

### W7 — `frontend/src/App.tsx`: delete Placeholder, redirect unknown paths — **done**

Remove the import and both uses; add the catch-all `<Navigate to="/" replace />`
**inside** the Layout route. Delete `screens/Placeholder.tsx`.

**Test:** `frontend/src/App.test.tsx` — `an unknown path sends a logged-in
manager to the dashboard`, `an unknown path sends an anonymous visitor to
/login` (proving the catch-all is inside the guard, per the App.tsx section).

### W8 — `frontend/src/useNextRaceSquad.ts`: squad status for the next race — **done**

New hook per D4.

**Test:** `frontend/src/useNextRaceSquad.test.ts` — `fetches nothing when raceId
is null`, `reports saved`, `reports not saved`, `reports null on a failed
request`.

### W9 — `frontend/src/screens/Dashboard.tsx`: rebuild from real data — **done**

Rewrite per the Dashboard section. Delete `placeholderData.ts`,
`courseProfile.ts`, and `theme.ts`'s `inboxTag`/`formColor`.

**Test:** `frontend/src/screens/Dashboard.test.tsx` — `greets the logged-in
manager by name`, `shows the team name`, `shows the season and week`, `shows the
team's own rank and points`, `shows nothing for standings when the team is not
ranked`, `shows the next race with its name`, `says the squad is set when it
is`, `nudges when no squad is chosen`, `says the season has no races left when
none remain`, `renders no standings block while standings are loading`, `renders
the rest of the page while one block is still loading`.

**Load-bearing:** the last case. It is what proves the per-block loading
discipline from the Dashboard section rather than a single combined gate.

### W10 — documentation

Per the next section. Lands last so it describes what was actually built.

## Execution order

W1 → W2 → W3 → W4 → W5 → W6 → W7 → W8 → W9 → W10.

- **W1 first** because every other frontend item names a test file, and they
  need a runner to live in.
- **W2 before W9** — the Dashboard consumes `nextRace()`, and proving the
  derivation against a pure function is far cheaper than proving it through a
  rendered component.
- **W3 early and alone.** It is the only backend change, it is three lines, and
  it is independently verifiable with pytest. Landing it before the frontend
  guard means the SPA is briefly stricter on the server than the client, which
  is the safe direction: a screen 403s rather than a visitor seeing data.
- **W4 before W5** — the guard has to be setting `location.state.from` before
  the login screen can read it.
- **W6 and W7 are separable but adjacent**; W6 first, so that when W7 removes the
  `?? Placeholder` fallback there is already no nav item that needs it. Doing W7
  first leaves a window where `/transfers` is a nav item pointing at a deleted
  component.
- **W9 late** because it is the largest single item and it depends on W2 and W8.

Commit at the end of each work item; the suite must be green at every one.

## Documentation update (required, not optional)

**`frontend/README.md`** — substantial revision, not an append:

- *What exists* table: remove the `Placeholder` row and the ten unbuilt routes;
  note that an unknown path redirects to `/`.
- Delete the paragraph beginning "Every sidebar item routes somewhere real…"
  through "…hides whether routing worked at all." **That passage argues for the
  placeholder and against the redirect this ticket implements.** Replace it with
  the current rule: every nav item has a screen, and an unknown path goes home.
- *Identity*: document both guards, their order, and that `loading` gates them —
  naming the refresh race as the reason, so nobody "simplifies" it away.
- *Where the data comes from*: `placeholderData.ts` is gone. Say so, and that no
  screen renders an invented value. Remove the `TEAM` paragraph.
- New short section on testing: the runner, `npm --prefix frontend test`, and
  where tests live.

**`api/README.md`** — *Authentication* section:

- The paragraph beginning "Three endpoints override it with `AllowAny`, **by
  design, not as a placeholder**…" is now wrong in its conclusion. Rewrite: the
  game exposes nothing to an anonymous visitor; the clock, position and calendar
  now require a session.
- State that `MeView` remains `AllowAny` and **why** — it is the endpoint that
  answers "nobody is logged in", and the SPA cannot boot without it.
- Record the reversal explicitly, per the spec's *Closing the public endpoints
  is a deliberate reversal*, so a future landing page reopens it knowingly
  rather than assuming an oversight.

**`AGENTS.md`** — the `frontend/` row currently reads "Dashboard and Roster
render from the mockup; everything else is a placeholder route. No DB yet."
All three clauses become false. Update to reflect six real screens and no
fixture data.

## Verification

```bash
.venv/bin/python -m pytest
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run lint
```

The build is not optional: deleting `placeholderData.ts` breaks any import that
was missed, and `tsc -b` is what catches it. `grep -rn
"placeholderData\|courseProfile\|Placeholder\|inboxTag\|formColor" frontend/src`
must be empty.

Then run it for real — `npm --prefix frontend run build && .venv/bin/python
manage.py runserver` — and walk these, which unit tests cannot prove:

1. **Logged out, visit `/league` directly.** Expect the login screen. Log in.
   Expect to land on `/league`, not `/`.
2. **Logged in, hard-refresh a deep link** (`/roster`, Cmd-Shift-R). Expect the
   roster. **Expect never to see the login screen flash.**
3. **Throttle the network to Slow 3G and repeat (2).** This is the check that
   catches the named risk — the race condition is invisible on localhost because
   `getMe()` returns in single-digit milliseconds. A blank page that becomes the
   roster is correct; a login screen that becomes the roster is the bug.
4. **Log out.** Expect the login screen, not a guarded page bouncing.
5. **Visit `/transfers`.** Logged in: the dashboard. Logged out: the login
   screen.
6. **A newly registered manager** goes to `/claim` and can reach nothing else;
   after claiming, `/claim` sends them to `/`.
7. **Dashboard content**: every value on it should be traceable to something you
   can verify elsewhere in the app — the name you registered with, the team you
   claimed, the week the calendar shows, your row in the league table.

Evidence that proves nothing: a passing `Layout.test.tsx` that renders with
`loading: false` only. The race-condition case must assert on the
`loading: true, me: null` state specifically, or it cannot fail for the right
reason.

## Risks

| Risk | Mitigation |
|---|---|
| The guard bounces a logged-in manager to `/login` on refresh, because the `loading` check was written after the `authenticated` check. | D2 fixes the order and marks it load-bearing; W4 tests the `loading: true, me: null` state directly; verification step 3 throttles the network, which is the only way to see it by hand. |
| A reader removes `MeView`'s `AllowAny` while "finishing the job" in W3. | D6 and the W3 note both call it out; `test_me_reports_anonymous_for_a_visitor` fails immediately if it happens. |
| The catch-all route is placed outside `<Layout />`, so unknown paths bypass the guard and leak the dashboard shell to a logged-out visitor. | The App.tsx section states the placement and the reason; W7's second test case asserts an anonymous visitor hitting an unknown path reaches `/login`. |
| Deleting `placeholderData.ts` leaves a dangling import that only shows at build time. | `npm run build` runs `tsc -b`; it is listed in Verification as non-optional, plus the grep. |
| The Dashboard gets a single combined loading gate, so the whole screen blanks until the slowest of four fetches returns. | The Dashboard section forbids it explicitly; W9's final test case asserts the page renders while one block is still loading. |
| Vitest setup drifts from the Vite build config and tests pass against a different transform than production. | Vitest reads `vite.config.ts` directly (D10) — the `test` block is added to that same file, not a separate `vitest.config.ts`. |

## Open questions

None.
