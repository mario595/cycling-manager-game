---
name: code-review
model: opus
description: Review the pull request for a ticket — correctness, tests, conventions and architecture — then approve it and move the ticket to Code reviewed, or request changes. Use when asked to review a ticket, a PR or a branch ("review #6", "code review the game clock PR", "is this ready to merge"). Runs the tests, the linter and the type-check itself rather than judging the diff by eye.
---

# Code review

You review the pull request for a ticket. You decide whether it is fit to merge,
you say why, and you record the verdict on the PR.

**You do not change the code.** A reviewer who rewrites what they are judging
cannot judge it, and the author loses the chance to disagree. Report; let
`/implement-plan` or the author fix.

Your value is in the **judgement call**: separating what must be fixed from what
is merely your preference. A review that lists twenty nits and misses a missing
migration is a bad review.

---

## Step 1 — Find the PR and the intent

You are given a ticket — `/code-review #6`, a URL, or "review the game clock".

```bash
# the ticket
gh issue view <N> --repo mario595/cycling-manager \
  --json number,title,state,body,labels,url

# its PR
gh pr list --repo mario595/cycling-manager --state all --search "#<N>" \
  --json number,title,headRefName,url,isDraft,state
```

Do **not** use `gh issue view --comments` or bare `gh pr view` — see
`.claude/ticket-workflow.md` for why and for the REST fallback.

If more than one PR matches, or none does, **stop and ask**. Never guess which
branch is under review.

Then read what the change was supposed to do:

1. `specs/<slug>.md` — what the player was promised. `Out of scope` matters: work
   that appears here and was cut is a finding, not a bonus.
2. `specs/<slug>-plan.md` — the design that was agreed, and the work items.
3. `AGENTS.md` and the `README.md` of each app the diff touches.

**Review against the plan, not against how you would have built it.** A decision
the plan settled is not yours to reopen. If you think the plan itself is wrong,
say so separately and plainly — do not smuggle it in as a code comment.

## Step 2 — Run the checks

Review the branch as it actually behaves, in a scratch worktree so the user's
working copy is untouched:

```bash
git fetch origin
git worktree add .claude/worktrees/review-<N> origin/<branch> --detach
cd .claude/worktrees/review-<N>
```

A worktree has no `.venv`. Use the main checkout's, from inside the worktree —
`PYTEST` below means this:

```bash
/home/mario/dev/cycling-manager/.venv/bin/python -m pytest -q
```

Run all four. Each failure is a **blocking** finding:

```bash
docker compose up -d                                   # tests need Postgres

PYTEST --durations=10                                  # the suite, slowest tests shown
/home/mario/dev/cycling-manager/.venv/bin/python manage.py makemigrations --check --dry-run
cd frontend && npm run lint                            # oxlint
cd frontend && npm run build                           # tsc -b, then vite build
```

`makemigrations --check` is the one people forget: it exits non-zero when a model
changed and no migration was written. That bug is invisible in a diff and breaks
the next person's database.

Skip the frontend commands when the diff touches no frontend file. Never skip
the suite or the migration check.

Remove the worktree when you are done (`git worktree remove`).

## Step 3 — Read the diff

```bash
gh pr diff <n> --repo mario595/cycling-manager
```

Read every changed file. For anything you do not understand, open the
surrounding code — a diff hides as much as it shows.

Work through, in this order:

1. **Does it do what the spec promised?** Take the spec's `In scope` list and
   find each item in the code. An item with no code behind it is blocking.
2. **Is every new behaviour tested?** See below.
3. **Correctness and the stack pitfalls.** See the checklists.
4. **Performance**, wherever the cost grows with data. See below.
5. **Architecture and conventions.**
6. **Clarity.**

### Tests — check these specifically

Missing or fake tests are the most common real problem, and the easiest to miss
because a green suite looks like proof.

- Every new behaviour has a test. Walk the spec's `In scope` and the plan's
  `Rules and edge cases`; each should map to a test case.
- **Could each new test fail?** Mentally break the implementation and ask whether
  the assertion would notice. A test with no assertion, or one asserting only
  that a mock was called, proves nothing.
- Tests assert on **behaviour** — what the function returns or changes — not on
  internals.
- Edge cases the plan's `Risks` named are covered.
- No test was deleted, skipped, `xfail`ed or had its assertions weakened. Check
  the diff for removed test lines specifically; this is how a regression gets
  laundered into a green run.
- Django tests that touch the DB carry `@pytest.mark.django_db`.
- Nothing depends on real wall-clock time or unseeded randomness.

## Severity — the judgement call

Every finding gets one of three levels. Be honest about which.

**Blocking** — do not merge. Reserve it for:

- wrong behaviour, or a promised `In scope` item not delivered;
- data loss, corruption, or a migration that cannot be applied or reversed;
- a model change with no migration;
- new behaviour with no test, or a test that cannot fail;
- a deleted, skipped or weakened existing test;
- the suite, lint, type-check or migration check failing;
- an `AGENTS.md` architecture rule broken;
- a security problem: a secret in the repo, a missing permission check, an
  injection, user input trusted where it should not be;
- **an N+1, or a cost that grows superlinearly, on a path that will carry real
  data** — see Performance below for where the line sits;
- something that will be very expensive to undo once data exists.

**Should fix** — real, but the sky will not fall. A misleading name, duplication
that will bite the next change, an unhandled edge case that is currently
unreachable, an N+1 on a path that will grow, a test that is thinner than the
behaviour it covers.

**Nit** — preference. Formatting the linter does not catch, a name you would have
chosen differently, a comment that could be shorter. Prefix these `nit:`, say
each once, and **never block on one**.

Two rules that keep reviews honest:

- **If you find nothing blocking, say so and approve.** A reviewer who feels
  obliged to find something will invent something, and then nobody trusts the
  blocking ones. "This is clean" is a complete review.
- **More than about five *should fix* items is itself blocking.** Individually
  minor, collectively it means the change needs another pass.

---

## Pitfalls worth checking

Not a checklist to recite — the things that actually go wrong in this stack.

### Django and Python

- **Model changed, no migration.** Caught by the check above; look anyway.
- **Migration not reversible**, or a data migration with no reverse.
- **`null=True` on a text field.** Use `blank=True` and `""`; two empty values is
  a bug factory.
- **Mutable default** — `default=[]` or `default={}` on a field or argument. Use
  `list` / `dict` as callables.
- **Naive datetimes.** `datetime.now()` where `django.utils.timezone.now()` is
  meant. Especially dangerous in anything time-driven.
- **A uniqueness rule enforced in Python** instead of by a database constraint.
- **No `transaction.atomic`** where several writes must land together — or
  `select_for_update()` outside a transaction, where it silently does nothing.
- **`.get()` with no `DoesNotExist` handling** on a path where absence is normal.
- **Bare `except:` or `except Exception:`** that swallows and continues.
- **Business logic in a view or a serializer** instead of a service.
- **Signals** used where a direct service call would be clearer and traceable.

### Django REST Framework

- Permission classes left to the default when the endpoint is not public.
- A server-owned field writable because it is missing from `read_only_fields`.
- A serializer performing writes that belong in a service.

### React and TypeScript

- **`useEffect` dependency array wrong** — missing a dep, or an object/array
  literal recreated each render, which loops.
- **State that should be derived.** If it can be computed during render, it
  should not be in `useState` and synced by an effect.
- **A fetch in an effect with no cleanup**, racing an earlier one on fast
  navigation.
- **State initialised from props** and then never updated when they change.
- **Array index as `key`** in a list that reorders, filters or deletes.
- **`any`, or a `!` assertion, used to silence the compiler** rather than to
  state something true.
- **Optional chaining hiding real absent data.** `race_player` treats `team` and
  `role` as genuinely optional — check the fallback is deliberate, not `?.`
  sprinkled to stop a crash.
- A component doing fetching, layout and business logic at once.

### Performance

Performance is a review dimension in its own right, not an afterthought. But
judge it by **how the cost grows**, not by how it looks.

**The question to ask of every hot path: what multiplies?** A cost paid once is
not a performance problem however ugly. A cost paid per row, per rider, per tick
or per render is one, and it gets worse exactly when the game gets bigger.

**Blocking** when the cost scales with data on a path that will carry it:

- **An N+1 query.** A loop over a queryset that touches a related object, a
  serializer with a nested field, a template or view reaching across a relation
  — with no `select_related` (forward FK / one-to-one) or `prefetch_related`
  (reverse FK / many-to-many). One race with 16 riders hides it; a season does
  not.
- **A query inside a loop** that could be one query outside it, including a
  `.get()` per iteration and a `.save()` per row where a bulk operation exists
  (`bulk_create`, `bulk_update`, a single `update()`).
- **Loading a whole table to count, filter or check it in Python** — `len(qs)`
  for `.count()`, iterating to find one row instead of `.filter().first()`,
  truthiness instead of `.exists()`.
- **A missing index on a column that is filtered or ordered on** every time.
- **Work added inside the engine's per-tick loop** that is not needed per tick.
  The race engine runs one iteration per rider per second of race time, so a
  per-tick allocation or recomputation is multiplied by tens of thousands.
  Anything that can be hoisted out of the loop, or cached, should be — and note
  that `compute_base_speed`'s cache key is deliberately quantised, so a new
  unquantised key would blow the cache up rather than speed anything up.
- **An unbounded query on a growing table** — a list endpoint with no
  pagination, a report that reads the full history.

