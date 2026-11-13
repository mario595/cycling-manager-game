# LLM beta testers — Implementation Plan

**Status:** implemented
**Spec:** `specs/archive/beta-agents.md`
**Issue:** #132

## Context you need

- `specs/archive/beta-agents.md`, the product decisions this plan builds.
- `world/STAGING_BRIEFING.md`, which goes into the prompt as it stands (the part
  after its `---` rule).
- The OpenAPI schema at `/api/schema/` (#130). Every operation has a verb
  `operationId` and a description in game terms. The tools are generated from it.
- `api/README.md`, *Tokens*: send `Authorization: Bearer <key>` and **never a
  cookie**, or writes need CSRF. 60 requests a minute per account.
- `deploy/README.md`: staging is the Fly app `velodra` at `https://velodra.fly.dev`.

## Goal

A tester can run one visit against any server with
`python -m beta_agents visit <tester>`, and a scheduled GitHub Actions workflow
runs the due testers every hour, keeping each one's diary on the
`beta-diaries` branch.

## Design decisions (settled — implement these, do not substitute)

1. **Not a Django app.** `beta_agents/` is a plain Python package beside the
   apps. It imports nothing from the game, and talks to it only over HTTP, as
   any player's client would. It isn't in `INSTALLED_APPS`, and the dependency
   graph in `AGENTS.md` doesn't change.
2. **No new dependencies.** HTTP goes through `urllib.request`, from the
   standard library, for the game API and the model alike. Neither holds a
   cookie jar, so no cookie is ever sent. The workflow needs only a Python and
   the repo.
3. **The model is reached through an OpenAI-compatible chat completions
   endpoint.** Mistral, Groq, OpenRouter and Gemini's compatibility endpoint all
   speak it, so the provider is three settings: `BETA_LLM_BASE_URL` (default
   `https://api.mistral.ai/v1`), `BETA_LLM_MODEL` (default
   `mistral-small-latest`) and `BETA_LLM_API_KEY`. Moving to Claude would
   take a second small client class behind the same `chat()` call, which is
   not built now.
4. **One tool per API operation**, generated at the start of every visit from
   the live `/api/schema/`, so a new endpoint becomes a tool with no harness
   change. `$ref`s are inlined. Path parameters and request-body fields become
   the tool's top-level arguments. Left out: `login`, `logout`, `register`
   (session operations) and `get_race_log` (a large binary replay).
5. **Two harness tools beside them.** `finish_visit(diary_entry)` ends the
   visit and is the only way to write the diary. `report_a_problem` is the
   API's own operation, but the harness counts the calls and refuses a fourth
   in one visit with a tool error, so the cap holds whatever the model does.
6. **A visit is bounded.** At most `BETA_MAX_STEPS` model calls (default 40). A
   tool result longer than 8,000 characters is cut, with a note saying so. If
   the model stops calling tools without finishing, it is asked once for its
   diary entry. If the cap is hit, the harness writes the entry itself,
   saying the visit was cut short.
7. **Pacing.** Model calls are spaced at least 1.2 s apart (the free tier
   allows about one a second). A `429` from either side is waited out using
   `Retry-After`, up to three times. After that, the call fails.
8. **Failure is a skipped visit.** If the schema can't be fetched, the key is
   refused, or the model errors after retries, the command exits non-zero
   before touching the diary, and the run log says why. A game API error
   inside a visit is not a failure: it goes back to the model as the tool's
   result, since a wrong answer may be exactly what should be reported.
9. **The diary** is `diaries/<tester>.md`, in a directory the caller names
   (`--diary-dir`). Entries are appended under a heading with the real UTC
   time. A visit reads the last 5 entries. The workflow checks the
   `beta-diaries` branch out into that directory and commits after each visit.
10. **The schedule is computed, not written in cron.** The workflow runs at
    minute 17 of every hour and asks `python -m beta_agents due`, which lists
    the testers due at the current UTC hour: tester *t* is due when
    `hour % period == offset`. Four testers have period 4 and offsets 0–3, so
    exactly one of them visits each hour. The minimal-effort tester has
    period 24 and offset 2. The testers in one run visit one after another,
    and a workflow `concurrency` group keeps two runs from overlapping.
11. **Pause** is the repository variable `BETA_AGENTS_ENABLED`. The scheduled
    job runs only when it is `true`. A manual `workflow_dispatch` run of one
    named tester ignores it, which allows a test visit while paused.
12. **Accounts.** `python -m beta_agents register <tester> --base-url ...`
    registers the tester's account through the normal register endpoint with
    a random password, which nobody needs afterwards, and prints the
    `issue_api_token` command for the operator to run on the server. The key
    goes into the GitHub secret `BETA_KEY_<TESTER>`. The tester claims its
    own team through the API on its first visit, which also exercises the
    claim path. No Django code changes.

## `beta_agents/` layout

| File | What it holds |
|---|---|
| `__main__.py` | The CLI: `visit`, `due`, `register`, `tools` (prints the generated tool list, for debugging). |
| `testers.py` | The five `Tester` records: slug, display name, email, period, offset, persona text. `due(hour)`. |
| `prompt.py` | Builds the system prompt: role as a beta tester, the persona, the reporting rules, `PLAYERS_GUIDE.md`, the staging briefing. |
| `PLAYERS_GUIDE.md` | The one-page player's guide, from player-facing rules only. |
| `game_api.py` | `GameAPI`: bearer requests without cookies, `429` handling, `schema()`, `call(method, path, body)`. |
| `tools.py` | OpenAPI to tools: `$ref` inlining, argument mapping, `execute(name, args)`. |
| `llm.py` | `ChatClient.chat(messages, tools)` for an OpenAI-compatible endpoint, with pacing and retries. |
| `visit.py` | `run_visit(tester, api, llm, diary)`: the loop, the caps and the outcome. |
| `diary.py` | Reads the last *n* entries and appends one. |
| `tests/` | Plain pytest with fake transports, no database. |

## Workflow `.github/workflows/beta-agents.yml`

- Triggers: `schedule: cron "17 * * * *"` and `workflow_dispatch` with an
  optional `tester` input.
- `concurrency: beta-agents`, with `cancel-in-progress: false`.
- Steps: check out master, check out (or create) the `beta-diaries` branch
  into `diary/`, set up Python 3.12, run `due` (or take the input), visit each
  tester with its key, then commit and push `diary/` if it changed.
- Permissions: `contents: write` (for the diary branch only).
- Secrets: `BETA_LLM_API_KEY` (the model provider's key) and `BETA_KEY_<TESTER>`. Variables:
  `BETA_AGENTS_ENABLED`, and optionally `BETA_BASE_URL` (default
  `https://velodra.fly.dev`) and `BETA_LLM_MODEL`.

## Work items

1. Package skeleton, `testers.py`, `due()`, and tests.
2. `game_api.py` and `tools.py`, with tests against a sample schema.
3. `llm.py`, with tests against a fake transport.
4. `diary.py`, `prompt.py`, `PLAYERS_GUIDE.md`, `visit.py`, with a scripted
   fake model in the tests: claim, act, report and finish, the report cap, the
   step cap, and the nudge for a diary entry.
5. CLI and workflow. Add `beta_agents` to `testpaths`.
6. A live visit against a local server with a real model, if a key is
   available, or with the scripted model otherwise.
7. Docs: `beta_agents/README.md` (the runbook), `AGENTS.md` table, and a
   pointer in `deploy/README.md`.

## Verification

- `pytest beta_agents` passes, and the full suite and coverage floor still hold.
- `python -m beta_agents tools --base-url http://localhost:8000` lists 38
  operation tools plus `finish_visit` against a local server seeded with
  `seed_world`.
- One visit against the local server claims a team, makes a squad pick, and
  writes a diary entry.

## Risks

- **Mistral's tool calling with 39 tools** may be shaky on the small model.
  The fallback is `mistral-medium-latest`, changed by a single variable.
- **Free-tier limits are unpublished.** A visit's tool definitions are about
  8K tokens a call, which is fine at the reported 500K tokens a minute.
- **Commits to `beta-diaries`** run about 26 a day. They're on their own
  branch, never merged, and never trigger CI (`ci.yml` runs on pull requests,
  `deploy.yml` on master).

## Open questions

None.
