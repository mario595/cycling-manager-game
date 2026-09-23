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

Do all six steps, in this order. Do not skip one because it looks unnecessary.

### 1. Read

In this order:

1. `specs/<slug>-plan.md` — the whole file. This is your instruction set.
2. `specs/<slug>.md` — the product spec, so you know what it is for.
3. `AGENTS.md` — the app table, the dependency direction, the principles.
4. The `README.md` of every app the plan touches.

### 2. Go to the ticket's worktree

**The worktree already exists.** `/product-spec` created it, and the spec and
the plan are committed on its branch. Reuse it — do not create a second one, and
do not work from the main checkout.

```bash
cd .claude/worktrees/<slug>        # <slug> from specs/<slug>-plan.md
```

Only if it is genuinely missing — an older ticket, or a plan written before this
convention — create it as *The ticket's worktree* in
`.claude/ticket-workflow.md` describes, from an up-to-date master. These skills
are the project instruction that authorises a worktree.

Confirm you are where you think you are before touching anything:

```bash
pwd && git branch --show-current && git log --oneline -3
```

The log should show the spec and plan commits. If it does not, you are in the
wrong place — **stop and ask** rather than starting work on master.

Everything from here runs inside this worktree.

### 3. Start the database

```bash
docker compose up -d
```

Development uses PostgreSQL, and the tests need it. If it does not start, **stop
and ask**. Do not switch the settings to SQLite to get around it.

### 4. The test command

`.venv/` is gitignored, so **a worktree has no virtualenv of its own**. Always
run Python with the main checkout's interpreter, from inside the worktree:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python -m pytest -q
```

For the rest of this document, `PYTEST` means that command.

**You do not have to do anything about other agents.** Each worktree gets its
own test database, named after the worktree, so a suite running in another
worktree at the same time cannot drop yours mid-run. `config/worktree.py` has
the scheme. Never set `POSTGRES_DB` to work around a database problem — that
opts you back into sharing.

### 5. Bring master in — before you write a line

Your branch may have been cut days ago, and other tickets have landed since.
Merge master **now**, not at the end. Conflicts resolved here are conflicts
against your own empty diff, which is the cheapest they will ever be; left until
the PR, you resolve them against a whole feature and risk having built on a base
that had already moved.

Follow **Bringing master in** below, then come back here.

### 6. Check the environment works

**Do not run the full suite here.** CI runs it on every push to master, so the
branch you just merged is green by construction. What CI cannot tell you is
whether *this machine* is set up: Postgres up on 5433, this worktree's database
created, the main checkout's interpreter resolving from inside a worktree.

Two quick commands prove all of that in seconds:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python scripts/dev_db.py
/home/mario/dev/cycling-manager/.venv/bin/python manage.py migrate
PYTEST race_engine
```

`migrate` exercises the interpreter, the settings, the connection and the
schema. `race_engine` is 51 plain-Python tests with no database, under a second,
so a failure there means something is wrong with the checkout itself rather than
with the database.

**If either fails, stop and ask.** Do not start work in an environment you have
not proved, and do not "fix" it by editing settings.

There is no baseline number to carry. Because master is green when you start,
the rule for the rest of this document is simply: **the suite must be green**.
Any failure after this point is yours.

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

**It must be green.** You started from a green tree, so any failure is yours.
Fix it before going any further — do not carry a red suite into the next work
item, and do not tell yourself it was probably already broken.

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
- the **environment check failed** — migrations, the database, or the engine tests;
- the **database will not start**;
- doing what the plan says would **break a rule in `AGENTS.md`**;
- you need a **package that is not in `requirements.txt`**;
- you want to change **anything the plan does not mention**;
- the work item turns out to be **much bigger** than the plan suggests;
- a merge conflict with master is **semantic** — both sides changed the same
  behaviour in ways that cannot both be true. That is a design decision, not a
  merge.

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
- Never merge the pull request, and never merge your branch into master. (Merging master *into* your branch is required — see **Bringing master in**.)
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
4. **Bring master in again** — see below. You merged it before you started;
   master has probably moved since. Do this *before* the user tries it, so what
   they verify is what will actually merge.
   **This is a gate you may not skip before opening the PR: the branch must be
   conflict-free against latest master.**
