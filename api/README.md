# API

## What lives here

DRF routers and serializers that aggregate other apps' data for the SPA.
`api/` owns no models of its own — it translates, it does not persist.

## What exists

- `GET /api/world/clock/` — the game's current time (`ClockSerializer`,
  `ClockView`, serializing `world.services.now()` directly — there is no
  model instance behind this response, since in production there is
  nothing stored to read). See `world/README.md` for what the clock is.
- `GET /api/schedule/position/` — where the world is in its season
  (`PositionSerializer`, `PositionView`, serializing
  `schedule.services.current_position(now())`). One of three shapes,
  discriminated by `state`: `in_season` (with `season`, `week`,
  `week_ends_at`), `off_season` (with `season` — the one that just
  finished — and `week`/`week_ends_at` null), or `no_season` (everything
  null, before any season has ever been declared). See
  `schedule/README.md` for what a season is.
- `GET /api/schedule/calendar/` — the current season's whole calendar
  (`CalendarSerializer`, `CalendarView`). Same `state` vocabulary as the
  position endpoint. `weeks` is always exactly twelve entries when
  `in_season`, each with a `races` list — zero to seven entries, since the
  calendar's rule is at most one race per *day*, not per week — never a
  shorter list and never `null`, so an empty week is visible as one rather
  than looking like missing data. Outside `in_season`, `weeks` is `[]`.
  `status` on a race is `Race.status` verbatim (including `failed`);
  mapping it to player-facing words is the SPA's job. See
  `schedule/README.md`, *The race calendar*.
- `GET`/`PUT /api/racing/races/<race_id>/squad/` — the **caller's own**
  team's squad for one race (`SquadSerializer`, `SquadWriteSerializer`,
  `SquadView`). No team id in the URL: the team is always
  `request.user.team`, via the `team_for()` helper below. `GET` returns the
  team's saved selection if it has one, else a suggestion from
  `racing.services.suggested_squad` (`saved: false`). `PUT` replaces it via
  `racing.services.set_squad` and returns the same shape; a `SquadError` (wrong
  size, a rider from another team, no single leader, or a race that has
  already started) becomes a 400, and a caller with no team becomes a 403.
  `candidates` is the team's whole roster, each flagged `selected`/
  `is_leader`, so one response gives the squad screen everything it draws.
  Its five engine attributes are the 0-10 display scale, same as the riders
  endpoint below — see `racing/README.md`, *Squads*. Each candidate also
  carries `freshness` on that same 0-10 display scale; the hidden
  `recovery_rate` behind it never appears in this or any other payload — see
  `riders/README.md`, *Freshness*.
