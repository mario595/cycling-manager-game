# CI: run tests and enforce a coverage threshold — Implementation Plan

**Spec:** `specs/archive/ci-test-and-coverage.md` · **Issue:** #80 · **Status:** implemented
**Apps touched:** none. New files: `.github/workflows/ci.yml` (new), `.coveragerc` (new), `requirements.txt`, `README.md`, `AGENTS.md`, `config/settings/dev.py`

## Context you need

This repository has **no CI at all** — `.github/` does not exist. Nothing here
changes application code; the whole change is one workflow file, one coverage
config, one dependency line, and documentation.

What the workflow has to reproduce is what a developer runs by hand today:

```bash
docker compose up -d                        # Postgres 16 on host port 5433
.venv/bin/python -m pytest                  # 398 tests, ~2.5-4 min
cd frontend && npm run lint && npm run test && npm run build
```

**Also verified during planning: the backend suite's 2.5–4 minute runtime is
almost entirely password hashing, not database or fixture cost.** Every test
that creates a `User` — directly, or via a fixture that does — pays Django's
default PBKDF2 hasher cost, measured at **~1.8 seconds for one
`create_user()` call**. `teams/tests/test_services.py`'s `user` fixture and
`accounts/tests.py`'s login tests are the biggest payers. Switching the test
settings to `MD5PasswordHasher` (Django's own documented recommendation for
test suites — insecure by design, fine for throwaway test data, never used in
production) measured at **163s → 15s, all 398 tests still passing**. This is
now W1 below, ahead of the CI workflow itself, so the workflow is fast from
its first run rather than needing a follow-up.

Four facts about this repo that the workflow must respect, all verified:

1. **The database port is 5433, not 5432.** `config/settings/base.py` defaults
   `POSTGRES_PORT` to `"5433"` because `docker-compose.yml` maps the container's
   5432 to the host's 5433 to avoid clashing with a natively installed Postgres.
   A GitHub Actions service container has no such clash, so CI will map 5432 and
   **must set `POSTGRES_PORT=5432` explicitly** — inheriting the default silently
   points at nothing. This is the single likeliest thing to get wrong.
2. **Tests run under `config.settings.dev`,** set by `DJANGO_SETTINGS_MODULE` in
   `pyproject.toml`'s `[tool.pytest.ini_options]`. `dev.py` imports
   `config/worktree.py` and derives the database name from the checkout
   directory. In CI the checkout is *not* under a `worktrees/` parent, so
   `worktree_name()` returns `None` and the names are the plain
   `cycling_manager` / `test_cycling_manager`. No override needed — but the
   service container must therefore create a database named `cycling_manager`
   with user/password `cycling`/`cycling`, matching `base.py`'s defaults.
3. **`race_engine/` needs no database.** Verified: its 51 tests pass in **0.47s**
   with `POSTGRES_PORT` pointed at a dead port. `core/` has no tests at all. So
   the DB-free backend slice is exactly `race_engine`.
4. **The frontend has a committed `package-lock.json`,** so `npm ci` is available
   and correct. There is no `.nvmrc`; local Node is v20.

Relevant repo rules (`AGENTS.md`): Postgres everywhere; tests are pytest run via
`.venv/bin/python -m pytest`; `race_engine/` imports nothing from Django. None of
the app-dependency rules apply — this change touches no app.

## Goal

When this is done:

1. Opening a pull request, or pushing to `master`, runs the tests automatically.
2. Two jobs run in parallel: a fast one with no database (`race_engine` +
   frontend lint/test/build), and a backend one with Postgres 16 (the Django
   suite) — which now finishes in ~15s instead of ~3 minutes.
3. The backend job measures coverage with migrations, tests, settings,
   `manage.py` and `race_player/` excluded, and **fails below 85%**.
4. The result is visible as a check on the pull request. It does not block merge
   — branch protection is unavailable on this plan.
5. `pytest-cov` is a declared dependency, and the coverage exclusions live in a
   committed config file that a local run uses too.
