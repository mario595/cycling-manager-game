# Cycling Manager Game

An online multiplayer cycling management game where users build and manage fictional cycling teams, compete in leagues, stage races, and classics. Think Sokker but for cycling.

## Domain docs — read on demand

This file is the **only** always-loaded context document. It is deliberately
short: an index, not a manual.

Every domain folder that has been built out carries its own **`README.md`** — the
authoritative spec, design notes, conventions and gotchas for that domain. Those
files are detailed and long, and they are **not** meant to be read up front.

**The rule:** before working in a domain folder, read that folder's `README.md`.
Do not read the others. Engine internals are irrelevant when styling the player,
and vice versa — pulling them all in just crowds out the work.

A folder's `README.md` is the entry point for that folder, and links to any
further docs alongside it (audits, plans, findings). Follow those links only when
the task actually needs them.

When a new domain folder gets real work in it, give it a `README.md` and mark it
in the table below. (`README.md` rather than some other name so GitHub renders it
automatically when browsing into the folder.)

## Feature specs

`specs/` holds product-level feature definitions — what a feature does for the
player, with no implementation detail — and the implementation plan for each,
as `specs/<slug>-plan.md`. Order of work is **spec → plan → code**, one skill
per step: `/product-spec #<issue>` writes the spec and moves the ticket to
**Scoped**; `/tech-plan #<issue>` writes the plan and moves it to **Refined**;
`/implement-plan specs/<slug>-plan.md` builds it in a worktree, one commit per
work item, then opens a PR and moves the ticket to **Implemented**; and
`/code-review #<issue>` reviews that PR and moves it to **Code reviewed**. See
`specs/README.md`, and `.claude/ticket-workflow.md` for the ticket handoff.

**Closing a ticket:** once a ticket is implemented, before opening the pull
request, update the `README.md` of every folder the feature touched with
what was actually built, then delete that ticket's `specs/<slug>.md` and
`specs/<slug>-plan.md`. The spec and plan are working documents for getting
the feature built; once it exists, the documentation that matters lives in
`README.md`, and a spec or plan left behind is a second, aging copy of
decisions the code and the README already record.

