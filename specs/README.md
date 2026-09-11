# Feature specs

Product-level definitions of features: what the game should do from a **player's**
point of view. No code, no data model, no formulas — those belong in the domain's
`README.md` or a `*_PLAN.md` next to it.

A spec is written by the `product-spec` skill (`.claude/skills/product-spec/`),
which reads the relevant domain `README.md`, asks clarifying questions, challenges the
scope, and only then writes the file. Run it with `/product-spec` followed by the
rough feature idea.

One file per feature, kebab-case: `specs/mechanical-problems.md`.

Order of work: **spec → plan → code.** A spec says what; a `*_PLAN.md` says how.

## Two files here are not feature specs

- **`roadmap.md`** — which issues to build next, in what order, and why the rest
  are deferred. Read it before picking something up.
- **`backlog-brain-dump.md`** — the captured backlog (issues #5–#43) and the
  reasoning behind how each item was scoped and named. Read the entry for a
  feature before speccing it; it records decisions already taken.