6. The Django test suite uses a fast password hasher, so both CI and local
   `pytest` runs benefit — not just CI.

## Design decisions (settled — implement these, do not substitute)

1. **Two jobs, not one, and not three.** `fast` (no services) and `backend` (with
   Postgres). The fast job gives a red X in well under a minute for a type error,
   lint failure or engine regression; the backend job takes ~3-4 minutes. Do
   **not** merge them into a single job "for simplicity" — the whole point of the
   split is that the 0.47s engine suite and the 5s frontend build should not wait
   behind a database container. Do **not** split the frontend into its own third
   job either: at ~7 seconds total it does not justify a second runner spin-up,
   and it needs no database, so it belongs with `race_engine`.

2. **`POSTGRES_PORT=5432` is set explicitly as a job-level env var.** Load-bearing.
   `base.py` defaults it to 5433 for local Docker reasons that do not apply to a
   service container. Omitting it produces a connection failure that looks like a
   broken service container and wastes an afternoon.

3. **The service container is `postgres:16-alpine`** — the exact image pinned in
   `docker-compose.yml`, whose comment already says it is pinned so "every machine
   **and CI run** gets the same Postgres". Use `POSTGRES_DB: cycling_manager`,
   `POSTGRES_USER: cycling`, `POSTGRES_PASSWORD: cycling` to match `base.py`'s
   defaults, so no database env overrides beyond the port are needed.

4. **Health-check the service container with `pg_isready` and `--health-*`
   options.** Load-bearing. Without it the job starts `pytest` before Postgres
   accepts connections and fails intermittently — the worst possible CI failure
   mode, because it trains people to re-run rather than read. `docker-compose.yml`
   already uses `pg_isready -U cycling -d cycling_manager`; mirror it.

5. **Coverage config lives in a committed `.coveragerc`, not in the workflow's
   command line.** The exclusions are a property of the project, not of CI: a
   developer running coverage locally should get the same number CI does. Do
   **not** put `--cov-config` inline flags in `ci.yml` and leave local runs
   measuring something different.

6. **The threshold is enforced with `--cov-fail-under=85`,** passed on the command
   line in the workflow rather than baked into `.coveragerc`. Rationale: the
   *exclusions* are a project property (hence the file), but the *gate* is a CI
   policy — a developer running coverage locally to explore should see the number
   without the command exiting non-zero. Current coverage under these exclusions
   is **89%**, so there are four points of headroom.

7. **Do not add `coverage` and `pytest-cov` both.** `pytest-cov` pulls
   `coverage` in. Add only `pytest-cov>=5` to `requirements.txt` under the
   existing `# Dev / test` heading.

8. **Triggers are `pull_request` and `push` to `master` only.** As decided in the
   spec, to conserve Actions minutes against an agent workflow that pushes to
   feature branches repeatedly. Do **not** add `workflow_dispatch` "just in case"
   — it is unused surface; add it the day someone wants it.

9. **`npm ci`, not `npm install`.** A lockfile is committed; `ci` respects it
   exactly and fails if `package.json` and the lock have drifted, which is a
   thing worth failing on.

10. **Use `actions/setup-python` with `3.12` and `actions/setup-node` with `20`,**
    both with built-in dependency caching (`cache: 'pip'` / `cache: 'npm'`).
    `.python-version` pins `3.12.11`; setup-python can read it via
    `python-version-file`, which is better than duplicating the number — use
    that. Node has no pinned file, so `20` is stated directly.

11. **No `.venv` in CI.** Locally the commands are `.venv/bin/python -m pytest`;
    in CI `setup-python` provides the interpreter directly, so it is
    `python -m pytest`. Do not try to recreate a `.venv` — it buys nothing on a
    disposable runner.

12. **`race_player/` is excluded from coverage but its tests, if any, are not
    run separately.** It is not in `pyproject.toml`'s `testpaths`, so pytest
    never collects it today. Leave that as-is.