**Opening a ticket:** every new issue must be added to the
[Cycling Manager Game](https://github.com/users/mario595/projects/5) project
board, whether it's filed by hand or created while speccing another ticket
(e.g. a piece split out during `/product-spec`). An issue left off the board
doesn't show up in any Status column and gets missed when picking up work —
`gh project item-add 5 --owner mario595 --url <issue-url>`.

`specs/roadmap.md` says **which issues to build next and why**, and which are
deliberately deferred. Read it before picking up work.

`specs/backlog-brain-dump.md` is the captured backlog — 36 items, all tracked
as issues #5-#43. It records *why* each item is shaped the way it is and which
naming and design decisions were already taken; read it before speccing one.

## Design mockups

`design/` holds UI mockups exported from Claude Design — the visual reference
`frontend/` is built against. They are **reference, not source**: nothing there
is compiled or served, and the export is a template DSL rather than runnable
HTML. See `design/README.md` before touching a screen's layout or colours.

## Tech Stack

- **Backend:** Python 3.12.11 (pinned in `.python-version`, managed with pyenv), Django, Django REST Framework
- **Frontend:** React, TypeScript (single SPA, served by Django via WhiteNoise)
- **Database:** PostgreSQL everywhere — production and development alike (local instance via `docker compose`)
- **Deployment:** TBD (target: low-cost/free hosting)

## Running it

```bash
.venv/bin/python scripts/dev_db.py     # create this checkout's database
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
.venv/bin/python -m pytest
```

The same suite runs in CI on every pull request, with an 85% backend coverage
floor — see `.github/workflows/ci.yml`.

**Each git worktree gets its own database, test database and dev-server port**,
derived from the worktree's directory name, so agents working in parallel do not
drop each other's test database or mix two branches' migrations into one schema.
The main checkout keeps the plain `cycling_manager` and port 8000. See
`config/worktree.py`; `python config/worktree.py` prints what this checkout gets.

Settings are split: `config/settings/base.py` holds what is shared, with
`dev.py` (DEBUG, local Postgres defaults) and `prod.py` (env-driven credentials) on top.
`manage.py` defaults to `config.settings.dev`.

## Seeding a world for testing

Before a feature can be tried by hand, the database needs data. Each domain owns
its own seed script, which is additive and safe to re-run. From a worktree's
root, in dependency order:

```bash
.venv/bin/python manage.py seed_user      # accounts: test@mail.com / 123456789
.venv/bin/python manage.py seed_teams --claim-for test@mail.com  # teams: one claimed for the demo account, the rest claimable
.venv/bin/python manage.py seed_trainers  # staff: hireable trainers in the pool
.venv/bin/python manage.py load_season seasons/season-1.example.json  # schedule: season 1's twelve weeks and races
```

`seed_user` is idempotent; the others only add (`load_season` errors if the
season is already declared — pass `--replace` while it has not started).
`seed_teams --claim-for` gives the demo account a team and leaves the rest
unmanaged, so a freshly registered player still has teams to claim.
`mock_clock set <season start>` and `tick` then settle the world, but only under
`GAME_CLOCK_CLASS=world.clocks.MockClock`.

**`seed_teams` runs before `load_season` in the order above**, so at that
point no season exists yet and no team gets a sponsor offer round — that
step is skipped, not broken. Either re-run `seed_teams` once the season is
declared, or move the mock clock to the season's start and `tick`: both
generate every team's round (`economy/README.md`, *Sponsorship*).

**If a feature needs more data to be visible, extend the relevant domain's seed
script and note it here**, rather than inventing data by hand in a database.

**Agent setup when building the review environment:** create the worktree's
database and migrations, then run these seeds before starting the server. See
`.opencode/skills/implement-plan/SKILL.md` (and its `.claude/` twin).

## Game Domains

Each domain is a Django app. **Apps are created when a feature needs them**, not
up front — an empty app is just noise. The table below marks which exist.

| Folder | Domain | Status | Description |
|--------|--------|--------|-------------|
| `race_engine/` | Race Engine | **built**, `README.md` | Core simulation: rider attributes, tactics, terrain, weather, fatigue. Pure Python, no Django. |
| `race_player/` | Race Player | **built**, `README.md` | React visualizer for race logs: elevation profile, rider markers, playback. |
| `racing/` | Racing | **built**, `README.md` | The seam between Django and the engine: race records, results, log storage, ORM↔dataclass adapter. |
| `core/` | Core | **built** | Shared abstract models. Deliberately tiny. |
| `accounts/` | Accounts | **built**, `README.md` | Custom `User`, login by email. Register, log in, log out. |
| `riders/` | Riders | **built**, `README.md` | Persisted riders: engine attributes plus speciality, build, age, generation, the weekly age curve (growth/decline), trainer-driven weekly training, rider freshness (fatigue and weekly recovery), and a per-rider weekly salary set at generation and frozen for the season. |
| `teams/` | Teams | **built**, `README.md` | Teams, codes, colours, manager link, claiming an unmanaged team (which resets its ledger balance and fanbase via takeover entries), and releasing a managed team back to the pool with a private record of the spell (#62). Staff/tactics still to come. |
| `transfers/` | Transfers | *not yet* | Market for buying/selling riders, auctions, contracts, free agents, market value. (The youth academy is a **development squad** and lives in `riders/`.) |
| `competitions/` | Competitions | **built**, `README.md` | Race points, prize money and season standings, one Group. The prize table is computed here but written to `economy/`'s ledger. Divisions, multiple Groups, promotion/relegation, classifications and season history still to come. A **Division** is a tier; a **Group** is a parallel section within one. |
| `schedule/` | Schedule | **built**, `README.md` | Seasons, their twelve weeks, and the race calendar declared within them. **Not** `calendar/` — that shadows the stdlib module. |
| `economy/` | Economy | **built**, `README.md` | The append-only ledger: every team's balance is the sum of its `LedgerEntry` rows — starting balance, weekly wages (the sum of each rider's own weekly salary), race prize money, trainer hire fee and weekly trainer salary, merchandise income, sponsorship, claim takeover — and its fanbase, the sum of its `FanbaseEntry` rows. A team picks one of three fanbase-sized sponsor offers per season; its weekly payment then swings with race results inside a promised range. Budgets still to come. |
| `staff/` | Staff | **built**, `README.md` | Trainers hireable from a shared pool into one fixed slot per team at a speciality-derived hire fee plus a weekly salary, plus the team's weekly training focus and its rollover report. Physios and scouts still to come. |
| `world/` | World Simulation | **built**, `README.md` | The game clock and the tick (which charges each team its weekly wages and trainer salary, adjusts fanbase, pays merchandise income and sponsorship, and generates each team's sponsor offer round on season open). AI team decisions still to come. |
| `api/` | API | **built**, `README.md` | DRF routers aggregating each app's serializers and views. |
| `frontend/` | Frontend/UI | **built**, `README.md` | The React SPA. Built to `frontend/dist/`, served by Django. Eight real screens (dashboard, roster, staff, sponsors, calendar, results, league table, finances) plus squad selection, all from the API, no fixture data. Unknown paths redirect to `/`; every route requires a session. |

### Dependency direction

Keep this one-way; it is what stops the apps tangling:

```
accounts      -> (nothing)
core          -> (nothing)
riders        -> core, teams
teams         -> core, accounts, riders
staff         -> core, teams, riders, schedule
schedule      -> core
racing        -> riders, teams, race_engine, schedule
competitions  -> core, racing, teams, schedule
economy       -> core, teams, riders, schedule
world, api    -> everything (orchestration / presentation)
```

`world/` and `api/` are the only apps allowed to know about everything, and
nothing is allowed to import *them*.

**`teams -> economy` is an exception that proves the rule.** `teams/` may
import exactly the `economy/` functions it needs — `reset_to_starting_balance`
and `reset_fanbase` in `claim_team`, `ensure_opening_balance` and
`ensure_starting_fanbase` in `seed_teams`' `handle()` — all **inside function
bodies, never at module scope**. A module-scope import would
load `economy/` (and through it `teams/`) the moment `teams/models.py`
loads, creating an import cycle; the lazy import keeps the edge real but
breaks the cycle. It is the same entry-point pattern as `schedule/`'s
`load_season` command importing `racing.models` inside `handle()`. See
`teams/README.md` and `economy/README.md`.

**`race_engine/` imports nothing from Django, ever.** The only module permitted
to import the engine is `racing/adapters.py`. See `racing/README.md` for why.

**`staff -> schedule` is a *string-only* reference.** `staff.TrainingWeekReport.week`
is a `ForeignKey("schedule.Week", ...)` declared as a string, so `staff/models.py`
imports nothing from `schedule/` — the same import-free pattern `racing/models.py`'s
`Race.week` uses. The edge in the graph is real; a string FK is still a dependency.
See `staff/README.md`.

**`schedule -> core` still holds even though `schedule`'s `load_season`
command creates `racing.Race` rows.** `schedule/management/commands/load_season.py`
imports `racing.models.Race` and `world.services.now` **inside `handle()`**,
never at module scope, and `schedule/`'s library code (`models.py`,
`services.py`, `loaders.py`) imports neither — a management command is an
entry point, the same way `world/`'s own commands are. This is deliberate,
not an oversight in the graph above; see `schedule/README.md`, *What
`schedule/` may import*.

## Project Structure

```
cycling-manager/
├── AGENTS.md              # This file — the index (CLAUDE.md symlinks to it)
├── manage.py
├── requirements.txt
├── pyproject.toml
├── config/                # Django project: settings/, urls, wsgi, asgi
│   └── settings/          # base.py + dev.py + prod.py
├── specs/                 # product-level feature specs (what, not how)
├── design/
│   ├── README.md          # how to read the mockups; what is built from them
│   └── *.dc.html          # Claude Design exports — reference, never a build input
├── frontend/
│   └── README.md          # the SPA scaffold, the /static/ prefix, conventions
├── race_engine/
│   └── README.md          # engine spec + its own linked docs
├── race_player/
│   └── README.md          # visualizer design notes
├── racing/
│   ├── README.md          # the Django<->engine seam, log storage
│   └── adapters.py        # the ONLY importer of race_engine
├── competitions/
│   └── README.md          # race points, standings, what may import back
├── schedule/
│   └── README.md          # seasons, weeks, the transition record
├── core/
├── accounts/
│   └── README.md          # email login, session auth, what this app may import
├── economy/
│   └── README.md          # the append-only ledger, the balance-as-sum rule
├── riders/
│   └── README.md          # attributes, display scale, generation
├── teams/
│   └── README.md          # codes, colours, claiming an unmanaged team
└── staff/
    └── README.md          # the trainer pool, the one-slot rule, hiring
```

## Development Principles

1. **MVP First:** Build the simplest version that works, then iterate.
2. **Domain-Driven:** Each folder is a Django app with its own models, services, and tests.
3. **Separation of Concerns:** The race engine stays decoupled from the Django ORM. This is a hard rule, not an aspiration — see `racing/README.md`.
4. **Testable:** Each domain should be independently testable.
5. **Create apps on demand:** Add a Django app when a feature needs it, and give it a `README.md` at the same time.

## Generated files

Race logs (`*.jsonl`) are never source. They are gitignored; never commit them.

Two ways they come into being, and the distinction matters:

- **Standalone engine runs** — `python -m race_engine <config.json>` writes into
  `race_player/public/` for local visualizer work. Throwaway, regenerate freely.
- **Simulated game races** — written through Django's storage API and pointed at
  by a `RaceLog` row. These are **authoritative records**, not build output: the
  engine evolves, so re-running a stored seed on a newer engine will not
  reproduce the race it recorded. See `racing/README.md`.

The log format is knowingly verbose and slimming it is planned work — the static
header is repeated on every line, and a single mountain stage runs to 75 MB.
Tracked as [#88](https://github.com/mario595/cycling-manager/issues/88); details in `racing/README.md`.

## Displaying game money

The game's currency is an abstract whole-number unit, never a real-world
currency and never a decimal (see `economy/README.md`). Anywhere an amount of
it is shown to the player, prefix it with **`$`** — `$471,982`,
thousands-separated. The `$` is a genre convention (Sokker and similar
management games use it the same way) rather than a claim that this is real
money; it exists so a money amount is never mistaken for a plain count of
something else on the same screen — a fanbase number, a rider count, a
position — which get no symbol at all.

Only amounts of the game's currency get the `$` prefix. A count of anything
else (fanbase, riders, race points) is shown as a plain number.
