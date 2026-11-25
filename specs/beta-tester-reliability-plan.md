# Beta testers that probe, report and visit on time: implementation plan

**Spec:** `specs/beta-tester-reliability.md` · **Issues:** #159, #160 · **Status:** proposed
**Apps touched:** `beta_agents/` (not a Django app), `deploy/crontab`, `.github/workflows/beta-agents.yml`

## Context you need

`beta_agents/` is a stdlib-only package that plays the staging world over HTTP
(`beta_agents/README.md`). It imports nothing from the game and the game imports
nothing from it. That stays true: nothing here touches a Django app.

Today a visit is `python -m beta_agents visit <tester>`: `__main__._visit` builds a
`GameAPI`, a `Toolbox` from the live schema and a `ChatClient`, then
`visit.run_visit` runs the tool loop until the model calls `finish_visit`, and
appends a `## <UTC time>` section to `diaries/<tester>.md` with a stats footer.
`prompt.py` holds the instructions. `testers.py` holds the five personas and the
dueness rule (due once `period - 30 min` has passed since the last diary stamp).
The workflow runs at minute 17 of every hour on GitHub's cron, which in practice
fires about once every 6 to 10 hours (spec, *Why this exists*).

The staging machine runs `supercronic` over `deploy/crontab` (the tick and the
nightly backup). The image is built with `COPY . .`, so `beta_agents/` is
already on the machine at `/app/beta_agents`.

The repository is **private**, so Actions minutes are limited. That is why the
machine checks dueness before it dispatches (decision 2).

## Goal

1. The staging machine checks hourly whether a tester is due, reading the
   diaries from the `beta-diaries` branch, and if so dispatches the workflow. It
   does nothing without its token.
2. A dispatched or scheduled run visits whoever is due, and respects the pause.
3. Each visit opens with a harness-taken reading of the team and the changes
   since the last one, saved in the diary for next time.
4. Regular testers get a rotating focus area and are pushed back once on an
   early finish. Every entry must carry a critical observation.
5. The diary footer shows the focus and the hours since the previous visit.

## Design decisions (settled)

1. **The dispatcher lives in `beta_agents`, as `python -m beta_agents dispatch`.**
   It needs the dueness rule, which lives in `testers.py`, so putting it
   anywhere else would duplicate the rule. `deploy/crontab` only calls it. Do
   not write it as a shell `curl` in `deploy/`: the dueness check would have to
   be reimplemented in shell.
2. **Dispatch only when someone is due** (load-bearing). An hourly dispatch that
   finds nobody due still costs a billed minute of Actions on a private repo,
   which is about 720 wasted minutes a month. The dispatcher reads each
   tester's diary from GitHub's contents API
   (`GET /repos/{repo}/contents/diaries/{slug}.md?ref=beta-diaries`, with
   `Accept: application/vnd.github.raw`), takes the last stamp with the same
   `STAMP` regex as `Diary`, and calls `testers.due`. A 404 means no diary, so
   the tester is due. Any other failure exits non-zero with a message, which
   supercronic logs. It never raises into the tick: they are separate cron lines.
3. **Gated by `BETA_DISPATCH_TOKEN`.** If it is unset, the command prints one line
   and exits 0. Production and local machines never set it. The token is a
   fine-grained PAT on `mario595/cycling-manager` only, with **Actions:
   read and write** and **Contents: read**. The repo comes from
   `BETA_DISPATCH_REPO` (default `mario595/cycling-manager`), and the ref from
   `BETA_DISPATCH_REF` (default `master`).
4. **The dispatch says "due", not a tester.** The workflow's `tester` input
   becomes a choice whose first option and default is `due`. In the job, `due`
   means "run `python -m beta_agents due`", which is today's scheduled
   behaviour. The machine dispatches `{"ref": "master", "inputs": {"tester": "due"}}`.
5. **Pause is honoured for `due` dispatches.** The job condition becomes
   `vars.BETA_AGENTS_ENABLED == 'true' || (github.event_name == 'workflow_dispatch' && inputs.tester != 'due')`.
   So a named manual run still works while paused, as the README promises, but
   the machine's runs are skipped. A skipped job is not billed.
6. **GitHub's cron stays** as the backup. A run started by either trigger
   while another is queued waits on the existing `concurrency` group and then
   finds nobody due. Do not add a "check for running workflows" step: the
   duplicate is rare and costs one minute.
7. **The machine's cron line runs at minute 5** (`5 * * * *`), away from GitHub's
   minute 17, so the two rarely queue behind each other.
8. **The reading is taken by the harness, not the model**, with five GETs
   through the tester's own `GameAPI`: `/api/accounts/me/`,
   `/api/economy/finances/`, `/api/riders/`, `/api/competitions/standings/`,
   `/api/schedule/position/`. They cost no model calls. Each part is read
   independently. A non-200 status or an unreachable server for one part
   records `{"error": "<status and short body>"}` for that part and goes on.
   With no team (`team: null`), only `me` and `position` are read.