13. **The fast password hasher is set in `config/settings/dev.py`, guarded so
    it can never reach production**, using the same pattern `dev.py` already
    uses for `AUTH_PASSWORD_VALIDATORS` a few lines above it (that override
    "has no way to leak into production" because `prod.py` imports only
    `base.py`, never `dev.py`). Do **not** create a separate `test.py`
    settings module for this — `pyproject.toml`'s `DJANGO_SETTINGS_MODULE` is
    already `config.settings.dev`, `manage.py` defaults to it too, and adding
    a third settings file for one line is more moving parts than the change
    needs. Do **not** gate it behind an environment variable — dev and test
    should always get the fast hasher; there is no scenario where a developer
    wants slow local test runs.

    ```python
    # config/settings/dev.py, placed near AUTH_PASSWORD_VALIDATORS
    #
    # Django's default hasher (PBKDF2) is deliberately slow — ~1.8s per
    # create_user() call — which is correct for production and pointless
    # for throwaway test/dev accounts. MD5PasswordHasher is Django's own
    # documented recommendation for speeding up tests. Like
    # AUTH_PASSWORD_VALIDATORS above, this only applies when
    # DJANGO_SETTINGS_MODULE points at this file — prod.py never imports
    # dev.py, so this has no way to reach a real deployment.
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    ```

## Data model

None. This feature adds no models, no migrations, and no application code.

## `.coveragerc` (new, repository root)

```ini
[run]
source = .
omit =
    */migrations/*
    */tests/*
    */test_*.py
    */tests.py
    manage.py
    config/settings/*
    config/worktree.py
    race_player/*
    scripts/*
    .venv/*
    */apps.py

[report]
precision = 0
show_missing = true
```

Notes on two entries that are not obvious:

- `*/tests.py` as well as `*/tests/*` — this repo uses **both** layouts.
  `racing/tests.py`, `accounts/tests.py` and `api/tests.py` are single files,
  while `world/`, `teams/`, `staff/` and others use a `tests/` package. Omitting
  only one pattern leaves several hundred test statements counted as covered
  source, which is what inflates the raw number from 89% to 93%.
- `*/apps.py` — Django app config classes, executed by the framework at startup,
  and meaningless to test.

`source = .` with omits (rather than listing every app) means a **new app is
covered automatically** the day it is created. Listing apps explicitly would mean
a new app silently contributes nothing to the number until someone remembers.

## `requirements.txt`

One line added under the existing `# Dev / test` section:

```
pytest-cov>=5
```

## `.github/workflows/ci.yml` (new)

Both jobs in one workflow file so a single check-group appears on the PR.

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [master]

jobs:
  fast:
    name: Engine and frontend
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version-file: .python-version
          cache: pip

      - run: pip install -r requirements.txt

      # No database needed: race_engine is plain Python (51 tests, <1s).
      - name: Engine tests
        run: python -m pytest race_engine

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - run: npm ci
        working-directory: frontend

      - run: npm run lint
        working-directory: frontend

      - run: npm run test
        working-directory: frontend

      # `build` is `tsc -b && vite build`, so this is the type check too.
      - run: npm run build
        working-directory: frontend

  backend:
    name: Django suite and coverage
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: cycling_manager
          POSTGRES_USER: cycling
          POSTGRES_PASSWORD: cycling
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U cycling -d cycling_manager"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

    env:
      # base.py defaults this to 5433 for local Docker; a service container
      # has no port clash, so it is the standard 5432 here. Without this the
      # suite cannot reach the database.
      POSTGRES_PORT: 5432

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version-file: .python-version
          cache: pip

      - run: pip install -r requirements.txt

      - name: Tests with coverage
        run: python -m pytest --cov --cov-report=term-missing --cov-fail-under=85
