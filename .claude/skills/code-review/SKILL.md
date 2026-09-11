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

PYTEST                                                 # the suite
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
4. **Architecture and conventions.**
5. **Clarity.**

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
- **N+1 queries.** A loop over a queryset touching a related object, or a
  serializer with a nested field, and no `select_related` / `prefetch_related`.
- **A query inside a loop** that could be one query outside it.
- **`len(qs)` where `.count()` is meant**, or truthiness where `.exists()` is.
- **No `transaction.atomic`** where several writes must land together — or
  `select_for_update()` outside a transaction, where it silently does nothing.
- **A field filtered on constantly with no index**, or a uniqueness rule enforced
  in Python instead of by a constraint.
- **`.get()` with no `DoesNotExist` handling** on a path where absence is normal.
- **Bare `except:` or `except Exception:`** that swallows and continues.
- **Business logic in a view or a serializer** instead of a service.
- **Signals** used where a direct service call would be clearer and traceable.

### Django REST Framework

- A list endpoint with no pagination.
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
