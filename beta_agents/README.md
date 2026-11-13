# beta_agents: the LLM beta testers (#132)

Five AI managers play the staging world on a schedule, each with its own
account, team, persona and diary, and report anything that looks wrong through
the game's report-a-problem channel (#131). The spec and the plan are
`specs/archive/beta-agents.md` and `specs/archive/beta-agents-plan.md`.

**This is not a Django app.** It's a plain Python package that talks to the
game only over HTTP, exactly as a player's API client would. It imports
nothing from the game, and the game imports nothing from it. It uses only the
standard library, so it needs no install step.

## What a visit does

`python -m beta_agents visit <tester>`:

1. Fetches the live OpenAPI schema with the tester's key, and turns every
   operation into a tool named by its `operationId` (`tools.py`). It leaves
   out `login`, `logout`, `register` and `get_race_log`. If the server or the
   key is unusable, the visit is skipped here and the diary is left alone.
2. Gives the model the tester's instructions (`prompt.py`): its role as a beta
   tester whose job is finding problems, its persona, how to report,
   `PLAYERS_GUIDE.md`, and `world/STAGING_BRIEFING.md` (everything after
   its `---` rule). The model also gets the tester's last five diary entries.
3. Runs the tool loop (`visit.py`). A game error, such as a 4xx or 5xx, goes
   back to the model as the tool's result. A wrong answer may be exactly what
   should be reported.
4. Ends when the model calls `finish_visit(diary_entry)`, which appends a
   `## <real UTC time>` section to `diaries/<tester>.md` with a line of visit
   stats.

The limits hold whatever the model does:

| Limit | Value | Where |
|---|---|---|
| Model calls per visit | 40 (`BETA_MAX_STEPS`) | `visit.py`. When the cap is hit, the harness writes the diary entry itself and says so. |
| Reports per visit | 3 | `visit.py`. A fourth call gets a tool error and never reaches the server. |
| Tool result size | 8,000 characters, with a note when cut | `tools.py` |
| Gap between model calls | 1.2 s (`BETA_LLM_MIN_INTERVAL`) | `llm.py` |
| 429s waited out | 3 times, using `Retry-After` | `game_api.py` and `llm.py` |

If the model stops calling tools before `finish_visit`, it is asked once more
for its entry. If the model fails partway through, the harness writes an entry
saying so, and the command exits non-zero.

**No cookies, ever.** Requests go through `urllib.request` with no cookie jar.
A token request that carries a session cookie is treated as a browser request
and needs CSRF (`api/README.md`).

## The testers

`testers.py`. A tester is due when `utc_hour % period == offset`.

| Slug | Persona | Visits |
|---|---|---|
| `youth` | builds through the development squad | every 4 h, at 00, 04, 08… UTC |
| `trader` | trades at auction and in the free-agent pool | every 4 h, at 01, 05… |
| `money` | chases sponsorship and a low wage bill, and audits the ledger | every 4 h, at 02, 06… |
| `racer` | picks a squad for every course, and sets training | every 4 h, at 03, 07… |
| `casual` | minimal effort, leaves squads to the auto-pick | once a day, at 02 UTC |

Exactly one regular tester visits each hour. Four real hours is about four game
days on the staging clock, and once a day stays well inside the 70-hour
inactivity release.

## The workflow

`.github/workflows/beta-agents.yml` runs at minute 17 of every hour. It runs
`python -m beta_agents due`, visits each due tester in turn, then commits
`diaries/` to the **`beta-diaries`** branch, creating the branch on its
first run. That branch is never merged, and pushes to it trigger neither CI
nor the deploy. Read a tester's diary at `diaries/<tester>.md` on that
branch, and a visit's full transcript (every tool call and its status) in the
run's log.

Scheduled workflows only run from the default branch, so the schedule starts
once this is on master.

**Pausing.** The scheduled job runs only while the repository variable
`BETA_AGENTS_ENABLED` is `true`. Set it to anything else to pause every tester.
A manual run (*Actions → Beta testers → Run workflow*, choosing a tester) works
even while paused, which makes it the way to try one visit. A pause longer than
about three real days costs the testers their teams through the inactivity
release. Freeze the staging clock for a long pause (`deploy/README.md`).

