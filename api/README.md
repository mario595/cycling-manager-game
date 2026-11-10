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
  mapping it to player-facing words is the SPA's job. Each race also
  carries `stage_race` — `null` for a one-day race, else `{id, name,
  stage_number, stage_count}` — so the SPA can fold consecutive stages of
  one tour into a single calendar entry without a second request. See
  `schedule/README.md`, *The race calendar*, and `racing/README.md`,
  *Stage races*.
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

  **A stage race's later stages are different.** `stage_race` on the
  payload is `null` or `{name, stage_number}`. For `stage_number > 1`,
  `editable` is always `false`, `GET` returns `racing.services.
  carried_squad` (never `suggested_squad` — that falls back through
  `previous_squad`'s "most recent race raced", which is the wrong rule for
  a squad that is always stage 1's, carried forward) rather than a fresh
  suggestion, and `PUT` is always a 400 — `set_squad` refuses any stage
  past the first outright. See `racing/README.md`, *Stage races*.
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
   Every rider payload at every call site also carries **`final_season`**:
   `true` only while a season is open *and* the rider is active *and* past
   their hidden retirement age, i.e. the one season left where they can
   still race for the team
   ([#42](https://github.com/mario595/cycling-manager/issues/42); see
   `riders/README.md`, *Retiring by age*). It is a `SerializerMethodField`
   reading `riders.services.is_due_to_retire`, so the age behind it — and
   the `peak_age`/`decline_rate` it is derived from — is never shipped.
   The "is a season open" half is `_in_season`, a per-request check cached
   on the serializer's `context`, because a roster is dozens of riders
   sharing one world position: reading it per rider would put a constant
   extra query set on every payload, and `context` is the only place
   already per-request. It is deliberately **not** a model field or a
   `week__`-join: a boolean that changes on a clock tick, not on a save,
   cannot be cached on the row, and the season is not in the queryset.
   `True` is not shipped off-season either — between seasons the tag would
   name a season that is over, and the next one is decided by ageing that
   has not run yet.
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
  `team_for()` gate). `404` only for a deleted never-raced rider; a retired
  rider remains available. The identity keys (`id` through `release_cost`)
  are inherited unchanged from `RiderSerializer` — `release_cost` serializes
  as `null` here, the same documented behaviour `FreeAgentSerializer` relies
  on, since no team context is passed. Seven keys are added: `team`
  (`id`/`name`/`code`, or `null` for a free agent — the rider's **current**
  team, not who they raced for); `development_squad` (`id`/`name`/`code` of
  the team whose squad this rider sits in, or `null` — set only for a
  development squad rider (#33), whose `team` is always null; see
  `riders/README.md`, *Youth intake*); `current_week` (`{season, week}`, or `null`
  before any season has ever been declared — `schedule.services.current_position`,
  with an
  off-season world reporting its just-finished season's last week);
  `retired` (`{season, week}` when the rider has retired, otherwise
  `null`) — an in-season retirement reports the season and week, an
  off-season retirement reports the season and `week: null`, and a retirement
  with no season reports `{season: null, week: null}`;
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
  `{riders: [...], balance}`. `riders` is the active free-agent pool, every
   active rider with no team, ordered by name, each carrying `signing_fee`
   (`transfers.pricing.signing_fee_for`, exact credits) and — inherited
   from `RiderSerializer` — all the roster fields, `final_season` included,
   so a buyer sees a rider's last season **before** paying the signing fee
   rather than after; a free agent's
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
  signed, a retired rider, a full roster, or an unaffordable fee is a **409**
  — the request is well-formed but the game's state refuses it; no team is
  a 403. Success is 204.
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
   how many bids or auctions are open. History and `min_next_bid` both read
   **live** bids only (`Bid.objects.live()`, #30): a bid withdrawn by a team
   claim stays in the row as history but must read as never having happened.
   A caller with no team gets a 403.
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
  **Live bids only** (#30), so a withdrawn bid drops out of the list as well
  as out of `is_high_bidder`. Read-only, polled the same way
  `FreeAgentsView` is.
- `GET /api/racing/races/<race_id>/` — one race's own facts
  (`RaceDetailSerializer`, `RaceDetailView`): id, name, status, starts_at,
  distance and the raw `{length, gradient}` course segments. It also carries
  `markers`, the race's `RaceMarker` rows in course order
  (`{kind, name, distance, category, weight, points}` — see below). It also
  carries
  `payout` — the race's `{position, points, prize}` list for 1st through 10th,
  from `competitions/scoring.py`'s two tables — so the SPA can show the prize
  list before the race has run. It also carries `has_replay`: whether a
  `RaceLog` row with a file exists for this race. It is a `boolean`, never
  absent, and it is `false` for any race that has not finished as well as for
  a finished one recorded before replays existed — the SPA decides between
  "Watch race" and a note, and never has to infer it. Readable by any
  authenticated manager regardless of team — the contrast with `SquadView`
  below, which 403s a caller with no team. No status filter: a `scheduled`,
  `running`, `finished` or `failed` race all return `200`; the status is in
  the payload and the SPA decides what to draw.

  **A stage of a stage race carries two more fields.** `payout` reads the
  reduced stage table instead of the one-day table; `gc_payout` is `[]` for
  a one-day race, else the (bigger) GC table — the award for the whole tour,
  paid once on the final stage. `stage_race` is `null` or `{id, name,
  stage_number, stage_count, stages}`, where `stages` lists every stage of
  the tour (`{id, stage_number, starts_at, status}`) so the race screen can
  draw a strip linking between them. See `racing/README.md`, *Stage races*.
- `GET /api/racing/races/<race_id>/log/` — a finished race's recorded log,
  as the newline-delimited JSON the race engine wrote (`RaceLogView`). The
  body is **streamed from storage** in chunks, never read into memory whole:
  a five-hour stage's log is tens of megabytes decompressed.
  - **Compression is content negotiation, not a header of our own.** The
    stored file is brotli (`*.jsonl.br`), so if — and only if — the request
    accepts `br` (`br` in `Accept-Encoding` with `q=0` for `br` not
    counted as acceptance), the stored bytes are streamed as they are, with
    `Content-Encoding: br`. A client that does not accept `br` is served the
    **decompressed** log instead, with no `Content-Encoding` at all. There is
    no `?decompress=1` escape hatch and no third state: the client's own
    header is the only input, so a proxy, a CDN and a browser all get an
    answer they can decode.
  - `Vary: Accept-Encoding` is always set, so a cache between the client and
    Django cannot hand a brotli body to a client that cannot read one.
  - `Content-Type: application/x-ndjson`, set **explicitly** rather than left
    to Django's default for a streaming response. The parser on the other end
    splits on newlines; the type says what it is, and an absent header is
    exactly what would make a future caller treat it as `text/html`.
  - `Cache-Control: private` — a race log is a manager's business, and a
    shared cache must not hold one.
  - A `404` in three cases, all "there is no replay for this race": the race
    is not `FINISHED`, the race has no `RaceLog` row, or its row's file is
    missing or empty in storage. Not a `403` and not a `500` — an unfinished
    race has no log, and that is an ordinary state, not an error worth
    showing a manager.
  - `IsAuthenticated`, the project default, like every other view here.
    `/media/` is **not** linked from this payload: a log is only ever fetched
    through this endpoint, never by URL, so the log's storage name never
    reaches the client.
- `GET /api/racing/races/<race_id>/results/` — a finished race's finishing
  order plus each team's points and prize money from it (`RaceResultsSerializer`,
  `RaceResultsView`). A race that has not reached `FINISHED` is a `404`, not
  a `200` with an empty list — "no results yet" and "no such race" would
  otherwise look the same to the SPA. `points` carries one row per team that
  started, scoring teams first ordered by position and then the rest by
  marker points then name, with `position: null` and `prize: 0` for a team
  that scored no finish points — the starter set comes from `RaceSquad`, not
  from which teams recorded a result (see `racing/README.md`, *Squads*).
  Each row's `points` is `finish_points + sprint_points + mountain_points`:
  `finish_points` is what `RacePoints` awarded (0 if none), `sprint_points`
  and `mountain_points` are the team's `MarkerPoints` for this race split by
  marker kind (0 if none) — a team can be in the "unplaced" group by finish
  and still carry a nonzero `points` from markers alone. The split is keyed
  by kind rather than summed into one column, so a climb never shows up as
  sprint points. `prize` is the team's total winnings, summed from its
  `prize_money` ledger entries for the race, so the results page and the
  ledger cannot disagree. `IsAuthenticated`, the project default.

  Each row's own `team` (in `results`, alongside `rider`) is the team that
  rider **raced for**, from `RaceSquadRider` — not `rider.team`, which is
  the rider's *current* team and would mislabel every past race of a rider
  who has since been released or re-signed. The rider profile endpoint
  above reads the same squad rows for the same reason, so the two screens
  always agree about which team ran a given race.

  The payload also carries `markers`, one entry per `RaceMarker` in course
  order, each with `crossings` — the first `MARKER_PLACES_SHOWN` (**5**,
  raised from 3 to match the marker scoring depth so every scoring position is
  visible — #16) riders across that marker, `{position, rider, team,
  points}`. `team` here is again the team raced for (the same
  `team_by_rider` map the results rows use), so a rider released since
  still shows the team they crossed with. `points` is what that crossing
  scored, read from the marker's own kind — `null` for a crossing whose
  teammate already took the team's one scoring row at that marker
  (`competitions/README.md`, *Marker points*). The full crossing
  order stays in the database; a 64-rider field over ten markers
  is 640 rows this screen never draws. `markers` is `[]` for a race with
  none.

  A marker entry itself (both here and on race detail above) carries
  `category`, `weight` and `points`: for a sprint marker, `weight` is its
  `minor`/`standard`/`major` tier and `points` is that tier's award by
  crossing position, `[1st, 2nd, 3rd, 4th, 5th]` — e.g. `[6, 4, 3, 2, 1]`
  for `standard`; for a mountain marker, `category` is its `hc`/`cat1`/`cat2`/
  `cat3` class and `points` that class's award, e.g. `[10, 7, 5, 3, 2]` for
  `hc`. The other field is `null` in each case, so a client never has to
  guess which of the two vocabularies a marker is scored under.

  Each `results` row also carries `group_time` — the finish time shared by
  every rider who crossed with no meaningful gap to the rider ahead, null
  for a non-finisher, written for every race (one-day included) but only
  ever read by the `gc` block below; a one-day race's own gap display still
  reads `finish_time`. `race` itself carries `stage_race` (`null` or
  `{id, name, stage_number, stage_count}`). `points` (the team-points list,
  not a crossing's `points` above) is filtered to `RacePoints.kind ==
  RACE` — a completed tour's final stage also carries its `kind == GC`
  award, and that belongs in `gc`, not in the stage's own team-points
  table.

  `gc` is `null` for a one-day race. For a stage race's stage it is
  `{after_stage, final, standings, points}`:
  `racing.services.general_classification(stage_race,
  through_stage=race.stage_number)` as of *this* stage, `final` true once
  the whole tour has completed and this is its last stage, `standings` one
  row per eligible rider (`{position, rider, team, gc_time, gap}`, `gap` is
  seconds behind the leader, `0` for the leader), and `points` — the frozen
  GC award, `[]` until `final` — each team's best-placed GC rider's
  `{team, position, points, prize}`, prize summed from that team's
  `gc_prize_money` ledger entries for the final stage, the same pattern
  `prize` above uses for `prize_money`. See `racing/README.md`, *Stage
  races*.
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
  The claim, `transfers.services.withdraw_bids(team, at=at)` and
  `transfers.services.cancel_listings(team, at=at)` run inside **one**
  `transaction.atomic()`, with the `except` clauses outside it, so a new
  manager inherits neither the team's standing bids (#30) nor its open
  listings (#114), and no tick can resolve one of them to them in between (see
  `transfers/README.md`, *Withdrawal and cancellation on claim*). Since #34 a
  claim also closes the team's squad; the graduates it releases are still
  listed with this team as seller, so the same `cancel_listings` call ends
  their auctions too.
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
- `GET /api/development-squad/` (`DevelopmentSquadView`, #32) — the caller's
  development squad as the whole screen's state: `level` (null while closed),
  `balance`, and every level with its `level`, `name`, `weekly_cost`,
  `season_cost` (the weekly cost times
  `schedule.models.SEASON_WEEKS`, so the screen can show a season's total
  without hardcoding how long a season is), `fee`, `action` and `requires`.
  `fee` is what moving to that level **from where the team is now** would
  cost, and the ladder makes that a property of the level rather than of the
  move: opening (at the entry level) and upgrading both charge the target's
  own `opening_fee`, so the panel quotes 150,000 for Elite and the ledger is
  debited 150,000. `action` is the server's own `level_status` answer —
  `open`, `upgrade`, `current`, or `locked` — and `requires` is that answer's
  reason, non-null for every `locked` level. A closed squad is
  a normal `200`, not a `404`: "you have no squad" is a state this screen
  exists to show.

  The server owns that rule and every caller reads it from here, so the figure
  shown, the figure charged and the padlock drawn cannot drift. `action` is
  sent verbatim rather than as the parts it came from (`is_current`, a
  per-level affordability flag): the rule that gates a level is a rule about
  the game, not about the screen, and deriving it twice is how a padlock and a
  409 come to disagree. The two lock reasons are the reason for `requires` —
  "Upgrade to National first" and "Climbed past. Close the squad to start
  over." are different sentences about the same `locked` action, and only the
  server knows which applies.

  Since #33, the payload also carries `riders` and `intake`. `riders` is the
  squad's own riders, strongest first (`riders.pricing.strength`), through a
  dedicated `DevelopmentSquadRiderSerializer` — identity, speciality, age,
  the five attributes on the 0-10 display scale, `arrived` (`{season,
  week}`, resolved through `current_position(rider.intake_at)` the same way
  `retired_payload` resolves `retired_at`), and `is_new`. **No
  `weekly_salary`, `market_value`, `release_cost` or `final_season`** — none
  of those apply to a rider who draws no wage and isn't in any market, and
  they are deliberately not inherited from `RiderSerializer` (see
  `riders/README.md`, *Youth intake*). `is_new` is true only for riders whose
  `intake_at` equals the most recently opened intake week's `starts_at`
  (`_latest_intake_at`) — after the next batch arrives, the previous one
  stops being new even though it is still in the squad. `intake` is
  `{every_weeks, batch_size, next}`, where `next` is `{season, week}` of the
  first declared intake week after now, or `null` once none is declared
  (`_next_intake`). Both keys resolve against `schedule.Week` rows, not a
  reimplementation of `% INTAKE_INTERVAL_WEEKS` in SQL — the cadence rule
  lives once, in `riders.youth_intake.is_intake_week`. `riders` is `[]` and
  `intake` is `null` while the squad is closed — a closed squad has no
  riders and nothing due.

  **Since #34 the payload carries the squad's own state and splits its
  riders in two.** `places` is the held level's capacity and `in_squad` how
  many of them are used — so "make room" on the screen means a number rather
  than an impression — and `roster_count` with `roster_cap` is the *team's*
  roster, sent so the screen can disable Promote instead of offering an action
  the server would refuse with a 409. Each level also carries `places` (6 / 8 /
  10), because a rung's cost and its capacity are read together.

  `riders` is now **only the in-squad prospects**, and `graduates` is a
  separate list — a graduate keeps its squad link but occupies no place
  (`riders/README.md`, *Youth triage*), so mixing the two in one list made
  "how full is my squad" unreadable. Both are ordered strongest first.
  Every row adds `weeks_left` (the rest of the spell for a prospect, the
  remaining decision window for a graduate — **a count, not a
  `{season, week}`**, since the next season is often undeclared and a
  position-less rider is exactly the one a manager needs a number for, and
  **the total less the weeks already opened** rather than the plan's
  `+ 1 - opened`: the week a rider arrives in is the week whose opening has
  already counted for them, and they develop nothing until the next boundary,
  so counting it again would read "Decide within 3 weeks" on a two-week
  window),
  `change` (displayed movement on each of the five attributes since the
  intake's baseline snapshot, on the 0-10 scale both sides are taken on, and
  **`null`** when the rider has no baseline rather than a fabricated zero),
  and `promotion_salary` (what they would draw once promoted — a squad rider
  draws nothing today, so this is the only wage figure that applies). A
  graduate row adds `market_value` and `listed`.

  **Every one of those figures is built once for the squad and passed to the
  serializers through `context`** — `weeks_left`, `graduate_weeks_left`,
  `promotion_salaries`, `market_values`, `listed` and `baselines` are all
  per-squad maps keyed by rider pk. A `SerializerMethodField` that queried per
  rider would turn one squad screen into thirty queries, and the endpoint is
  asked about at most ten riders. `intake.next` also carries
  `arrivals_at_risk`: how much of that batch would be turned away if nothing
  changes before the week, computed from `free_places`, so the warning can be
  given **before** the week rather than after. It is a projection — promoting
  or discarding a prospect moves it.
- `POST /api/development-squad/open/` (`OpenDevelopmentSquadView`) — open the
  squad at `{level}`, debiting that level's fee. `204`; `409` if a squad is
  already open, if `level` is not the entry level (`LevelLocked` — however rich
  the team is, a squad is opened at the bottom), or the team cannot afford it;
  `400` for a level outside `1..3`, from the serializer's `ChoiceField`, before
  the view runs.
- `POST /api/development-squad/level/` (`ChangeDevelopmentSquadLevelView`) —
  move the open squad to `{level}`, which must be the level directly above the
  one held. `204`; `409` if no squad is open, if the team is already at that
  level, if `level` skips a rung (`LevelLocked`), if `level` is below the one
  held (`CannotDowngrade` — there is no way back down, and the refusal says so
  rather than reading as an arbitrary error), or if the team cannot afford it.
- `POST /api/development-squad/close/` (`CloseDevelopmentSquadView`) — close
  the squad. `204`; `409` if none is open, rather than a silent `204` that
  would make a double-click look like a success. `POST` rather than `DELETE`
  for `FireTrainerView`'s reason and then some: the row really is deleted, but
  the opening fee already paid stays in the ledger, so nothing here is
  destroyed. A close has disposed of every rider in the squad since #33, and
  since #34 the two states go opposite ways — every rider still **in** the
  squad is discarded outright, every **graduate** is released to the
  free-agent pool — calling `close_squad(team, at=now())` and see
  `riders/README.md`, *Youth intake* and *Youth triage*. Since #34 it wraps
  that in one transaction with
  `transfers.services.cancel_unowned_listings(team, at=at)`, because a
  released graduate's auction would otherwise stay biddable until its
  deadline and its winner would be refused by the very ownership check that
  would have caught it days earlier.
- `POST /api/development-squad/riders/<id>/promote/`
  (`PromoteSquadRiderView`, #34) — move a prospect **or a graduate** onto the
  senior roster. `204`; `409` for another team's rider (`NotYourProspect`) or
  a roster already at `transfers.services.ROSTER_CAP` (`RosterFull`). It works
  on a graduate because deciding early is a choice a manager is entitled to
  make — the alternative the spec weighed was refusing it, with the worse
  consequences. `ROSTER_CAP` is **passed in** rather than imported by
  `riders/`, which may not know about `transfers/`; the screen disables the
  button from the payload's `roster_count`/`roster_cap` first.

  Promoting a **listed** graduate also cancels their auction, in the same
  transaction. The squad screen keeps Promote available on a listed rider — a
  listing takes away the *sale*, not the option of keeping them — so this is
  the only honest reading of the button: the manager is choosing the rider over
  the bids, and the sale ends. Left alone, the auction would sit open over a
  player the team is now paying and fielding.
- `POST /api/development-squad/riders/<id>/discard/`
  (`DiscardSquadRiderView`, #34) — discard a prospect or a graduate for good;
  they leave the game rather than joining the free-agent pool. `204`; `409`
  while an auction of theirs is open (`ProspectListed`). `POST` like every
  other action here: the request is an order, not a description of a resource
  that is already gone. The listing rule arrives as an **injected `check`
  callback** (`_not_listed`), so `riders/discard` needs no knowledge of the
  auction market — the same shape `promote`'s `roster_cap` argument takes.
  It raises rather than returning a verdict, because a check that returns one
  can be forgotten by a caller while one that raises cannot.

  All six are `IsAuthenticated` by the project default — **no `AllowAny`** —
  and all six return `403` without a team, the same `team_for()` check every
  other team-scoped view makes. The three writes share a module-level
  `_squad_charge(team)` helper that is the injected `charge` callback: the
  balance check and the `economy.services.charge_development_squad_fee` write
  happen **inside** the service's own transaction, so a refused open or
  upgrade leaves neither a squad row nor a fee row. It raises
  **`riders.development_squad.InsufficientFunds`**, which is aliased on import
  as `SquadInsufficientFunds` because `staff.services.InsufficientFunds` —
  a different, unrelated class already imported unaliased above — is in scope
  in the same module; catching the wrong one turns a `409` the player should
  see into a `500`.
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

- `GET /api/economy/solvency/` (`SolvencySerializer`, `SolvencyView`) — the
  caller's standing against the insolvency ladder (#27): `insolvent`,
  `balance`, the live weekly `shortfall`, `target` (the shortfall at the last
  payday), `cut_so_far`, `strikes`, `paydays_left` and `deadline` (both null
  when the live shortfall is zero, and `deadline` also when the week it falls
  in is not declared yet), plus `roster_size` and `roster_floor` for the
  force-sale button. A caller with no team gets the solvent shape with zeros,
  matching `FinancesView`. See `economy/README.md`, *Insolvency*.
- `POST /api/transfers/auctions/force/` (`ForceSellView`) — body
  `{rider_id}`. Sells one of the caller's riders under insolvency: the rider
  leaves the roster now and is auctioned with no severance
  (`transfers/README.md`, *Forced sales*). `204` on success. `409` when the
  team is not insolvent, the rider is not on the roster, or the sale would
  take the roster to the floor (`RosterAtFloor`); `403` with no team.
- **The embargo.** While a team is insolvent, `POST` to free-agent signing,
  bidding, trainer hire, development-squad open and development-squad level
  change all return `409` with the same `detail`, checked before the payload is
  validated. Not blocked: sponsor signing, trainer fire, squad close, rider
  release and ordinary listing — each cuts cost or adds income.
- `GET /api/transfers/auctions/` carries `forced` on each auction (#27), so
  the market can label a sale made under insolvency.

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