9. **The reading is stored in the diary entry as one HTML comment line**:
   `<!-- reading: {json} -->`, written just before the footer. GitHub's
   Markdown hides it, the next visit parses it, and no second file is needed.
   `Diary.last_reading()` returns the parsed JSON from the newest entry that
   has one, or None. The comparison only uses the **immediately previous**
   entry's reading. If the previous entry has none (an entry from before this
   change, or a harness-written entry from a failed visit), there is no
   comparison. Do not search further back: changes over two visits read as one.
10. **What a reading holds** (all from fields the API already ships):
    `team` (`{id, code, name}` or null), `season`, `week`, `state`, `balance`,
    `weekly_wage_bill`, `fanbase`, `riders` (`{str(id): name}`), `rank` and
    `points` (the row of the league table whose `team.id` is ours, or null).
11. **The change list** (`snapshot.describe_changes(previous, current)`) is plain
    lines: season/week moved, balance from → to with the signed difference,
    wage bill, fanbase, rank and points, roster count with "joined: …" and
    "left: …" names. If the team ids differ, one line says the team changed and
    nothing else is compared. An errored part on either side says
    "<part> could not be read" instead.
12. **Focus areas** are a fixed tuple in `prompt.py`: `finances`, `roster`,
    `market` (auctions and free agents), `racing` (calendar, squads, results),
    `development` (the development squad), `staff_and_sponsors`. Each has a
    two- or three-sentence instruction naming what to cross-check. The focus for
    a visit is `FOCUS_AREAS[entry_count % len(FOCUS_AREAS)]`, where
    `entry_count` is the number of entries in the diary before this visit.
    It's deterministic, so it's testable, and it rotates evenly. **Casual gets
    no focus** (`Tester.probes = False`).
13. **Early-finish pushback**: `Tester.min_tool_calls` is 12 for the regular
    four and 0 for casual. When `finish_visit` arrives and the visit's tool
    calls so far (not counting this `finish_visit`) are below the minimum, and
    the visit has not been pushed back yet, the tool result is
    `{"saved": false, "error": "<keep going on your focus area>"}` and the loop
    continues. The second `finish_visit` always saves. The step cap still holds.
14. **Critical observation pushback**: the diary entry must contain the words
    `Critical observation` (case-insensitive). If not, and this pushback has not
    happened yet, the result is `{"saved": false, "error": "..."}` asking for one.
    The pushbacks are counted separately, so a visit can hit both once. Casual
    is not exempt from this one: the spec asks for it in every entry.
15. **Hours since the previous visit** comes from `diary.last_visit_at()` read
    before the append. The footer becomes
    `_Visit stats: 14 tool calls, 1 report filed, focus: market, 8.1 h since the last visit._`.
    It leaves out the focus for casual and the hours on a first visit.
16. **Call budget.** Twelve tool calls is usually 8 to 12 model calls, since the
    model often batches. Four regulars at three visits a day, plus casual, at
    a 30-call cap is at most 390 model calls a day, inside 500. Leave
    `BETA_MAX_STEPS` at 30.

## `beta_agents/snapshot.py` (new)

```python
def take(api: GameAPI) -> dict
def describe_changes(previous: dict | None, current: dict) -> list[str]
def describe_current(current: dict) -> list[str]   # for a visit with nothing to compare with
```

## `beta_agents/diary.py`

- `entry_count() -> int`
- `last_reading() -> dict | None`: the newest entry's `<!-- reading: … -->`,
  only if the **newest** entry has one (decision 9).
- `append(entry, at=None, reading=None)`: writes the comment line when a reading
  is given. The comment must survive the heading-escaping in `append`, which it
  does because it does not start with `## `.

## `beta_agents/testers.py`

`Tester` gains `min_tool_calls: int = 12` and `probes: bool = True`. Casual sets
`min_tool_calls=0, probes=False`.

## `beta_agents/prompt.py`

- `FOCUS_AREAS: tuple[tuple[str, str], ...]` and `focus_for(tester, entry_count) -> tuple[str, str] | None`.
- `ROLE` and `REPORTING` gain the reporting bar: a dismissed report costs
  nothing, use `looks_wrong` for what you can't explain, and three visits
  without a report means you are not looking hard enough.
- `VISIT` step 3 becomes "account for every change the harness listed, using
  the ledger, results and your diary, and report any you can't explain". A new
  step tells the tester to spend the rest of the visit on its focus area. The
  diary instructions require a line starting `Critical observation:`, and say
  "everything is fine" doesn't count.
