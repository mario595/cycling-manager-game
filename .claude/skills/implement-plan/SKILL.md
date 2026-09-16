---
name: implement-plan
description: Implement an agreed implementation plan from specs/<slug>-plan.md — write the code and its tests, work item by work item, keeping the full test suite green. Use when asked to build, implement or code a plan or a ticket that already has one ("implement specs/game-clock-plan.md", "build #6", "start on the game clock"). Works in a git worktree and commits each work item separately.
model: sonnet
---

# Implement a plan

You implement a plan that has already been agreed. The plan made the decisions.
Your job is to carry them out exactly, with tests, without breaking anything.

**Do not redesign anything.** If the plan looks wrong, stop and say so — see
[Stop and ask](#stop-and-ask). Do not quietly do something different.

Work on **one work item at a time**, in the plan's order. Finish it, test it,
commit it. Then start the next one.

---

## Before you start

Do all five steps. Do not skip one because it looks unnecessary.

### 1. Read

In this order:

1. `specs/<slug>-plan.md` — the whole file. This is your instruction set.
2. `specs/<slug>.md` — the product spec, so you know what it is for.
3. `AGENTS.md` — the app table, the dependency direction, the principles.
4. The `README.md` of every app the plan touches.

### 2. Start the database

```bash
docker compose up -d
```

Development uses PostgreSQL, and the tests need it. If it does not start, **stop
and ask**. Do not switch the settings to SQLite to get around it.

### 3. Record the baseline — before you change any file

```bash
.venv/bin/python -m pytest -q
```

Write down the result: how many passed, how many failed. That is your baseline.

**If anything fails now, stop and report it.** Do not start work in a red repo —
you will not be able to tell your breakage from the breakage that was already
there.

### 4. Make a worktree

This skill is the project instruction that authorises a worktree. Use the
`EnterWorktree` tool with the feature slug as the name (`game-clock`). If that
tool is not available:

```bash
git worktree add .claude/worktrees/<slug> -b <slug>
cd .claude/worktrees/<slug>
```

### 5. Work out the test command for the worktree

`.venv/` is gitignored, so **a fresh worktree has no virtualenv**. Use the main
checkout's one, from inside the worktree:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python -m pytest -q
```

Run it once now. It must match your baseline. If it errors, stop and ask.

For the rest of this document, `PYTEST` means that command.

**You do not have to do anything about other agents.** Each worktree gets its
own test database, named after the worktree, so a suite running in another
worktree at the same time cannot drop yours mid-run. `config/worktree.py` has
the scheme. Never set `POSTGRES_DB` to work around a database problem — that
opts you back into sharing.

---

## The loop

For each work item in the plan's **Execution order** — W1, then W2, and so on.
One at a time. Never two. Never skip ahead.

### a. Find an example to copy

**Before writing anything new, find the closest existing thing in the repo and
match it.**

| Writing a… | Open… |
|---|---|
| model | another app's `models.py` |
| service function | an existing service in the same or a neighbouring app |
| management command | an existing one |
| test | the test file closest to what you are testing |
| migration | the app's most recent migration |

Match their structure, naming, import order, docstring style and error handling.
**Do not invent a new pattern.** Consistency with the codebase matters more than
your preference.

If you cannot find anything similar, **stop and ask**.

### b. Write the code

Only what this work item says. Not the next one. Not something you noticed on the
way past.

### c. Write the tests

Every new behaviour gets a test. The plan names the test file and the test case —
use those names.

- Test **behaviour**, not internals. Call the public function; assert on what it
  returns or changes.
- Cover the edge cases named in the plan's *Rules and edge cases* and *Risks*.
  Those are there because someone expects them to break.
- **A test that would pass against an empty implementation is not a test.** Where
  you can, run the test before the code exists and watch it fail. If it passes,
  the test is wrong — fix the test.

### d. Run the new tests

```bash
PYTEST path/to/test_file.py
```

### e. Run the whole suite

```bash
PYTEST
```

Compare with the baseline. The count must be **the same or better**. Any test
that passed before and fails now is a regression **you** caused. Fix it before
going any further.

Three things you must not do to get green:

- Do not delete, skip or `xfail` an existing test.
- Do not change an existing test's assertions, unless the plan explicitly says
  that behaviour changes.
- Do not change settings, `pyproject.toml`, or fixtures to make a failure go away.

If a test fails and you do not understand why after one honest attempt, **stop and
ask**.

### f. Commit

```bash
git add -A
git commit -m "<one line, imperative, saying what changed>"
```

Match the style of the repo's existing commit messages (`git log --oneline -10`).
One work item, one commit. Never `--no-verify`, never `--force`.

### g. Tick it off

Mark the work item done in `specs/<slug>-plan.md` so a later session can see
where you got to. Include that edit in the same commit.

Then go back to **a.** with the next work item.

---

## Stop and ask

Stop, say plainly what you found, and wait for an answer. Do not guess, and do
not pick "the most likely" option.

Stop when:

- the plan names a file, function, field or test that **does not exist** or does
  not look the way the plan says it does;
- the plan can be read **two reasonable ways** and they lead to different code;
- you **cannot find an existing pattern** to copy;
- a test fails and you **do not understand why** after one honest attempt;
- the **baseline was not green**;
- the **database will not start**;
- doing what the plan says would **break a rule in `AGENTS.md`**;
- you need a **package that is not in `requirements.txt`**;
- you want to change **anything the plan does not mention**;
- the work item turns out to be **much bigger** than the plan suggests.

Asking costs one message. A wrong guess costs the whole work item, and sometimes
the ones after it.

When you ask, give: what you were doing, what you found, the two or three options
you can see, and which you would pick.

---

## Never

- Never write a `TODO` and move on. If you cannot do it, stop and ask.
- Never leave commented-out code, or dead code you added.
- Never add a dependency without asking.
- Never edit `specs/<slug>.md`, or change a decision in the plan.
- Never merge the pull request or the branch yourself.
- Never end a work item with the suite red.

---

## Code quality

Short rules. Follow all of them.

- **Follow the pattern already in the repo.** Consistency beats cleverness.
- **Names say what the thing is.** No abbreviations the repo does not already use.
- **A function does one thing.** If a block needs a comment to explain it, that
  block wants to be its own function with a name.
- **Comment *why*, never *what*.** The code says what.
- **No new abstraction for a single caller.** Write it straight; extract later if
  a second caller turns up.
- **Handle the error where you can do something about it.** Do not catch an
  exception just to re-raise it, and do not swallow one silently.
- **Keep functions pure where you can.** A function that only computes is far
  easier to test than one that also writes to the database.

## Architecture rules

These come from `AGENTS.md`. Check it rather than trusting this list — but these
are the ones that get broken:

- **Dependency direction is one-way.** `AGENTS.md` has the graph. Only `world/`
  and `api/` may import from everywhere, and nothing may import *them*.
- **`race_engine/` imports nothing from Django, ever.** `racing/adapters.py` is
  the only module allowed to import the engine.
- **Business logic goes in services, not in views or models.** Views translate
  HTTP; models hold data and the rules that belong to one row.
- **A new app gets a `README.md` in the same change**, plus `INSTALLED_APPS` and
  its first migration.
- **Race logs are records, not build output.** Never regenerate one to make
  something pass.

---

## When the plan is done

1. Run the full suite one last time. It must be green.
2. Do the plan's **Documentation update** section. It is not optional.
3. Commit that documentation change.
4. **Leave it running for review** — see below.
5. **Open the PR and move the ticket.** Follow `.claude/ticket-workflow.md`:
   confirm in one line and wait for a yes, then push the branch and open the pull
   request, then set the board's Status field to **Implemented**. That file has
   the PR body template and the exact `gh` commands. Put the scenarios from step
   4 into the PR body under **How to try it**.

   The PR body ends with `Closes #<N>`. That is deliberate — the ticket stays at
   **Implemented** through review and testing, and merging to master is the last
   step.
6. Report, briefly:
   - the URL the app is running on, and that you saw it respond;
   - the scenarios to try;
   - the pull request URL, and the branch name;
   - which work items are done (and any that are not, and why);
   - tests added, and the baseline count versus the final count;
   - anything you had to stop and ask about;
   - anything you noticed that the plan did not cover.

**Do not merge the pull request. Do not delete the worktree.** Review and testing
happen on the PR, and the user merges it.

**If you stopped part-way** — a work item unfinished, a question unanswered, the
suite not green — do not start the server, do not open the PR and do not move the
ticket. Commit what is finished, say exactly where you got to, and stop.

---

## Leaving it running for review

The user checks this by hand before it merges. Set it up so they can, and tell
them exactly what to try. Everything here runs **from inside the worktree**, so
what they see is the branch's code and not master's.

### 1. Database and migrations

```bash
docker compose up -d                                    # Postgres, host port 5433
/home/mario/dev/cycling-manager/.venv/bin/python scripts/dev_db.py   # this worktree's own database
/home/mario/dev/cycling-manager/.venv/bin/python manage.py migrate
```

`dev_db.py` creates the database for **this worktree** if it is not there yet.
`migrate` creates tables, not databases, so without it a fresh worktree fails
with "database ... does not exist", which reads like a misconfiguration rather
than a missing step.

Migrating matters too: your branch almost certainly added migrations, and
without it the app runs against the old schema and the feature looks broken.

The database is this worktree's alone, so seeding it cannot disturb another
agent's review, and the user's main checkout keeps its own data.

### 2. Give it something to look at

A feature with an empty database is not reviewable. Before starting the server,
make sure there is data to see.

- Check what already exists: `manage.py help` lists the project's own commands.
  There are already commands for setting a world up — `load_season`,
  `mock_clock`, `tick`. **Prefer an existing command to inventing data.**
- If you must create data, do it with a short script through `manage.py shell`,
  and say exactly what you created.
- **If logging in is needed, do not invent credentials.** Ask the user to run
  `manage.py createsuperuser`, or tell them which existing account to use.

### 3. Build the frontend, if the frontend changed

Django serves the built bundle from `frontend/dist/`, so without this the user
sees the *old* UI and reports a bug that is not there:

```bash
cd frontend && npm run build
```

Skip it when the diff touches no frontend file.

### 4. Start the server in the background

This worktree has its own port, so it does not fight another agent's server.
Ask for it rather than guessing:

```bash
PORT=$(/home/mario/dev/cycling-manager/.venv/bin/python -c \
  'from config.worktree import runserver_port; print(runserver_port())')

/home/mario/dev/cycling-manager/.venv/bin/python manage.py runserver "$PORT" \
  > /tmp/runserver-<slug>.log 2>&1 &
```

The port is derived from the worktree name, so it is the same every time and
the user can bookmark it.

Then **confirm it is actually up before you tell the user it is**:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:$PORT/"
```

Anything other than a 200 means read the log. **Never report a URL you have not
seen respond.**

Two worktrees can rarely hash to the same port. If the log says the address is
in use, step up by one and say which port you ended on. **Never kill whatever is
already there** — it is another agent's review server.

### 5. Write the scenarios

Give a short numbered list of things to try — **only the flows this ticket added
or changed**. Not a tour of the app, not a regression sweep.

Derive them from the spec's `In scope` and the plan's work items: every in-scope
item should either be reachable by a scenario, or you should say why it is not
visible from the outside.

Each scenario is a few lines:

1. **Do this** — the exact URL, click or command.
2. **You should see** — the observable result.
3. **Then this** — the edge case worth poking, where there is one.

The shape, for a registration ticket:

```
1. Register — http://127.0.0.1:<port>/register, any email and password.
   You should land on the dashboard, and the account shows in /admin/.
2. Log out. You should be back at sign-in, and the dashboard should now
   bounce you there too.
3. Log in again with the same details. Same dashboard, same team.
4. Register again with an email already used. The form should say so, and
   there should still be only one account.
```

Rules for the list:

- **Say what state to start from**, and start from a clean one where you can.
- **Include at least one unhappy path** — the validation failure, the empty
  list, the double submit. That is where hand-testing earns its keep; the happy
  path already has a unit test.
- **Name the URL.** "Go to the dashboard" is not a scenario.
- **If the change has no UI, say so and give the equivalent** — a `manage.py
  shell` snippet, a management command, or a `curl http://127.0.0.1:<port>/api/...`.
  A clock or engine ticket is tried with `mock_clock` and `tick`, not by
  clicking.
- **Name anything from the ticket you could not make reachable**, and why.

### 6. Hand it over

Tell the user, in this order: the URL and that you saw it respond; what data you
created; the numbered scenarios; and how to stop it when they are done —

```bash
kill %1                # or the PID from the log
```

Leave Postgres running — `docker compose down` would stop it for every other
worktree too, and another agent is probably using it.