## Setting it up

You do this once.

1. **The model key.** Store it as the repository secret `BETA_LLM_API_KEY`.
   Choose the provider with the variables below.
2. **The accounts.** For each tester, from any machine:

   ```bash
   python -m beta_agents --base-url https://velodra.fly.dev register youth
   ```

   This registers `beta-youth@velodra.test` with a random password that
   nobody needs afterwards, and prints the command that issues its key on the
   server:

   ```bash
   fly ssh console --app velodra -C "su app -s /bin/sh -c 'cd /app && python manage.py issue_api_token beta-youth@velodra.test'"
   ```

   Store the printed key as the secret `BETA_KEY_YOUTH`, and likewise
   `BETA_KEY_TRADER`, `BETA_KEY_MONEY`, `BETA_KEY_RACER` and `BETA_KEY_CASUAL`.
   A tester claims its own team on its first visit.
3. **Switch on.** Set the variable `BETA_AGENTS_ENABLED` to `true`. Then try one
   visit by hand from the Actions tab before relying on the schedule.

After a `seed_world --reset`, the accounts and keys survive, because a reset
keeps accounts. The testers lose their teams, and each claims a new one on
its next visit.

## Choosing the model

The model is reached through an **OpenAI-compatible chat completions**
endpoint (`llm.py`). Most providers offer one, so switching provider means
changing these repository variables:

| Variable | Default | Notes |
|---|---|---|
| `BETA_LLM_BASE_URL` | `https://api.mistral.ai/v1` | Gemini: `https://generativelanguage.googleapis.com/v1beta/openai` |
| `BETA_LLM_MODEL` | `mistral-small-latest` | For Gemini, the Flash-Lite model id AI Studio lists |
| `BETA_LLM_MIN_INTERVAL` | `1.2` (seconds) | Keep within the provider's requests per minute. For a 15-a-minute tier, use `5`. |
| `BETA_MAX_STEPS` | `40` | Model calls per visit |
| `BETA_BASE_URL` | `https://velodra.fly.dev` | The game server |

A visit makes up to about 40 model calls. Each call carries about 8K tokens
of instructions and tool definitions, plus the visit's history so far. Budget
about 0.5M tokens and 30 calls per visit, and about 26 visits a real day at
the default cadence. Claude would need a second small client behind the same
`chat()` call, which isn't built.

Free tiers move. In November 2026, Mistral's Free plan stopped activating API
keys, Groq's free tier allowed 200K tokens a day (too few), and Gemini
Flash-Lite allowed about 500 calls a day. Check the provider's console for
the numbers on your own project.

## Trying it locally

Against a dev server seeded with `seed_world`:

```bash
GAME_CLOCK_CLASS=world.clocks.MockClock .venv/bin/python manage.py seed_world --set-clock
.venv/bin/python manage.py runserver
.venv/bin/python -m beta_agents --base-url http://127.0.0.1:8000 register racer
export BETA_KEY_RACER=$(.venv/bin/python manage.py issue_api_token beta-racer@velodra.test)
.venv/bin/python -m beta_agents --base-url http://127.0.0.1:8000 tools          # the generated tool list
BETA_LLM_API_KEY=... .venv/bin/python -m beta_agents --base-url http://127.0.0.1:8000 visit racer --diary-dir /tmp/diary
```

The tests (`beta_agents/tests/`) are plain pytest with fake transports and no
database. `visit.py`'s tests drive a scripted model through a whole visit.

## Keeping it in step

- **The player's guide** (`PLAYERS_GUIDE.md`) is the rules as the testers know
  them. When a rule changes, change it here too, or the testers will report
  the new behaviour as a bug. It states only rules a player can see, and no
  numbers the API already shows.
- **The staging briefing** is read from `world/STAGING_BRIEFING.md` on every
  visit, so it never needs copying.
- **New endpoints** become tools automatically. An operation that shouldn't be
  a tool goes in `EXCLUDED_OPERATIONS` in `tools.py`.