- `opening_message(diary_entries, now_utc, changes: list[str], focus, hours_since)`:
  adds a `## The team since your last visit (read by the harness)` section and a
  `## Your focus this visit` section.

## `beta_agents/visit.py`

`run_visit(..., reading: dict | None = None)`. If a reading is given, it
computes the changes against `diary.last_reading()` and the focus from
`diary.entry_count()`, then puts them in the opening message. It applies
decisions 13 and 14, and passes `reading` to `diary.append`. `VisitOutcome`
gains `focus`, `hours_since` and `pushbacks`.

## `beta_agents/__main__.py`

- `_visit` calls `snapshot.take(api)` after the schema succeeds and passes it to
  `run_visit`.
- New `dispatch` subcommand: `--now` for trying it, plus the env variables in
  decision 3. Uses a small `github_get` / `github_post` pair over `urllib`, with
  an injectable transport for tests. It prints the due testers and whether it
  dispatched. A 204 from the dispatch is success.

## Workflow and crontab

- `.github/workflows/beta-agents.yml`: input `tester` has options
  `[due, youth, trader, money, racer, casual]`, default `due`. The condition
  follows decision 5. The run step treats an empty input or `due` as the due list.
- `deploy/crontab`: `5 * * * * cd /app && python -m beta_agents dispatch`, with
  a comment. It is a no-op without `BETA_DISPATCH_TOKEN`. CI's `supercronic -test`
  covers the syntax.

## Work items

### W1: `testers.py`, `diary.py`: tester fields, entry count, reading comment
Tests in `test_diary.py`: a reading round-trips; `last_reading` is None when the
newest entry has none even if an older one does; `entry_count`.

### W2: `snapshot.py`: take and describe
Tests in a new `test_snapshot.py`, using `FakeTransport`: a full reading; one
part failing gives an error part and the rest is read; with no team, only `me`
and `position` are read; the changes cover balance, roster joined/left, rank,
team changed, and an unreadable part.

### W3: `prompt.py`, `visit.py`: focus, change list, pushbacks, footer
Tests in `test_visit.py`: an early finish is pushed back once, then saves;
casual is not pushed back; a missing critical observation is pushed back once;
the footer carries the focus and the hours; the focus rotates with the entry
count; the opening message carries the changes. Update the existing tests whose
scripted visits finish after one or two calls: give them a tester or entry that
passes, rather than weakening the rule.

### W4: `__main__.py`: reading on visit, `dispatch` command
Tests in `test_cli.py`: no token means exit 0 with no requests; nobody due means
no dispatch; someone due (a 404 diary, or an old stamp) means one POST to
`/actions/workflows/beta-agents.yml/dispatches` with `{"ref":"master","inputs":{"tester":"due"}}`;
a non-204 means exit 1.

### W5: workflow, crontab, READMEs

## Execution order

W1 → W2 → W3 → W4 → W5. Each is one commit. The full `beta_agents` and `deploy`
tests run after each.

## Documentation update

- `beta_agents/README.md`: *What a visit does* (the reading, the focus, the
  pushbacks), the limits table (minimum tool calls, the one-time pushbacks),
  *The testers* (who gets a focus), *The workflow* (the machine's dispatcher,
  the `due` input, the pause), and *Setting it up* (creating the token, then
  `fly secrets set BETA_DISPATCH_TOKEN=…`).
- `deploy/README.md`: the env table gets `BETA_DISPATCH_TOKEN` (optional,
  staging only), and the crontab section gets the new line.
- `AGENTS.md`: the `beta_agents/` row mentions the machine-side dispatcher.

## Verification

- `.venv/bin/python -m pytest beta_agents deploy`.
- `python -m beta_agents dispatch --now …` with no token prints the no-op line.
- After merge and the secret being set, the Actions history shows
  `workflow_dispatch` runs about every 8 hours, and the diary footers read
  "~8 h since the last visit". **The likeliest failure** is a token lacking
  Contents: read, which shows as a 404 for every diary, so every tester is
  always due and the workflow is dispatched every hour. Guard it: if **every**
  diary read is a 404 and the branch itself can't be read
  (`GET /repos/{repo}/branches/beta-diaries` is not 200), exit 1 without
  dispatching.

## Risks

| Risk | Mitigation |
|---|---|
| Dispatching every hour from a bad token or wrong ref | The branch check in *Verification*. Dispatch only when due. |
| Pushback loops eat the step budget | Each pushback happens at most once a visit. The step cap holds. |
| Pushbacks breaking scripted tests by accident | Update the tests to satisfy the rule. Do not add a flag that turns the rule off. |
| The reading changing the model's behaviour in a bad way, e.g. it reports every balance drop | That is fine: triage is cheap (spec). |
| The machine's cron failing affects the tick | It's a separate cron line. supercronic runs jobs independently. |

## Open questions

None.