- `GET /api/riders/` — the **caller's own** team's roster
  (`RosterSerializer`, `RiderListView`): `{riders: [...], squad_value}`.
  Same `team_for()` pattern as the squad endpoint: no team id in the URL, a
  caller with no team gets a 403. Attributes and freshness are shipped
  through `riders.display.to_display_scale` (0-10, never the stored
  1-100); the hidden traits (`potential`, `peak_age`, `decline_rate`,
  `injury_proneness`, `training_affinity`) and the hidden `recovery_rate`
  never appear in this or any other payload — see `riders/README.md`.
  `weekly_salary` ships as the exact stored credits, not through
  `to_display_scale` — see `riders/README.md`, *Salary*. Each rider also
  carries `market_value` (`transfers.pricing.market_value_for`, exact
  credits, computed fresh on every request — never stored), and
  `squad_value` is that same function summed over the response's own
  riders in Python, not a separate query, so the two numbers can never
  disagree (`transfers/README.md`, [#31](https://github.com/mario595/cycling-manager/issues/31)).
Since #29 each rider also carries `release_cost`
  (`transfers.services.release_cost_for`, exact credits): 0 while the
  claim cooldown shields a rider inherited from the team's most recent
  claim, full severance once fewer than `CLAIM_COOLDOWN_WEEKS` in-season
  weeks no longer hold. It is a `SerializerMethodField` that reads
  `context["team"]`/`context["weeks_opened"]` and degrades to `null`
  when a payload is built without a team in scope (free agents), so a
  future second call site fails a test rather than 500ing in production.
  The weeks are counted by `_cooldown_weeks_opened` in `api/views.py`
  (0 for a never-claimed team) — the caller counts, never `transfers/`.
  A third top-level key, `salary_review`, carries the team's most recent
  season-end salary review or `null` when there isn't one (#26).
  `economy.services.latest_salary_review` picks the newest by
  `season__starts_at`, and the payload is `{season_number, payroll_before,
  payroll_after, changes: [{rider_id, rider_name, from_value, to_value}]}`
  — the wage-bill numbers are exact whole credits, and `changes` lists only
  the riders whose salary moved by at least the threshold
  (`riders.pricing.SALARY_REVIEW_THRESHOLD`); see
  `economy/README.md`, *Salary review*. The change keys are exposed as
  `from_value`/`to_value` because the stored document names them `from`/
  `to` — a Python keyword that cannot be a serializer field name, hence
  DRF's `source="from"` mapping.
  This response shape changed with #31: it was previously a bare array.
- `GET /api/riders/<rider_id>/` (`RiderProfileSerializer`, `RiderProfileView`)
  — one rider's full profile, readable by **any** authenticated manager
  regardless of team (like `RaceDetailView`, not `RiderListView` — no
  `team_for()` gate). `404` for a rider that no longer exists. The identity
  keys (`id` through `release_cost`) are inherited unchanged from
  `RiderSerializer` — `release_cost` serializes as `null` here, the same
  documented behaviour `FreeAgentSerializer` relies on, since no team
  context is passed. Four keys are added: `team` (`id`/`name`/`code`, or
  `null` for a free agent — the rider's **current** team, not who they
  raced for); `current_week` (`{season, week}`, or `null` before any season
  has ever been declared — `schedule.services.current_position`, with an
  off-season world reporting its just-finished season's last week);
  `attribute_history`, the rider's `riders.RiderAttributeSnapshot` rows in
  time order — the baseline (`week: null`) first, then by
  `(season, week)`, **never** by `created_at`, which a backfill made
  meaningless — already display-scale values, **not** re-passed through
  `to_display_scale` (see `riders/README.md`, *Attribute history*); and
  `races`, every `FINISHED` race the rider has a result for, newest first
  by `starts_at`, each carrying the **team raced for** (from
  `RaceSquadRider`, never `Rider.team` — see below), `position`,
  `finish_time` (`null` for a DNF), `winner_time` (that race's fastest
  finisher, so the SPA can show the same total-time/`+gap`/`DNF` cells the
  results screen does) and `finished`. `career` sums that same `races` list
  in Python — `starts`, `wins`, `podiums`, `top_tens`, `dnfs` — so the two
  can never disagree (the `squad_value` precedent). **Neither `races` nor
  `career` carries a points or prize figure** — both are team awards (one
  team's best finisher, one team's placed riders summed), never an
  individual rider's, and showing one here would misrepresent it as
  personally earned and could not be reconciled against the standings or
  the League table (`competitions/README.md`). `api/rider_profile.py`
  builds the payload in a handful of fixed-shape queries regardless of
  career length — no per-race lookup.
- `GET /api/transfers/free-agents/` (`FreeAgentPoolSerializer`,
  `FreeAgentsView`) — the whole transfer market in one payload:
  `{riders: [...], balance}`. `riders` is the free-agent pool, every rider
  with no team, ordered by name, each carrying `signing_fee`
  (`transfers.pricing.signing_fee_for`, exact credits) and — inherited
  from `RiderSerializer` — all the roster fields; a free agent's
  `release_cost` serializes as `null` (it is on nobody's roster).
  `balance` (`economy.services.balance_for`) rides alongside so the SPA
  can disable the Sign it cannot afford, the same both-keys shape
  `StaffView` uses. A caller with no team gets a 403, like `RiderListView`.
- `POST /api/transfers/free-agents/sign/` (`SignFreeAgentSerializer`,
  `SignFreeAgentView`) — sign a free agent for its `signing_fee`. The
  views pass a `charge` closure into `transfers.services.sign_free_agent`
  that debits the ledger through `economy.services.charge_transfer_fee`
  (a `TRANSFER_FEE` row, description "Signed X"); the closure raises
  `InsufficientFunds` when `balance_for(team) < fee`. A rider already
  signed, a full roster, or unaffordable fee is a **409** — the request
  is well-formed but the game's state refuses it; no team is a 403.
  Success is 204.
- `POST /api/transfers/riders/release/` (`ReleaseRiderSerializer`,
  `ReleaseRiderView`) — release one of the caller's riders to the pool,
  debiting `release_cost_for` the same way. The view's `charge` closure
  writes a `TRANSFER_FEE` row (description "Released X") **only when the
  fee is positive** — a $0 cooldown-exempt release moves no money and
  leaves the ledger untouched. A rider not on the caller's roster is a
  409. Success is 204.
- `GET /api/transfers/auctions/` (`AuctionMarketSerializer`,
  `AuctionMarketView`) — every open auction plus the caller's balance,
  the same both-keys shape `FreeAgentsView` uses. Each entry carries the
  rider (same visible fields the roster shows), `current_price`,
  `min_next_bid`, `deadline`, `is_own_listing` and `bids` — the auction's
  full history, newest first, each row a `{team_name, amount, placed_at}`
  (#28; see `transfers/README.md`, *Auctions*). Bidding is not anonymous:
  every bid names the team that placed it. `bids` is prefetched with its
  `bidder_team` to keep the market a fixed number of queries regardless of
  how many bids or auctions are open. A caller with no team gets a 403.
- `POST /api/transfers/auctions/list/` (`ListForAuctionSerializer`,
  `ListForAuctionView`) — list one of the caller's own riders for
  auction. `RiderNotOnRoster` or `AuctionAlreadyExists` (the rider already
  has an open listing) is a 409 — the request is well-formed, the world's
  state refuses it, the same split every other transfer-market view
  documents. Success is 204.
- `POST /api/transfers/auctions/<auction_id>/bid/` (`PlaceBidSerializer`,
  `PlaceBidView`) — place a bid on an open auction. The view checks
  `balance_for(team) >= amount` itself, **before** calling
  `transfers.services.place_bid` — no money moves until an auction
  resolves, so unlike signing a free agent there is no injected `charge`
  callback on this path. An unaffordable bid, a self-bid, a bid that
  doesn't clear the minimum, or a closed auction are all 409. Success is
  204.
- `GET /api/transfers/auctions/mine/` (`MyBidStatusSerializer`,
  `MyBidsView`) — every open auction the caller's team has an active bid
  on, with `is_high_bidder` — backs the outbid notice (spec item 8).
  Read-only, polled the same way `FreeAgentsView` is.
- `GET /api/racing/races/<race_id>/` — one race's own facts
  (`RaceDetailSerializer`, `RaceDetailView`): id, name, status, starts_at,
  distance and the raw `{length, gradient}` course segments. It also carries
  `markers`, the race's `RaceMarker` rows in course order
  (`{kind, name, distance}`). It also carries
  `payout` — the race's `{position, points, prize}` list for 1st through 10th,
  from `competitions/scoring.py`'s two tables — so the SPA can show the prize
  list before the race has run. Readable by any
  authenticated manager regardless of team — the contrast with `SquadView`
  below, which 403s a caller with no team. No status filter: a `scheduled`,
  `running`, `finished` or `failed` race all return `200`; the status is in
  the payload and the SPA decides what to draw.
- `GET /api/racing/races/<race_id>/results/` — a finished race's finishing
  order plus each team's points and prize money from it (`RaceResultsSerializer`,
  `RaceResultsView`). A race that has not reached `FINISHED` is a `404`, not
  a `200` with an empty list — "no results yet" and "no such race" would
  otherwise look the same to the SPA. `points` carries one row per team that
  started, scoring teams first ordered by position and then the rest by
  name, with `position: null`, `points: 0` and `prize: 0` for a team that
  scored nothing — the starter set comes from `RaceSquad`, not from which
  teams recorded a result (see `racing/README.md`, *Squads*). `prize` is the
  team's total winnings, summed from its `prize_money` ledger entries for the
  race, so the results page and the ledger cannot disagree. `IsAuthenticated`,
  the project default.

  Each row's own `team` (in `results`, alongside `rider`) is the team that
  rider **raced for**, from `RaceSquadRider` — not `rider.team`, which is
  the rider's *current* team and would mislabel every past race of a rider
  who has since been released or re-signed. The rider profile endpoint
  above reads the same squad rows for the same reason, so the two screens
  always agree about which team ran a given race.

  The payload also carries `markers`, one entry per `RaceMarker` in course
  order, each with `crossings` — the first `MARKER_PLACES_SHOWN` (**3**)
  riders across that marker, `{position, rider, team, crossed_at}`. `team`
  here is again the team raced for (the same `team_by_rider` map the
  results rows use), so a rider released since still shows the team they
  crossed with. The full crossing order stays in the database for #16/#17;
  a 64-rider field over ten markers is 640 rows this screen never draws.
  `markers` is `[]` for a race with none.
- `GET /api/competitions/standings/` — the current season's points table
  (`StandingsSerializer`, `StandingsView`, serializing
  `competitions.services.standings`). Same `state` vocabulary as
  `PositionView`/`CalendarView`: `in_season`, `off_season` (the season that
  just finished, with its final table), or `no_season` (`standings: []`).
  `rank` is computed server-side from the sorted order — two teams level on
  points and countback are genuinely joint, and the server is where that is
  known. `IsAuthenticated`, like every endpoint the SPA reads.
- `POST /api/accounts/register/`, `POST /api/accounts/logout/` — owned by
  `accounts/`, included here under `/api/accounts/`. See `accounts/README.md`.
- `POST /api/accounts/login/` (`api.views.LoginView`) — routed **here**,
  ahead of the `include("accounts.urls")` line, so this view wins over the
  plain `accounts.views.LoginView` it subclasses. It does everything that
  view does and then stamps `request.user.last_seen_at` with
  `world.services.now()` — game time, not `django.contrib.auth`'s
  `last_login` — so `world/`'s inactivity trigger has something to measure
  from. The override exists because `accounts/` imports nothing and cannot
  reach `world/` itself (`accounts/README.md`, *Last seen is game time*).
- `POST /api/teams/claim/` (`ClaimTeamSerializer`, `ClaimTeamView`) — assigns
  the caller an unmanaged team, renamed and recoded to their choosing
  (`name`, `code` in the body; a lowercase code is uppercased, not rejected).
  Plain `IsAuthenticated`. Returns the new team (`id`/`name`/`code`, the same
  shape as `me`'s `team`) with 201. A caller who already manages a team, or a
  world with no unmanaged team left, both return 409 — the request is
  well-formed but the world's state refuses it. A malformed code or a name
  already taken returns 400. See `teams/README.md`, *Claiming a team*.
- `GET /api/staff/` (`StaffSerializer`, `StaffView`) — the **caller's own**
  team's staff: `trainer` (null when the slot is empty), `pool` (every
  unemployed trainer, but only populated when the slot is empty — a team
  with a trainer has nothing to hire, so the pool is `[]`), and the team's
  `balance` so the SPA can grey out a hire it cannot afford. Same `team_for()`
  pattern as the squad and roster endpoints: no team id in the URL, a
  caller with no team gets a 403. A trainer's five skills are shipped
  through `to_display_scale`, same as a rider's attributes, alongside the
  two prices derived from their speciality (`hire_fee`, `weekly_salary`) —
  see `staff/README.md`, *What a trainer costs*.
- `GET /api/economy/finances/` (`FinancesSerializer`, `FinancesView`) — the
  **caller's own** team's finances: `balance` (the sum of the ledger, never
  a stored column) and `entries`, newest first, each with `kind`,
  `description`, `amount`, `occurred_at`, `rider_count` and a `balance_after`
  running total computed in Python as the list is walked. `kind` is one of
  `starting_balance`, `wages`, `takeover`, `prize_money`, `merchandise`,
  `trainer_fee` or `trainer_salary` — a finished race pays the placed riders
  of every team it entered, merchandise pays weekly off the fanbase, and
  trainer moves are the one-off fee and the weekly salary. The payload also
  carries the
  team's `fanbase`, this week's `fanbase_change`, and `weekly_wage_bill` —
  the roster's current payroll from `economy.services.payroll_for`, not the
  ledger's last `wages` entry, so it reflects a roster changed since payday
  (`economy/README.md`, *Wages run off week transitions*). Same
  `team_for()` pattern as the staff endpoint: no team id in the URL. Unlike
  `staff/`, a caller with no team gets `{"balance": 0, "weekly_wage_bill":
  0, "entries": []}` — the screen has an empty state, not an error. See
  `economy/README.md`.
- `POST /api/staff/trainer/hire/` (`HireTrainerSerializer`,
  `HireTrainerView`) — hire the pool trainer named by `trainer_id` into the
  caller's empty slot, debiting the hire fee from the team's ledger. `204`
  on success. `409` (not `400`) when that trainer was hired by someone else
  a moment earlier, when the caller's slot is already filled, or when the
  team cannot afford the fee — the request is well-formed, but the world's
  state refuses it, the same split `ClaimTeamView` documents. The debit and
  the affordability check both run **inside** `hire_trainer`'s transaction
  (the injected `charge` callback, `staff/README.md`), so a refused or
  failed hire leaves no fee row and the trainer in the pool.
- `POST /api/staff/trainer/fire/` (`FireTrainerView`) — return the caller's
  trainer to the shared pool. `204` on success, `409` if the caller has no
  trainer to fire. `POST`, not `DELETE`: nothing is destroyed, the trainer
  survives in the pool.
- `GET /api/accounts/me/` (`MeSerializer`, `MeView`) — whether anyone is
  logged in, their display name, their team (`id`/`name`/`code`, or
  `null`), and `lost_team` (#62). Lives here rather than in `accounts/`
  because answering "does this user have a team" needs both `accounts` and
  `teams`, and `accounts/` may import neither — see `accounts/README.md`,
  *What `accounts/` may import*. `@ensure_csrf_cookie`: this is the request
  the SPA relies on to guarantee it holds a CSRF token before it ever
  issues a write (see *Authentication*, below).
  `lost_team` is non-null only when the caller currently has no team **and**
  has an unacknowledged `teams.ManagerialSpell` — the team they most
  recently lost, with `spell` (its id), `name`, `code`, the human-readable
  `reason` label, and `ended_at`. A caller who already has a team is never
  shown one, even if they lost an earlier team at some point: the query only
  runs when `team is None`, so the common case (a manager with a team) pays
  no extra cost on every SPA boot. See `teams/README.md`, *Managerial
  spells*.
- `POST /api/teams/spells/<int:spell_id>/acknowledge/` (`AcknowledgeSpellView`)
  — marks the caller's lost-team message as seen, so `me`'s `lost_team`
  stops reporting it. `204` on success. `404`, not `403`, both when the
  spell does not exist and when it belongs to someone else — a `403` would
  confirm the row exists for a spell id that isn't the caller's. Idempotent:
  a second call (or a lost network response resent) against an
  already-acknowledged spell also 404s, rather than double-writing or
  erroring.

## URL ordering

`config/urls.py` includes `api/urls.py` **above** the SPA catch-all
(`<path:unused>`). The catch-all matches any path, so an API route listed
after it would silently return the SPA's `index.html` instead of JSON.

## Authentication

The project default (`REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]` in
`config/settings/base.py`) is `IsAuthenticated`. The game exposes nothing to
an anonymous visitor: the clock, season position and calendar endpoints used
to override the default with `AllowAny`, but that is **deliberately
reversed** — a visitor who is not logged in gets a 403 from every data
endpoint here. If a future landing page wants shop-window world data for
visitors again, reopen that deliberately, not by assuming today's
auth-on-everything is an oversight.

`MeView` is the single exception, and it **must remain** `AllowAny`. It is
the endpoint that answers "nobody is logged in": the SPA fetches it on mount
and the route guard depends on that answer, so making it `IsAuthenticated`
would 403 the one request that tells the app to show the login screen, and
the app would never boot for a visitor. Its `@ensure_csrf_cookie` is
likewise load-bearing for writes (see *CSRF* below).

`SquadView` and `RiderListView` are both plain `IsAuthenticated`, with the
team always `request.user.team` rather than a URL parameter or query string —
see `team_for()` in `api/views.py`, and `accounts/README.md` for why that
helper lives here instead of in `accounts/`. Neither has an "anyone can view
or edit anyone's squad/roster" hole; a caller with no team gets a 403, not
someone else's data.

**CSRF.** DRF's `SessionAuthentication` enforces CSRF only for
*authenticated* sessions — an anonymous request passes `CsrfViewMiddleware`
untouched, which is why the squad endpoint needed no CSRF handling before
login existed. Now that `SquadView` requires authentication, its `PUT`
enforces CSRF like every other authenticated write, and the SPA sends
`X-CSRFToken` on all of them (`frontend/src/api.ts`'s `writeJson`). The
token itself comes from the `csrftoken` cookie, which `GET
/api/accounts/me/`'s `@ensure_csrf_cookie` guarantees is set before the SPA
issues its first write — see `frontend/README.md`.
