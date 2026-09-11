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
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
.venv/bin/python -m pytest
```

Settings are split: `config/settings/base.py` holds what is shared, with
`dev.py` (DEBUG, local Postgres defaults) and `prod.py` (env-driven credentials) on top.
`manage.py` defaults to `config.settings.dev`.

## Game Domains

Each domain is a Django app. **Apps are created when a feature needs them**, not
up front — an empty app is just noise. The table below marks which exist.

| Folder | Domain | Status | Description |
|--------|--------|--------|-------------|
| `race_engine/` | Race Engine | **built**, `README.md` | Core simulation: rider attributes, tactics, terrain, weather, fatigue. Pure Python, no Django. |
| `race_player/` | Race Player | **built**, `README.md` | React visualizer for race logs: elevation profile, rider markers, playback. |
| `racing/` | Racing | **built**, `README.md` | The seam between Django and the engine: race records, results, log storage, ORM↔dataclass adapter. |
| `core/` | Core | **built** | Shared abstract models. Deliberately tiny. |
| `accounts/` | Accounts | **built** | Custom `User`. Exists from the first migration by necessity. |
| `riders/` | Riders | **built** (model only) | Persisted riders mirroring the engine's attributes. Generation, aging, form, injury still to come. |
| `teams/` | Teams | **built** (model only) | Teams, codes, colours, manager link. Roster/staff/tactics still to come. |
| `transfers/` | Transfers | *not yet* | Market for buying/selling riders, auctions, contracts, free agents, market value. (The youth academy is a **development squad** and lives in `riders/`.) |
| `competitions/` | Competitions | *not yet* | Divisions and Groups, standings, points, promotion/relegation, classifications, season history. A **Division** is a tier; a **Group** is a parallel section within one. |
| `schedule/` | Race Calendar | *not yet* | Seasons, race types (classics, stage races, TTs), scheduling, race-specific rules. **Not** `calendar/` — that shadows the stdlib module. |
| `economy/` | Economy | *not yet* | Budgets, sponsorships, prize money, fanbase/merchandise. Use an append-only ledger, not a mutable balance field. |
| `staff/` | Staff | *not yet* | Hired trainers, physios and scouts. Fixed slots, one per role per team. |
| `world/` | World Simulation | **built**, `README.md` | The game clock and the tick. AI team decisions still to come. |
| `api/` | API | **built**, `README.md` | DRF routers aggregating each app's serializers and views. |
| `frontend/` | Frontend/UI | **scaffold**, `README.md` | The React SPA. Built to `frontend/dist/`, served by Django. Dashboard and Roster render from the mockup; everything else is a placeholder route. No DB yet. |

### Dependency direction

Keep this one-way; it is what stops the apps tangling:

```
accounts      -> (nothing)
core          -> (nothing)
riders        -> core, teams
teams         -> core, accounts
staff         -> core, teams, riders
racing        -> riders, teams, race_engine
world, api    -> everything (orchestration / presentation)
```

`world/` and `api/` are the only apps allowed to know about everything, and
nothing is allowed to import *them*.

**`race_engine/` imports nothing from Django, ever.** The only module permitted
to import the engine is `racing/adapters.py`. See `racing/README.md` for why.

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
├── core/
├── accounts/
├── riders/
└── teams/
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
header is repeated on every line. Details in `racing/README.md`.