```

Why `--cov` with no argument: `.coveragerc`'s `source = .` supplies the target,
so the flag only needs to switch measurement on. Passing `--cov=.` as well is
harmless but redundant.

The `backend` job runs the **whole** `testpaths` list including `race_engine`,
which the fast job also ran. That duplication is deliberate and cheap (0.47s of a
3-minute job): it keeps the coverage number whole-repo, which decision 5 of the
spec requires, and avoids a second coverage-combining step.

## Work items

### W1 — `config/settings/dev.py`: fast password hasher for dev and test — **done**

Add `PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]` as
shown in decision 13, near the existing `AUTH_PASSWORD_VALIDATORS` override.

**Proves it:** time the suite before and after — the whole point of this item
is a measured number, not a plausible-sounding setting:

```bash
git stash          # temporarily remove the change
time .venv/bin/python -m pytest --reuse-db -q
git stash pop       # restore it
time .venv/bin/python -m pytest --reuse-db -q
```

Expect roughly **163s → 15s**. All 398 tests must still pass — this changes
password *hashing speed*, not authentication behaviour, so no test should
newly fail or newly pass. If any test's outcome changes, stop: something
depended on the specific hasher (unlikely, but check before proceeding).

This item is independent of coverage and the workflow — it speeds up every
local `pytest` run too, immediately, whether or not W2 ever lands.

### W2 — `.coveragerc` + `requirements.txt`: make coverage measurable and reproducible — **done**

Add `.coveragerc` exactly as above and `pytest-cov>=5` to `requirements.txt`.

**Proves it:** run locally and confirm the number matches what CI will see:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest --cov --cov-report=term
```

The TOTAL line must read **89%** (or higher if the suite has grown). If it reads
93%, the test-file omits are not matching — check that both `*/tests.py` and
`*/tests/*` are present. If it reads far lower, an omit is too aggressive.

This is the load-bearing item: **the threshold in W3 is only meaningful if this
number is right**, and it is the one an implementer is most likely to get subtly
wrong by omitting one of the two test layouts.

### W3 — `.github/workflows/ci.yml`: the workflow — **done**

Add the workflow file as above. Nothing else changes.

**Proves it:** cannot be proven locally — a workflow only runs on GitHub. It is
verified by opening the pull request for this work and watching both checks go
green (see Verification). Optionally validate the YAML parses first:

```bash
.venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"
```

(PyYAML is present transitively; if it is not, skip this — GitHub will report a
syntax error on push.)

### W4 — `README.md` and `AGENTS.md`: document it — **done**

See *Documentation update* below.

**Proves it:** read it back. No test.

## Execution order

**W1 → W2 → W3 → W4**, one commit each.

W1 first, and on its own: it is independent of everything else, has an
immediate local payoff, and — importantly — changes the coverage baseline's
*runtime* (not its percentage), so measuring coverage in W2 against a suite
that already runs in 15s rather than 3 minutes is the honest starting point
for everything after it.

W2 second because the threshold number is an input to W3: if actual coverage
turned out to be 80% rather than 89%, the 85% floor in the workflow would be
wrong and W3 would need different content. Measuring before writing the gate is
the point.

W3 third, alone, so that the PR which introduces CI is itself the first thing
CI runs on — the cleanest possible proof, and now a fast one.

W4 last, once the workflow's real behaviour is known, so the documentation
describes what happened rather than what was intended.

Stop and commit after each.

## Documentation update (required, not optional)

No app `README.md` changes — this touches no app.

**`README.md` (repository root)** — add a short **Continuous integration**
section: that a workflow runs on pull requests and pushes to `master`; that it is
split into a fast no-database job and a Postgres-backed job; that backend
coverage must stay at or above 85%; and — importantly — that **a red check does
not block merging**, because branch protection is unavailable on this plan, so
the discipline is manual. Include the local command to reproduce the coverage
number (`.venv/bin/python -m pytest --cov`).

**`AGENTS.md`** — the *Running it* section currently lists the four local
commands. Add one line noting that the same suite runs in CI on every pull
request with an 85% coverage floor, and point at `.github/workflows/ci.yml`. Keep
it to a line or two: `AGENTS.md` is explicitly an index, not a manual.

