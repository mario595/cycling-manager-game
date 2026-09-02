# Cycling Manager Game

An online multiplayer cycling management game where users build and manage fictional cycling teams, compete in leagues, stage races, and classics. Think Sokker but for cycling.

## Tech Stack

- **Backend:** Python, Django, Django REST Framework
- **Frontend:** React, TypeScript
- **Database:** PostgreSQL
- **Deployment:** TBD (target: low-cost/free hosting)

## Game Domains

Each domain lives in its own folder within this project:

| Folder | Domain | Description |
|--------|--------|-------------|
| `race_engine/` | Race Engine | Core simulation: rider attributes, tactics, terrain, weather, fatigue. Determines race outcomes. |
| `riders/` | Riders | Procedural generation, attributes (climbing, sprint, etc.), aging, form, injury, career progression. |
| `teams/` | Teams | User-managed squads: roster, staff, tactics selection, training assignments. |
| `transfers/` | Transfers | Market for buying/selling riders, contracts, free agents, youth academy. |
| `competitions/` | Competitions | League tiers, promotion/relegation, seasons, cup races, championships. |
| `calendar/` | Race Calendar | Race types (classics, stage races, TTs), scheduling, race-specific rules. |
| `economy/` | Economy | Budgets, sponsorships, prize money, revenue streams. |
| `world/` | World Simulation | Background ticks: time progression, AI team decisions, rider development, transfer windows. |
| `multiplayer/` | Multiplayer/Auth | User accounts, authentication, real-time or async race execution. |
| `frontend/` | Frontend/UI | React app: dashboards, team management, race viewer, transfer market UI. |
| `data/` | Data/DB | Persistent storage, seasonal snapshots, historical records, migrations. |

## Project Structure

```
cycling-manager/
├── AGENTS.md              # This file
├── manage.py
├── requirements.txt
├── pyproject.toml
├── race_engine/
├── riders/
├── teams/
├── transfers/
├── competitions/
├── calendar/
├── economy/
├── world/
├── multiplayer/
├── frontend/              # React app (separate or embedded)
└── data/
```

## Development Principles

1. **MVP First:** Build the simplest version that works, then iterate.
2. **Domain-Driven:** Each folder is a Django app with its own models, services, and tests.
3. **Separation of Concerns:** Race engine logic stays decoupled from Django ORM where possible.
4. **Testable:** Each domain should be independently testable.
