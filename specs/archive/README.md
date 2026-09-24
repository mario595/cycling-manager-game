# Archive — shipped specs and plans

The spec and plan for every ticket that has shipped. They are kept as the
record of **why**, and they are **frozen**.

A `README.md` in a domain folder says what the code does today and is kept
current. These files say what was decided when the feature was built: which
alternative was rejected, what was deliberately cut, what was deferred and on
what reasoning. That is what the next ticket in the same area needs, and it is
not recoverable from the code.

**Nothing here is edited to match later changes.** A file that no longer
matches the code is not stale — it is a record of a decision taken at a point
in time. When behaviour moves, the new ticket writes its own spec in `specs/`;
it does not rewrite one here. Each file carries `Status: implemented`.

Live specs for work not yet shipped are one level up, in `specs/`.
