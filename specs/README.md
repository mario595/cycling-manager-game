# Feature specs

Product-level definitions of features: what the game should do from a **player's**
point of view. No code, no data model, no formulas — those belong in the domain's
`README.md` or a `*_PLAN.md` next to it.

A spec is written by the `product-spec` skill (`.claude/skills/product-spec/`),
which reads the relevant domain `README.md`, asks clarifying questions, challenges the
scope, and only then writes the file. Run it with `/product-spec` followed by the
rough feature idea.

One file per feature, kebab-case: `specs/mechanical-problems.md`.

Order of work: **spec → plan → code.** A spec says what; a plan says how.

Both writing steps start from a GitHub issue and move it on when their output is
agreed: `/product-spec` moves the ticket to **Scoped**, `/tech-plan` to
**Refined**. Each also posts its document to the issue as a snapshot comment —
the file here stays the source of truth. The procedure is in
`.claude/ticket-workflow.md`.

The third step is `/implement-plan`, which builds an agreed plan: a git worktree,
one commit per work item, tests for every new behaviour, and the full suite green
before each commit. It does not move the ticket.

## Plans

The implementation plan for a spec sits beside it as `specs/<slug>-plan.md`
(`game-clock.md` → `game-clock-plan.md`). It is written by the `tech-plan` skill
(`.claude/skills/tech-plan/`), which reads the spec *and the code*, settles the
technical decisions, and breaks the work into ordered, commit-sized items each
with the test that proves it. Run it with `/tech-plan specs/<slug>.md`.

A plan is written for an engineer who has not seen this codebase, so it names
files, fields and tests explicitly rather than describing them.

Older plans live next to their code as `<app>/<FEATURE>_PLAN.md` —
`race_engine/WIND_PLAN.md`, `race_player/TEAM_VISUALIZATION_PLAN.md`. Those stay
where they are and remain the best examples of the format; new plans go here.

## Two files here are not feature specs

- **`roadmap.md`** — which issues to build next, in what order, and why the rest
  are deferred. Read it before picking something up.
- **`backlog-brain-dump.md`** — the captured backlog (issues #5–#43) and the
  reasoning behind how each item was scoped and named. Read the entry for a
  feature before speccing it; it records decisions already taken.