5. **Leave it running for review** — see below.
6. **Open the PR, move the ticket, then tear the environment down.** Follow
   `.claude/ticket-workflow.md`: confirm in one line and wait for a yes, then
   push the branch and open the pull request, then set the board's Status field
   to **Implemented**. That file has the PR body template and the exact `gh`
   commands. Put the scenarios from step 5 into the PR body under **How to try
   it**.

   **The user's yes is the signal that they have finished trying it**, so it is
   also the signal to shut the environment down — see **Tearing it down** below.
   Do that only after the PR and the status move have both succeeded.

   **The PR must be linked to the issue, and must close it on merge.** This is
   not optional and not a formatting preference — it is how the ticket stops
   being open once the work lands. Two lines in the body do it, and the template
   in `.claude/ticket-workflow.md` has both:

   - `Implements #<N>.` at the top — the link a person reads.
   - `Closes #<N>` at the end — the keyword GitHub acts on.

   `Closes` is deliberate rather than a plain reference: the ticket sits at
   **Implemented** through review and testing, and merging to master is the last
   step, which closes it.

   **Then check that GitHub actually registered it**, because a typo in the
   number fails silently and you will not find out until a merged PR leaves the
   ticket open:

   ```bash
   gh pr view <n> --repo mario595/cycling-manager --json closingIssuesReferences
   ```

   That must list issue `<N>`. If it comes back empty, the keyword did not take
   — fix the body with `gh pr edit <n> --body-file ...` and check again. Do not
   move the ticket or tear anything down until it lists the issue.

   **Confirm the PR is conflict-free as GitHub sees it.** The merge in step 4
   proves the branch holds master's content, but GitHub recomputes conflicts
   against whatever master is now, and master may have moved since. `mergeable`
   must report `MERGEABLE` (not `CONFLICTING`), and `mergeStateStatus` `CLEAN`:

   ```bash
   gh pr view <n> --repo mario595/cycling-manager --json mergeable,mergeStateStatus
   ```

   If it comes back `CONFLICTING`, merge the new master in, re-run the suite and
   the migration check, push, and re-check. Never open a PR, report a PR, or move
   a ticket for a PR that GitHub reports as conflicting.
7. Report, briefly:
   - the pull request URL, and that the server and database are now shut down;
   - the scenarios, so they stay in the conversation as well as the PR;
   - the branch name;
   - which work items are done (and any that are not, and why);
   - tests added, and the suite's final state;
   - anything you had to stop and ask about;
   - anything you noticed that the plan did not cover.

**Do not merge the pull request. Do not delete the worktree.** Review and testing
happen on the PR, and the user merges it.

**If you stopped part-way** — a work item unfinished, a question unanswered, the
suite not green — do not start the server, do not open the PR and do not move the
ticket. Commit what is finished, say exactly where you got to, and stop.

---

## Bringing master in

**You do this twice**: once before you write any code, and once more before the
PR goes up, because master keeps moving while you work. Same procedure both
times.

Start by asking whether there is anything to merge at all:

```bash
git fetch origin
git log --oneline HEAD..origin/master
```

**Empty means master has not moved** — nothing to do, say so in a few words and
carry on. A worktree `/product-spec` created this morning is often already
current.

Otherwise merge:

```bash
git merge origin/master
```

### If it merges cleanly

Do not relax. **A clean git merge does not mean a clean codebase.** Run both
checks:

```bash
PYTEST
/home/mario/dev/cycling-manager/.venv/bin/python manage.py makemigrations --check --dry-run
```

The migration check is the one that catches what git cannot see. If master added
a migration and so did you, git merges the two files without complaint because
they are different files — but Django now has **two leaf nodes in the migration
graph**, and `migrate` refuses to run. Git was never going to notice: nothing
conflicted textually.

