# Frontend

The React SPA, served by Django from `frontend/dist/`: nine built screens,
all reading the real API. No screen renders invented data.

## What exists

| Route | Screen | State |
|-------|--------|-------|
| `/` | Dashboard | Built — season, standings, next race and squad status, and a "My auctions" section listing riders the team is selling and auctions it has bid on — the same `AuctionCard` the Transfers screen uses, so a Dashboard listing can be bid on directly — from the API, no fixture data |
| `/roster` | Roster | Built — filter, sort, rider detail panel, each rider's weekly salary, market value and release cost, a squad-value total, the same freshness bar as squad selection, the season-end salary review panel with the wage bill and each moved rider's old→new salary, and a "List for auction" action beside Release, from the API, no fixture data |
| `/staff` | Staff | Built — hire/fire a trainer, with each trainer's fee and weekly salary, from the API, no fixture data |
| `/development-squad` | DevelopmentSquad | Built — the three levels as cards, each with its weekly cost and per-season cost, and one action worded by state: **Open** on the entry level while closed, **Upgrade** on the rung above the level held, a **Current** badge on the level held, and everything else a **padlock** and no button, plus a **Close squad** button while one is open. From the API, no fixture data. The screen derives **no** ladder of its own: the server sends each level's `action` and `requires` and the client only decides the wording, which is the only way a padlock and a 409 can be kept from disagreeing. A locked card explains itself — "Upgrade to National first" for a rung not yet reached, "Climbed past. Close the squad to start over." for one already passed, since with no downgrade the way back is to close. An action costing more than the balance is disabled with a reason, as `Staff.tsx` does for an unaffordable trainer; a locked card is never reported as unaffordable, because a lock is not a price. The fee row is labelled by the rung it buys — "Open fee" on level 1, "Upgrade fee" above — and closing's confirmation states that costs stop for good and a reopened squad starts at Regional, because that is the only way left to spend less and a manager picks it under pressure. **The subtitle says what is charged and nothing more** — no youth riders, no "coming soon", because #33 owns intake and what a higher level does to it is not decided yet. `DevelopmentSquad.test.tsx` pins that for both the closed and open states. |
| `/sponsors` | Sponsors | Built — sign one of three sponsor offers, or see the signed contract, from the API, no fixture data |
| `/finances` | Finances | Built — balance, weekly wage bill and ledger history from the API, no fixture data |
| `/training` | Training | Built — set the weekly focus, see last week's moves, from the API, no fixture data |
| `/calendar` | Calendar | Built — twelve weeks from the API, no fixture data |
| `/transfers` | Transfers | Built — two tabs: the free-agent pool with each rider's signing fee and sign action, and live auctions with current price, minimum next bid, a live `dd hh mm ss` countdown to the deadline, a bid action and each auction's full bid history (bidding is not anonymous — collapsed by default, expandable), plus an outbid notice and the team's balance, from the API, no fixture data |
| `/race/:raceId` | Race | Built — the full race screen: course profile (with any declared markers overlaid and listed — a sprint marker's list entry also shows its weight and what winning it pays) and squad before it runs; after it, the same course profile, a **Watch race** button when the race has a replay (a muted note when it does not), and the results behind a **Show results** toggle, so opening a race never fetches the results. The results' marker card shows points beside each scoring crossing, and a team's points row splits into finish and sprint points when it scored any. From the API, no fixture data |
| `/race/:raceId/replay` | Replay | Built — a finished race's tick-by-tick replay: the game's own playback bar (step, play/pause, ×1–×50, seek, elapsed clock and wind read-out), the shared elevation profile with the player's own riders ringed, the field as it stood at the displayed tick (packs, gaps, leader, PULL/ATK, riders cut by the time limit under "Out of the race") and the same results toggle, all from the API, no fixture data |
| `/riders/:riderId` | RiderProfile | Built — one rider's full profile: identity, freshness, salary and value, the five-axis radar and the attribute-history chart, a career strip and race history, from the API, no fixture data. The affiliation segment is the current team, `Retired · Season S, Week W`, or `Free agent`. |
| `/league` | League | Built — season standings table from the API, no fixture data |
| `/login`, `/register` | Login, Register | Built — real accounts, no fixture data |
| `/claim` | ClaimTeam | Built — real claim, no fixture data |
| anything else | — | Redirects to `/` |

`/race/:raceId` is the first **parameterised** route, so it is registered as
an explicit `<Route>` in `App.tsx` rather than through `SCREENS` — that map
generates one route per nav item by path, which has nowhere to put a
`:raceId`. It is reached by clicking a race on the calendar or the next-race
card on the dashboard. `/race/:raceId/replay` is registered next to it, for
the same reason, and is reached only by that screen's **Watch race** button.
`/riders/:riderId` is the same shape, reached from the
Roster panel's "Full profile" link, a race result row, or a free-agent card
— never a nav item, so it never appears in the sidebar either.
`navigation.ts` owns all three link builders — `riderPath(id)`,
`racePath(id)` and `replayPath(id)` — and each is the **one** way its
callers build the link; nothing constructs `/riders/${id}`,
`/race/${id}` or `/race/${id}/replay` by hand. `titleForPath` names the two
race screens (`Race` and `Replay`) in the mobile top bar. `/login` and
`/register` are explicit routes for the same reason: neither is a nav item,
so neither belongs in the sidebar.

## Identity

`useAuth.tsx`'s `AuthProvider` learns who is logged in **once**, on mount,
via `GET /api/accounts/me/`, and shares it through `useAuth()` — the
sidebar, the race screen, the roster screen, and the login/register screens
all read the same `me` rather than each fetching it themselves. This is
also what makes a session survive a page reload: the browser still holds
the session cookie, so `getMe()` on the next mount re-learns the same
identity without the player logging in again.

`me.team` is what used to be the `?team=<id>` URL parameter described in an
earlier version of this file. That parameter is gone — squad selection and
the roster both derive the team from the session on the server
(`api/README.md`), so neither `Race.tsx` nor `Roster.tsx` needs to pass
one.

**An unknown visitor and a team-less manager are both bounced out of the
app chrome by `Layout.tsx`.** Two guards compose there, in a fixed order,
and `loading` gates both:

```tsx
if (loading) return null          // identity not yet established — redirect nothing
if (!me?.authenticated && !ANON_ALLOWED_PATHS.has(pathname)) {
  return <Navigate to="/login" replace state={{ from: pathname }} />
}
if (me?.authenticated && !me.team && !TEAM_LESS_ALLOWED_PATHS.has(pathname)) {
  return <Navigate to="/claim" replace />
}
```

Order is load-bearing. `useAuth` starts with `me === null, loading === true`,
so on the very first render of a hard page refresh `!me?.authenticated` is
true for *everyone*, including a logged-in manager. Without the `loading`
check first, a refresh would bounce a logged-in manager to `/login` before
`getMe()` returns. A failed `getMe()` leaves `me === null` after loading
settles, which correctly falls through to the login redirect.

`ANON_ALLOWED_PATHS` (`/login`, `/register`) is the escape hatch for
visitors, and `TEAM_LESS_ALLOWED_PATHS` (`/login`, `/register`, `/claim`)
for managers with no team — `/claim` must stay reachable or its own
redirect bounces back to itself. See `teams/README.md`, *Claiming a team*.
The guard passes the attempted path to the login screen in router location
state (`state: { from: pathname }`), and `Login.tsx` reads it, so login
returns the manager where they were headed; someone who visits `/login`
directly has no `from` and lands on `/`.

**The lost-team message (#62)** rides the same redirect: an ex-manager whose
team was released has no team either, so the guard above sends them to
`/claim` exactly like a fresh signup — no separate route or screen was
added for this. `ClaimTeam.tsx` reads `me.lost_team` and, when set, shows a
notice above the claim form naming the team and the reason, then calls
`acknowledgeSpell` once (guarded by a ref, so React 18 StrictMode's
double-invoke in development cannot fire it twice) so `me.lost_team` is
`null` on the next fetch. See `teams/README.md`, *Managerial spells*, and
`api/README.md` for the endpoint.

**Writes need a CSRF token.** DRF's `SessionAuthentication` enforces CSRF
for authenticated sessions, so any `POST`/`PUT` issued while logged in must
carry `X-CSRFToken`, or it 403s — a case nothing hit before login existed,
because every write used to run anonymously. `api.ts`'s `writeJson` (used by
`register`, `login`, `logout`, `putSquad`, the trainer hire/fire pair and the
three development squad writes) handles this: `ensureCsrfToken`
reads the `csrftoken` cookie, fetching `/api/accounts/me/` first if it isn't
set yet (that endpoint's `@ensure_csrf_cookie` guarantees it will be after).
Anything that issues a write should go through `writeJson`, not a bare
`fetch`.

Every sidebar item routes somewhere real, and an unknown path redirects to
`/` — there is no `Placeholder` screen left to catch one. The redirect is
deliberate: the alternative (trying to render a non-existent screen) is a
blank page that hides whether routing worked at all.

Adding a screen takes three edits: write the component, add its path to
`SCREENS` in `src/App.tsx`, and add it to the right `NAV_SECTIONS` group in
`src/navigation.ts`. The two maps hold different things and neither derives
from the other, and forgetting either fails differently and quietly — a path
in `SCREENS` but not in `NAV_SECTIONS` registers no route at all, so it falls
through to the catch-all and lands on the dashboard, while a nav item with no
`SCREENS` entry renders `undefined` and throws at runtime rather than at
build. `navigation.ts`'s comment is explicit that only built screens go in
the rail: a feature that does not exist yet is not hinted at.

The Development squad screen (#32) is the one where placement was a decision
rather than a formality — it sits after Staff in the TEAM group, beside the
other things a manager sets up once, rather than near Finances, which is
where the resulting cost shows up. It also needed a hook of its own and two
new labels in `Finances.tsx`'s `KIND_LABELS`, the one part of the wiring
that is *not* automatic: an unknown kind falls back to its raw string, so a
forgotten label shows the player `development_squad_fee` verbatim.

## Where the data comes from

`src/placeholderData.ts` is **gone** — it was the mockup's invented values,
and this ticket deleted it along with the last screen that consumed it. No
screen renders an invented value. `Dashboard.tsx` composes the same live
hooks everyone else uses: `useSeason` for the week label, `useStandings` for
the manager's own rank and points, `useCalendar` (via `src/nextRace.ts`) for
the next race, and `useNextRaceSquad` for whether that race's squad is set.

`/calendar`, `/roster` and `/transfers` render nothing while loading or on
error, rather than inventing a shape — `src/useCalendar.ts`,
`src/useRoster.ts`, `src/useFreeAgents.ts` and `src/useAuctions.ts` all
follow the discipline `useSeason.ts` established: a screen showing
invented data mid-fetch is indistinguishable from a real one with a bug
in it. `src/useMyBids.ts` is the one exception — its outbid notice is a
courtesy, not the screen's main content, so it starts from an empty list
and fails silently rather than blocking the page. `src/useDevelopmentSquad.ts`
(#32) follows the same rule for a screen where a stale price would be
actively misleading: it renders nothing while loading, and an error shows one
line saying so rather than three levels at figures the server would not
charge. It also exposes `refresh()`, so the screen re-fetches straight after
an open, change or close instead of waiting up to 60 seconds for the next
poll.

## How it is served

Django serves the SPA rather than a separate host. `config/urls.py` has a
catch-all that renders `index.html` for any path outside `/admin/` and `/api/`,
so client-side routing and browser refreshes both work.

Template resolution order (`TEMPLATES["DIRS"]` in `config/settings/base.py`):

1. `frontend/dist/` — the real Vite build, when it exists.
2. `frontend/templates/` — the committed placeholder, so a fresh clone runs
   before anyone has built the frontend.

`frontend/dist/` is gitignored build output; `frontend/templates/` is source.

### The `/static/` prefix

Django picks `dist/` up **twice**: as a template directory (for `index.html`)
and via `STATICFILES_DIRS` (so WhiteNoise serves `dist/assets/*` under
`/static/`). `vite.config.ts` therefore sets `base: '/static/'` for builds, so
the asset URLs Vite writes into `index.html` match where WhiteNoise actually
serves them. Under `vite dev` there is no Django and no prefix, so `base`
stays `/`. Changing one without the other gives a blank page and 404s on the
JS bundle.

## Running it

Dev server with hot reload, on **5174** (`race_player` owns 5173):

```bash
npm --prefix frontend run dev
```

`/api` and `/admin` proxy to Django on :8000, so this works against the real
backend once endpoints exist.

To check it the way it actually ships — built, served by Django:

```bash
npm --prefix frontend run build && .venv/bin/python manage.py runserver
```

## Conventions

- **Styling is inline `style={{}}`**, matching the design export. No CSS
  framework. `src/index.css` holds only the global reset and the handful of
  hover rules, which inline styles cannot express.
- **Colours come from `src/theme.ts`**, never as literals in components. The
  design repeats its hex codes inline; they are named once there instead.
  `attributeColor` names one colour per engine attribute (climb, sprint,
  flat, resistance, positioning), used by the rider page's radar and
  attribute-history chart — deliberately not `positive`/`negative`, which
  mean good and bad elsewhere and would misapply to an attribute.
- **Money goes through `src/format.ts`'s `formatMoney`**, which thousands-
  separates and prefixes `$` (the sign before the `$`), per `AGENTS.md`,
  *Displaying game money*. It is shared by `Finances.tsx` and `Staff.tsx`
  rather than reimplemented per screen.
- **`src/navigation.ts` is the single source of truth** for the sidebar and
  the router both. A nav item cannot exist without a route, and it owns every
  link builder — `riderPath`, `racePath`, `replayPath` — so no screen
  assembles a path by hand.
- **A screen that is not about the data does not fetch it.** A finished
  race's results sit behind `components/RaceResults.tsx`'s `HiddenResults`,
  which owns its own `useRaceResults` call and does not make it until the
  player clicks **Show results**. The race screen and the replay screen both
  reuse it, so opening either costs one request, not two. The same rule
  gates the replay's own log behind `has_replay`.
- **A rider's status label is a `primitives.tsx` tag, not per-screen
  markup.** `FinalSeasonTag` renders `LAST SEASON` from the API's
  `final_season` boolean
  ([#42](https://github.com/mario595/cycling-manager/issues/42)) and is used
  in three places, all the ones where a manager decides whether to keep
  paying a rider: the roster **card** and the roster **panel** (so it stays
  visible after the rider is opened, where the release button lives), and
  the **free-agent card** on Transfers, where it has to land before the
  Sign button the buyer is about to press. The rider **profile** puts it in
  the page heading's `aside` slot instead — the only header on the site
  with room for it. The API ships the boolean and never the age behind it
  (`api/README.md`), so the tag has nothing to render but the label itself.

## Testing

Vitest + React Testing Library + jsdom, configured in `vite.config.ts`'s
`test` block (jsdom environment, `@testing-library/jest-dom` matchers via
`src/setupTests.ts`). Tests live beside the code as `*.test.ts`/`*.test.tsx`
in the flat `src/` layout. Run them with:

```bash
npm --prefix frontend test
```

The four hooks outside the components are pure or near-pure, which is
deliberate: `src/nextRace.ts` is tested as a function with no rendering,
`src/setupTests.ts` stubs `window.matchMedia`, and screens mock their data
hooks rather than the `api.ts` fetch layer.

**`race_player` has no jsdom**, so anything of its that needs a DOM is tested
from here, importing across the boundary exactly as the app does:
`src/usePlayback.test.ts` (the shared playback hook, with fake timers) and
`src/components/replay/Highlight.test.tsx` (the own-team ring on the shared
profile). The maths stays in `race_player`'s own node-environment suite, and
CI now runs both.

## Relationship to `design/`

`design/Cycling Manager UI.dc.html` is the Claude Design export this was built
from — the reference for spacing, colour and copy. It is a mockup in a custom
template DSL, not runnable source, and it is not a build input. When it is
re-exported, reconcile `src/theme.ts` against it first.

The mockup's **Race day** screen is now **built** as `Race.tsx`, apart from
the deliberate exclusions. It shows the race's name, date, distance and
status, the course elevation profile on every reachable state (before the
race and after it has finished), a **prize list** (`PayoutTable`) — the
`{position, points, prize}` table from the race detail payload, shown only
on the upcoming screen, where the money is not yet visible anywhere else —
the squad-selection widget for the
manager's own team before the race, and — for a finished race — the rider
results and team points tables. Each placed rider carries **their own prize
on their own row** (`RiderResultsTable`), because a team's winnings are the
sum of its placed riders' — two riders from the same team in the points both
show, rather than a team lump sum. The team table carries only points
(no prizes), and a finished race drops the prize list: the winners' rows
already carry the money. Prize amounts
are game money, formatted through `Finances.tsx`'s
`formatMoney`, which `Race.tsx` now imports. The course profile is
**`race_player`'s
elevation chart, reused**: `CourseProfile.tsx` imports `CourseChart`,
`computeProfile` and the `Segment` type directly from `race_player/src/`,
so the SPA's calendar and the visualizer derive and draw a course
identically. That cross-package import resolves `react` from
`race_player/node_modules` unless held to the frontend copy, so
`vite.config.ts` dedupes `react`/`react-dom`; `race_player` remains the
source of the chart and the frontend only bundles it.

**The replay screen** (`/race/:raceId/replay`) is that same arrangement taken
further: `race_player`'s logic and SVG are imported directly —
`parseRaceLog`, `computePacks`, `computeRaceResults`, `packGaps`,
`resultLabel`, `formatDuration`, `usePlayback`/`PLAYBACK_SPEEDS`,
`ElevationProfile`, `RiderMarker`, `PackMarker` and `WindCompass` — while
every piece of chrome is the SPA's own (`components/replay/ReplayControls.tsx`,
`ReplayRiderList.tsx`), because the standalone's chrome is antd and Tailwind
and the SPA has neither. So a module the SPA imports must stay free of both:
`WindCompass` is inline-styled for that reason. The full list of shared
modules is in `race_player/README.md`, *Integration Strategy*.

The replay has **no mockup** in `design/`, and that is deliberate rather than
an omission. It follows the rule the Staff screen set: where a screen has no
mockup, it borrows the composition of the screen it sits next to — here the
race screen's cards, headings and `eyebrow`, with the game's own type and
colours throughout. What remains dropped from the mockup: the eight-rider
squads (the spec fixes four), per-rider course suitability (course-aware
assessment is #45), other teams' entrants on an upcoming race,
wind/temperature/tier/points display facts, and the discrete
`INJURED`/`FATIGUED` rider states
(#41) — freshness is a continuous meter, not a flag. The screen reuses the
mockup's checkbox-row and ★-to-set-leader interaction for the squad part.
Each candidate row additionally shows a `FIT` meter alongside the five
attribute bars — the rider's freshness on the same 0-10 display scale,
clipped apart from the engine attributes so it reads as a status marker
rather than a sixth skill
([#59](https://github.com/mario595/cycling-manager/issues/59); see
`api/README.md`). `Roster.tsx`'s cards draw the same readout — attributes
and freshness through the single `LabelBar` primitive, each with its printed
0-10 value — so a rider reads identically on both screens.

The mockup's **Calendar** screen additionally shows things this feature does
not have — multiple season cards with a switcher, win/podium/points stats, a
"Next up" highlight state, race terrain/class metadata, and result positions
that link through to a race-detail screen. `Calendar.tsx`
matches the mockup's per-season card and week-row structure, but shows one
season only (there is no multi-season history yet) and drops anything that
needs standings or a detail screen that does not exist.

`Staff.tsx` has **no mockup to build from at all** — `design/` was exported
before staff existed as a domain. It follows `Roster.tsx`'s existing
card-and-bar composition (the same `Card`, `Bar`, `barColor` primitives, the
same rider-card layout) rather than inventing a new visual language, so the
screen looks consistent with the rest of the app even without a reference
export. Since #69 each card also shows the trainer's hire fee and weekly
salary (from the API), and the Hire button is **disabled with a visible
reason** when the team's balance cannot cover the fee — the client-side twin
of the API's insufficient-funds 409, so the manager is not offered a hire the
server would refuse.

`Training.tsx` is in the same position — `design/` predates weekly training
as a feature — and follows the same rule, composing `PageHeading`, `Card`,
`CardHeader` and `Button` the way `Staff.tsx` does. Its shapes mirror the
API's `TrainingState` payload exactly: the last-rollover changes panel and
the focus picker are the two things `specs/archive/weekly-training-focus.md` asks
for, with nothing invented around them.

`Finances.tsx` likewise has **no mockup** — `design/` predates the economy
as a domain. It follows the same staff-composition rule, and its copy comes
from the ledger's own kinds (`economy/README.md`): a balance headline that
flags a negative balance, and the history list rendered newest-first with
the per-entry kind label, date and amount. A second tile shows the team's
fanbase with this week's change (green or red, per `economy/README.md`,
*Fanbase is derived too*); merchandise and sponsorship payments each appear
as their own positive ledger lines, and `prize_money` renders as "Prize
money" beside the other kinds. Its `formatMoney` helper is exported, since
`Race.tsx` formats race prize money with it too. The design's "CLUB"
grouping is aspirational — the SPA has no such section — so `/finances` is
a nav item in the TEAM section, next to the staff and training screens it
visually matches.

`Sponsors.tsx` is in the same position — `design/` predates sponsorship as
a feature — and follows `Staff.tsx`'s card-grid composition: one card per
offer (sponsor name, the low–high weekly range) with a Sign button, or a
single card for the signed contract once one exists. **The card shows only
the range, never `weekly_base` on its own** — `weekly_base` is the swing
formula's anchor, not a number the player actually receives (unless the
offer is `STEADY`, whose floor and ceiling equal it exactly), so surfacing
it standalone read as a promised amount and confused players in practice.
The range is the honoured contract (`economy/README.md`, *Sponsorship* —
floor/ceiling are stored and never repriced), so it is what the player
should read the offer by; a tight range already conveys "steady" and a wide
one already conveys "volatile" without a separate profile label or blurb.
Every money figure carries the `$` prefix (`AGENTS.md`, *Displaying game
money*) — including both ends of the range, since the range is money too.
`useSponsors.ts` polls the same way `useStaff.ts` does, and exposes
`refresh()` so signing updates the screen immediately rather than waiting
for the next poll.

`RiderProfile.tsx` has **no mockup either** — `design/` predates it, like
Staff, Training, Finances and Sponsors — and, like `CourseProfile.tsx`,
draws its two charts as **hand-written SVG with no charting library**.
`AttributeRadar.tsx` plots the five engine attributes as a ten-ring radar,
whole-number rings and a printed value at each vertex, matching the
roster's 0-10 display scale exactly — it never interpolates, smooths or
animates between values, since the input is already the coarse display
number. `AttributeHistoryChart.tsx` plots the same five attributes as a
**step chart**, never a sloped line — a displayed value only changes at a
recorded snapshot, so a slope between two snapshots would invent an
intermediate value the player was never shown. Both read `attributeColor`
for their five series (*Conventions*, above). The history chart's
right-hand end is always the rider's **current** attributes, not the last
recorded snapshot — `historySeries` appends that final point itself, so a
late or missing snapshot can never make the radar and the history chart
disagree about a rider's present shape (`specs/rider-detail-view-plan.md`,
D7-D8).
