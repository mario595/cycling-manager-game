# CI: run tests and enforce a coverage threshold on every PR

**Status:** proposed
**Domain(s):** none — this is repo/developer infrastructure, not a game domain
**One-liner:** Every pull request and push to `master` automatically runs the full test suite, lint, and build, and fails if backend coverage drops below 85%.

## Why this exists

Right now the test suite only runs when someone remembers to run it. There is
no `.github/` workflow, so a broken branch can reach `master` unnoticed, and a
pull request opened by an agent — which is how most changes now land, via
`/implement-plan` — carries no evidence anyone verified it. The groundwork is
already in place: `docker-compose.yml` pins the same Postgres version CI would
need, and both the backend (`pytest`) and frontend (`vitest`, `oxlint`,
`tsc`+`vite`) already have working local commands. This ticket wires them into
something that runs automatically and reports pass/fail where a PR is reviewed.

## Player experience

None — this feature has no player-facing behaviour. It changes what a
developer (or an agent opening a PR) sees on GitHub: a pull request shows a
red or green check summarizing whether the backend tests, frontend tests,
lint, build, and coverage floor all passed.

## In scope

1. A workflow runs automatically on every pull request and on every push to
   `master` — not on pushes to other branches.
2. The workflow runs the backend test suite against the same Postgres version
   used in local development.
3. The workflow runs the frontend's lint, test, and build commands.
4. The workflow separates work that needs a database from work that doesn't,
   so a broken frontend build or a broken engine-only test is visible in
   under a minute rather than waiting behind the full backend suite.
5. The workflow measures backend test coverage, excluding migrations, test
   files, settings, the management entry point, and the standalone visualizer
   (none of these are meaningfully testable in a way coverage should reward
   or punish).
6. The workflow fails if that coverage number drops below 85%.
7. A failing check is visible on the pull request. It does not and cannot
   block merging — this repository has no branch protection available (see
   Rules and edge cases) — so failure is informative, not preventative.

## Out of scope

- **Deploying anything (CD).** There is no chosen hosting target yet, so
  there is nothing to deploy to. Its own ticket, once a host exists.
- **Blocking merges.** Not available on this repository (private, free
  plan). See Rules and edge cases for why, and why that's an acceptable
  trade-off for now.
- **Coverage reporting to a third-party service** (Codecov or similar). The
  threshold is enforced inside the workflow itself; nothing external is
  needed to see or act on the number.
- **A rising coverage target ("ratchet").** Discussed and rejected — see
  Decisions taken.
- **Making the repository public, or paying for a hosting tier that unlocks
  branch protection.** Both would enable blocking merges, but neither is
  justified by this ticket alone. Revisit if the project gains contributors
  or goes public for other reasons.
- **Speeding up the backend test suite.** It currently takes 2.5–4 minutes.
  Worth watching, not worth fixing pre-emptively. Deferred to its own ticket
  if it becomes a problem — see Deferred.
- **The stale `requirements.txt` comment the original ticket flagged.**
  Already corrected; nothing left to do.

## Rules and edge cases

- **The coverage floor is a fixed number, not a rising target.** It is set
  once, close to (but below) the coverage that exists today, and stays there
  unless a person deliberately revisits it. It exists to catch a PR that
  adds a meaningful chunk of untested code, not to pressure incremental
  improvement.
- **A failing check does not block a merge.** GitHub branch protection
  requires either a public repository or a paid tier; this repository is
  private on the free plan. The check is a visible signal on the pull
  request — for a solo developer, and especially for a PR an agent opened
  without a human having run the suite, that visibility is the point even
  without an enforcement mechanism.
- **The workflow triggers on pull requests and on pushes to `master` only** —
  not on every push to a feature branch. Actions minutes are finite even on
  the free tier, and an agent workflow that pushes repeatedly to a branch
  during development would burn through them for no benefit; the useful
  checkpoints are "a PR exists to review" and "something landed on master."
- **Degenerate case: a PR that only touches the frontend, or only the
  backend.** Both halves of the workflow still run — the threshold and the
  checks are not scoped per-change. This keeps the workflow simple; a
  smarter per-diff version is deferred (see Deferred in the original issue
  discussion — not carried into this spec's scope).

## Decisions taken

- **Coverage floor is 85%, fixed, not a ratchet.** Current honest coverage
  (excluding migrations, tests, settings, `manage.py`, `race_player/`) is
  89%. A ratchet exists to drag a low number up over time; there is no low
  number here, and a rising floor on a solo project can fail a PR that
  deletes a well-tested module for good reason. A fixed floor with headroom
  answers the same need without that failure mode.
- **What coverage excludes:** migrations, test files, `config/settings/`,
  `manage.py`, and `race_player/` (a standalone visualizer, not meaningfully
  testable the same way). Whole-repo coverage with these exclusions was
  chosen over per-app or per-diff coverage as the frugal option.
- **`race_engine` tests, and the frontend suite, run in a job that needs no
  database.** They're the fast slice of the suite (`race_engine` is plain
  Python per `pyproject.toml`'s own comment; the frontend suite runs in
  ~7 seconds). Splitting them from the Postgres-backed Django suite means a
  broken build or a broken engine test is visible fast instead of waiting
  behind the ~3-minute database-backed run.
- **Trigger is pull requests and pushes to `master`, not every branch
  push.** Chosen to conserve Actions minutes on the free private-repo tier
  against an agent-driven workflow that pushes to branches frequently.
- **No blocking of merges, no move to make the repo public, no paid tier.**
  Convention only. The value is visibility, not enforcement, for a solo
  developer; revisit if that stops being true.
- **No third-party coverage service.** The threshold check runs inside the
  workflow; nothing external is needed.
- **CD is a separate, later ticket.** No hosting target exists yet.
- **The `requirements.txt` stale-comment note from the original issue is
  already resolved** — no action needed here.
- **Backend suite runtime (2.5–4 minutes currently) is not addressed by
  this ticket.** Tracked instead as a possible future ticket — see
  Deferred.

## Open questions

None outstanding — the original issue's open questions (database need for
`race_engine`, trigger scope, direct-push-to-master) are all resolved above.

## Deferred

- **Backend test suite runtime.** The suite takes 2.5–4 minutes with no
  single slow test to blame — it's spread thin across ~400 tests, heaviest
  in `accounts` and `api` fixture setup. Not a problem yet; worth its own
  ticket to investigate and speed up if CI turns-per-day makes the wait
  costly.
- **Per-diff or per-app coverage.** More useful than whole-repo coverage,
  more work to set up. Wait until there's more than one contributor for the
  distinction to start mattering.
- **Dependency caching (pip, npm) in the workflow.** Only worth it once
  workflow runtime is itself annoying.
- **A dependency-audit step in CI.** Not part of the original ask.
