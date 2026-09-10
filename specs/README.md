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