The fix is a merge migration, never hand-editing either file:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python manage.py makemigrations --merge
```

Commit that with the merge.

### If there are conflicts

Resolve them, with these rules:

- **Read both sides and understand what each was doing** before you choose. A
  conflict means two people changed the same thing for two different reasons;
  the resolution usually keeps both intentions, not one of them.
- **`--ours` and `--theirs` are almost always wrong** for a source file. They
  discard one side's work silently. Use them only for a generated file that is
  about to be regenerated anyway.
- **Never resolve a conflict by deleting a test.** If master added a test your
  branch breaks, your branch is what is wrong.
- **If the conflict is semantic** — both sides changed the same behaviour in
  ways that cannot both be true — **stop and ask**. That is a design question,
  not a merge.

Then the same two checks as above, plus a read of the merge diff:

```bash
git diff origin/master...HEAD
```

The suite must be green before you go any further. A failure now is the merge's
doing, and it is yours to fix.

### Then

Commit the merge, and re-apply migrations to this worktree's database before the
user looks at it, since master may have brought new ones:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python manage.py migrate
```

### Once more, just before you push

Master can move again while the user is clicking through. When you have the
go-ahead, check a last time and merge again if it has:

```bash
git fetch origin && git log --oneline HEAD..origin/master
```

Empty means nothing moved. If it is not empty, merge, re-run the suite and the
migration check, and say so — briefly — rather than pushing something you have
not tested. After the push, confirm GitHub agrees the PR is conflict-free
(`gh pr view <n> --json mergeable` → `MERGEABLE`); a branch that merged cleanly
locally can still be reported `CONFLICTING` once master has moved.

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
seed this worktree's database — see **AGENTS.md, *Seeding a world for testing***
for the canonical list. The usual order:

```bash
manage.py seed_user             # demo account: test@mail.com / 123456789
manage.py seed_teams --claim-for test@mail.com   # one team for the demo account, the rest claimable
manage.py seed_trainers         # hireable trainers in the pool
manage.py load_season seasons/season-1.example.json   # season 1 and its races
```

Run the ones the feature touches (`seed_user` is idempotent; the others only
add). If the feature needs data none of them provide, **extend the relevant
domain's seed command and add it to AGENTS.md** — do not invent data by hand in
the database. World-clock features additionally need
`mock_clock set <season start>` and a `tick`.

- **Logging in? Use the demo account `test@mail.com` / `123456789`.** Do not
  invent credentials.

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
created; and the numbered scenarios.

Then say that you will shut the server and its database down when they give the
go-ahead for the PR, and **wait**. Do not tear anything down before that: they
are about to click through it.

Note the server's PID from the background job now, so you can stop it later
without hunting for it.

---

## Tearing it down

Run this **after** the PR is open and the ticket has moved, not before. The
user's go-ahead means they have finished trying it by hand.

```bash
kill <the runserver PID>                       # the server you started
/home/mario/dev/cycling-manager/.venv/bin/python scripts/dev_db.py --drop
```

`--drop` removes this worktree's development database and its test database. It
refuses to run in the main checkout, so it cannot take the user's own database
with it.

Then confirm the port is actually free, so nothing is left holding it:

```bash
curl -sS -o /dev/null -m 2 "http://127.0.0.1:$PORT/" && echo "STILL UP" || echo "down"
```

What **not** to touch:

- **Postgres itself.** `docker compose down` stops it for every other worktree,
  and another agent is probably mid-run.
- **The worktree and the branch.** Review happens on the PR, and the reviewer
  may want the branch. Deleting them is the user's call.
- **Anything in the main checkout.**

If the PR step failed, or the user has not said yes, **leave everything
running**. A half-finished handoff with the environment torn down leaves them
nothing to look at.

Say in one line what you stopped and dropped. If they want it back later, it is
`scripts/dev_db.py`, `manage.py migrate`, the seed step, and `runserver` again —
the same four commands as before.
