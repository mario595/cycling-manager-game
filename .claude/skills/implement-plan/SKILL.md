---
name: implement-plan
description: Implement an agreed implementation plan from specs/<slug>-plan.md — write the code and its tests, work item by work item, keeping the full test suite green. Use when asked to build, implement or code a plan or a ticket that already has one ("implement specs/game-clock-plan.md", "build #6", "start on the game clock"). Works in a git worktree and commits each work item separately.
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
- Never merge the worktree back yourself.
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
4. Report, briefly:
   - the branch name and where the worktree is;
   - which work items are done (and any that are not, and why);
   - tests added, and the baseline count versus the final count;
   - anything you had to stop and ask about;
   - anything you noticed that the plan did not cover.

**Leave the merge to the user.** Do not merge, do not push, do not delete the
worktree.