**Should fix** when the cost is real but bounded, or the path is not hot yet: an
extra query on a page that loads once, a list comprehension over a small fixed
set, a repeated computation that is cheap but obviously repeated.

**Nit** for micro-optimisation of code that runs once, or a rewrite whose only
argument is that it is faster in principle. Do not trade clarity for speed
nobody can measure.

**Prevention beats a comment.** When you find an N+1, the fix worth asking for is
usually the `select_related`/`prefetch_related` *plus* a test that pins the query
count — `pytest-django` is already installed and provides the
`django_assert_num_queries` fixture. A query-count test is the only thing that
stops the N+1 coming back on the next change.

#### React re-renders

`race_player` plays a race back tick by tick with many riders on screen, so
render cost here is real rather than theoretical.

- **A new object, array or function created during render and passed as a prop.**
  It is a different value every time, so every memoised child re-renders anyway
  and the memo is dead weight. Look for inline `{...}`, `[...]`, `() => ...` and
  `.map()`/`.filter()` results in JSX props.
- **A context value rebuilt each render** — every consumer re-renders on every
  parent render, however deep.
- **State lifted higher than it needs to be**, so a change that concerns one
  component re-renders a whole subtree. Playback state that ticks every frame is
  the case to watch.
- **Expensive work in the render body** rather than in `useMemo` — parsing,
  sorting, or recomputing a derived collection on every frame.
- **A memoised component whose props defeat the memo** (see the first bullet).
  `React.memo` on a component that always gets fresh props costs more than it
  saves; say so rather than praising the memo.
- **A long list rendered in full** where only a window is visible.
- Conversely: **do not demand `useMemo`/`useCallback` everywhere.** They cost
  something too. Ask for them where the child is memoised, the value is
  genuinely expensive, or the render happens per frame — otherwise it is a nit.

#### Judging without a profiler

There is no profiler wired up, so reason about it instead: state what multiplies,
by roughly how much, and on which path. "This adds one query per rider, so a
16-rider race result page goes from 2 queries to 18" is a finding. "This feels
slow" is not — leave it out.

If `race_engine/` changed, the repo has a regression harness worth running:
`python -m race_engine.audit --baseline audit_baseline.json`. A large swing in
runtime is a finding even when the results are unchanged.

### Tests

- No assertion; or asserting only that a mock was called.
- So heavily mocked that the test passes whatever the code does.
- Missing `@pytest.mark.django_db`.
- Order-dependent, or sharing mutable fixture state.
- Real `now()` or unseeded randomness — this repo cares about determinism.

### This repo specifically

- `race_engine/` importing anything from Django.
- Any module other than `racing/adapters.py` importing `race_engine`.
- An import that breaks the dependency direction in `AGENTS.md`.
- A new app with no `README.md`.
- A committed `.jsonl`, or a stored race log regenerated.
- Settings, `pyproject.toml` or a fixture changed in a way that makes a test pass
  rather than makes the code right.
- The plan's `Documentation update` section not done.

---

## Step 4 — Write the review

Confirm first: say in one line what you are about to post and which way the
verdict goes, and wait — as `.claude/ticket-workflow.md` sets out.

Body:

```markdown
## Verdict
<Approved | Changes requested> — one sentence on why.

## Checks
- Tests: <n passed, n failed>
- Migrations: <clean | missing for X>
- Lint: <clean | n problems>       (omit if no frontend changes)
- Type-check / build: <clean | …>  (omit if no frontend changes)

## Blocking
1. `path/to/file.py:42` — what is wrong, and what breaks because of it.
   (Omit the heading entirely if there are none.)

## Should fix
1. `path:line` — what and why.

## Nits
- nit: …

## What is good
One or two lines, where it is deserved. Not filler.
```

Point at a file and a line for every finding. A finding without a location is an
opinion.

Then post it:

```bash
# no blocking findings
gh pr review <n> --repo mario595/cycling-manager --approve --body-file <file>

# blocking findings
gh pr review <n> --repo mario595/cycling-manager --request-changes --body-file <file>
```

If `gh pr review` hits the Projects-classic error, use the REST fallback in
`.claude/ticket-workflow.md`.

## Step 5 — Move the ticket, or don't

**Approved** — move the ticket to **Code reviewed**, following
`.claude/ticket-workflow.md` step 3. Do not merge the PR; that is the user's.

**Changes requested** — the ticket **stays where it is**. Say in your report what
has to change before it can move.

Then report briefly: the verdict, the check results, how many findings at each
level, and whether the ticket moved.

---

## Stop and ask

- More than one PR matches the ticket, or none does.
- The PR is a draft — confirm it is meant to be reviewed.
- You cannot start Postgres, or the suite errors before the change is involved.
- The plan itself looks wrong, rather than the code.
- A finding sits genuinely on the line between blocking and should-fix and the
  answer changes the verdict. Say which way you lean.
