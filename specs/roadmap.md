# Roadmap

**Status:** agreed 2026-09-11
**Scope:** ordering only. This file says *what to build next and why*; it does not
say what any feature does — that is each issue, and later each spec.

The backlog is 43 issues. This is the order to take them in, and — more useful —
the reasons for deferring the rest.

## The question this roadmap answers

Not "what is foundational" — nearly every item in the backlog claims to be. The
filter is:

> **What is the first version a stranger can log into and lose interest in?**

The real risk is not picking the wrong issue. It is building a complete and
elegant economy for a game nobody is playing yet.

---

## Phase 1 — a race happens on its own

**Issues: [#6](https://github.com/mario595/cycling-manager/issues/6),
[#5](https://github.com/mario595/cycling-manager/issues/5),
[#7](https://github.com/mario595/cycling-manager/issues/7)**

Today a race is simulated because somebody runs a command. Until races happen
*because time passed*, there is no game — there is a simulator with a web front
end. That is the gap Phase 1 closes.

- **#6 game clock — genuinely first.** Every timed thing reads it. Building #25
  (weekly salaries) or #36 (weekly training) before the clock exists means
  writing them twice.
- **#5 Season** and **#7 race calendar** — what the clock advances *through*.

**[#52](https://github.com/mario595/cycling-manager/issues/52) — sticky
sidebar duplicates/detaches on long pages, jumps to the front of the queue.**
A frontend layout bug, found while building #7's calendar screen (the first
screen long enough on desktop to expose it reliably; reproduces on `/roster`
too). Not a Phase 1 dependency, but every screen built from here on is more
likely to be long enough to trigger it, so it is cheaper to fix now than to
keep discovering it screen by screen.

**Deliberately excluded: [#8](https://github.com/mario595/cycling-manager/issues/8),
the admin season-configuration tool.** Use Django admin or a fixture. A
purpose-built season editor, for a game with one season and one admin, is the
definition of premature.

**Caveat to settle when speccing #6.** A fast-forwardable clock is a development
convenience, but "simulate months in minutes" collides with simulation cost the
moment a single race takes real minutes to run. Measure per-race wall-clock time
before committing to that requirement.

## Phase 2 — the player makes a decision that matters

**Issue: [#37](https://github.com/mario595/cycling-manager/issues/37) — squad selection**

The highest-value single item in the backlog, and under-rated when it was first
written up. It is the **only** item in Phases 1–3 where a player choice changes
an outcome. Everything before it is plumbing; everything after it is depth.

It does not need [#41](https://github.com/mario595/cycling-manager/issues/41)
(injuries) to ship. The stage-race squad lock is simply less interesting without
it — an argument for doing #41 soon after, not for blocking on it.

## Phase 2.5 — somebody to race against

**Issue: [#44](https://github.com/mario595/cycling-manager/issues/44) — unmanaged
teams field a default squad**

A Division is full long before it has enough users — 16 teams, 6 users. Without
this, most of the field does not start and there is nothing to simulate.

Small, and it belongs here rather than in its own phase because **it is the same
mechanism as [#39](https://github.com/mario595/cycling-manager/issues/39)**
(a managed team whose manager did not log in). Both are *"a team with no human
input needs a squad"*. Build it once.

[#45](https://github.com/mario595/cycling-manager/issues/45) (heuristic AI) is
**not** in the early phases — but it has a named expiry, not an open-ended one.
See the deferrals below.

## Phase 3 — the loop closes

**Issues: [#15](https://github.com/mario595/cycling-manager/issues/15),
[#12](https://github.com/mario595/cycling-manager/issues/12), and a slice of
[#10](https://github.com/mario595/cycling-manager/issues/10)**

Points from results, accumulating into a standings table.

**Take only the slice of #10 that #12 needs — "one Group exists".** The doubling
pyramid, promotion, relegation and new-Division-opening (#11, #13) are not
required to have a league table, and building them now means balancing a
structure nobody is in yet.

---

## After Phase 3, the game is playable

Races happen weekly. The player picks who rides. Results accumulate. There is a
table. Seven issues, plus a slice of an eighth.

Everything past this point makes the game *better* rather than making it *exist*,
and the order becomes a matter of taste rather than dependency.

---

## Explicit deferrals

Recorded because each of these has a plausible-sounding case for going first.

### The entire economy — #20–#27

Deferred **as a group**, including
[#21](https://github.com/mario595/cycling-manager/issues/21) (fanbase), which is
flagged in the backlog as a sleeper prerequisite. It is — *within the economy*.
That is a statement about internal ordering, not about priority against the rest
of the board.

Money is only interesting when there is something to spend it on, and the things
to spend it on — [#28](https://github.com/mario595/cycling-manager/issues/28)
transfers, [#32](https://github.com/mario595/cycling-manager/issues/32)
development squad, [#35](https://github.com/mario595/cycling-manager/issues/35)
trainers — are all further out. A ledger with income and no meaningful outgoings
is a scoreboard.

**When the economy does start, the internal order is fixed:** #20 ledger → #21
fanbase → #22/#23 sponsorship. #21 before #22/#23 is not negotiable; sponsor
offers price off fanbase.

### Sprint and mountain points — #16, #17

Engine changes with a stated cost: new log event types, and per
`specs/rider-attributes.md`, any new in-race input invalidates the verified
realism balance across all six bundled courses and requires re-deriving it.

High cost, and they add **texture** rather than a loop. Do them when the work is
about making racing better, not while making it exist.

### Heuristic AI for unmanaged teams — #45

Deferred, but **with a hard expiry rather than an open-ended one: the first full
Season played with real users.**

[#44](https://github.com/mario595/cycling-manager/issues/44) leaves unmanaged
teams weak in a predictable, unchanging way. Human teams train and buy; these do
not, so the gap widens every Season. For a six-user playtest that is fine —
arguably useful, as a stable baseline to measure human teams against. For a real
league it is fatal: a Season ending with every human team above every unmanaged
one is not a competition, and it makes promotion and relegation
([#13](https://github.com/mario595/cycling-manager/issues/13)) meaningless,
because teams move by headcount rather than merit.

So this is not "when we get round to it". It is a prerequisite for the first
Season that counts.

### Team tactics — #38

Still unsizeable, and the most expensive item on the board for the same
engine-balance reason as #16/#17. It is the right thing to build after #37, but
it needs its own spec session before it can be estimated at all.

---

## A correction to an earlier reading

An earlier pass through this backlog named the dependency roots — the items
nothing else waits on — as #5, #6, #10, #20 and #41, and implied those were the
starting points.

That is structurally true and strategically misleading. #20 and #41 are roots of
**subtrees that should not be started yet**. Being a dependency root only matters
if you want the tree.

---

## How to use this file

Work the phases in order. For each issue, the next step is a spec, not code:

```
/product-spec <the issue, in a sentence>
```

Order of work remains **spec → plan → code** (`specs/README.md`).

Revisit this file whenever a phase completes, or whenever an assumption in it
turns out to be wrong — particularly the per-race simulation cost noted against
#6, which is the one number here that could force a rethink.