## Verification

Unit tests cannot verify a CI workflow; it is verified by running.

1. **Open the pull request for this branch.** Both checks — *Engine and frontend*
   and *Django suite and coverage* — must appear and go green.

2. **Confirm the fast job is actually fast, and that the backend job is too.**
   The fast job should finish in well under two minutes and must not be
   waiting on a database. The backend job, with W1's hasher change in place,
   should finish in well under a minute of actual test time (plus checkout
   and dependency install) — not the 2.5–4 minutes the suite took before.
   If the backend job is still slow, W1 did not land or did not take effect
   in this environment; check it before investigating anything else.

3. **Confirm the coverage gate can actually fail** — this is the check that
   matters most, because *a threshold that cannot fail proves nothing*. A
   workflow that reports 89% tells you nothing about whether `--cov-fail-under`
   is wired up. Prove it deliberately, on a throwaway commit:

   ```bash
   # temporarily raise the bar above current coverage
   sed -i 's/--cov-fail-under=85/--cov-fail-under=99/' .github/workflows/ci.yml
   git commit -am "TEMP: prove the coverage gate fails" && git push
   ```

   The backend check must go **red**, with `Required test coverage of 99% not
   reached`. Then revert that commit and confirm it goes green again. Do not skip
   this: it is the only evidence the gate is connected.

4. **Confirm the database is genuinely reachable and used**, not silently skipped.
   The backend job's output must show 398 passed (or more). A suite that
   collected 51 tests means only `race_engine` ran and the Django tests were
   silently excluded.

The likeliest failure mode is **the port**: `base.py` defaults `POSTGRES_PORT` to
5433 and the service container publishes 5432. Step 4 catches it — a wrong port
produces `connection refused` at the first database-touching test, not a subtle
wrong answer.

## Risks

| Risk | Mitigation |
|---|---|
| **`POSTGRES_PORT` inherited as 5433, service container on 5432 → every Django test errors.** The single most likely mistake. | Job-level `env: POSTGRES_PORT: 5432`, called out in decision 2 and checked by Verification step 4. |
| **The hasher change is placed behind an environment-variable guard, or in a settings module `pyproject.toml` doesn't actually select**, so it silently never applies and the suite stays slow. | W1's own verification step times the suite before and after and expects a specific, large delta (163s → 15s) — a no-op change is caught immediately, not assumed. |
| **A test asserts something about password-hash *format*** (e.g. checking a stored hash starts with `pbkdf2_sha256$`), which MD5PasswordHasher would break. Not found in this codebase, but worth naming. | W1's verification requires all 398 tests to still pass with no change in which tests pass or fail — any such test would fail immediately and visibly. |
| **Coverage omits miss one of the two test layouts** (`tests.py` vs `tests/`), inflating the number to ~93% so the 85% floor is trivially met. | W2 states the expected number (89%) and says explicitly what 93% means. Both patterns are in `.coveragerc`. |
| **`--cov-fail-under` not actually wired up**, so the gate silently never fails. | Verification step 3 deliberately raises the bar to 99% and requires a red check before reverting. |
| **Job starts before Postgres is accepting connections → flaky red builds.** | `--health-cmd pg_isready` with interval/timeout/retries, mirroring `docker-compose.yml`. |
| Implementer "simplifies" the two jobs into one, losing the fast feedback. | Decision 1 states the split is the point and names the rejected alternative. |
| Implementer recreates a `.venv` in CI out of habit, matching local commands. | Decision 11: `setup-python` provides the interpreter; commands are `python -m pytest`, not `.venv/bin/python -m pytest`. |
| Actions minutes consumed faster than expected by agent-driven branch pushes. | Triggers limited to `pull_request` and `push: [master]` (decision 8). Revisit if the free tier is strained. |
| A future contributor reads the green check as "merge is safe/blocked". | `README.md` states plainly that the check does not block merging. |

## Open questions

None. The spec's `Open questions` section is empty and nothing in the code
contradicted it.
