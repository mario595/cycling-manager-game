# Roadmap

**Status:** agreed 2026-09-11, last revised 2026-09-17
**Scope:** ordering only. This file says *what to build next and why*; it does not
say what any feature does — that is each issue, and later each spec.

42 open issues. This is the order to take them in, and — more useful — the
reasons for deferring the rest.

## The question this roadmap answers

Not "what is foundational" — nearly every item in the backlog claims to be. The
filter is:

> **What is the first version a stranger can log into and lose interest in?**

**That version now exists.** A stranger can register, be given a team, pick a
squad each week, watch races run on a calendar, and see where they stand in a
table. Everything below is about making it worth coming back to.

---

## Done

| What | Issues |
|---|---|
| **Races happen because time passed** | [#6](https://github.com/mario595/cycling-manager/issues/6) clock, [#5](https://github.com/mario595/cycling-manager/issues/5) season, [#7](https://github.com/mario595/cycling-manager/issues/7) calendar |
| **A manager makes a decision that matters** | [#37](https://github.com/mario595/cycling-manager/issues/37) squad selection, [#64](https://github.com/mario595/cycling-manager/issues/64) leadership is per-race |
| **Everyone has an opponent** | [#44](https://github.com/mario595/cycling-manager/issues/44), [#39](https://github.com/mario595/cycling-manager/issues/39) — built once and shared, as planned |
| **A stranger can sign up and play** | [#50](https://github.com/mario595/cycling-manager/issues/50) accounts, [#46](https://github.com/mario595/cycling-manager/issues/46) claiming a team |
| **The loop closes** | [#15](https://github.com/mario595/cycling-manager/issues/15) race points, [#12](https://github.com/mario595/cycling-manager/issues/12) standings |
| **Riders are not static** | [#1](https://github.com/mario595/cycling-manager/issues/1)/[#57](https://github.com/mario595/cycling-manager/issues/57) attributes, [#58](https://github.com/mario595/cycling-manager/issues/58) growth and decline |
| **Staff exist** | [#35](https://github.com/mario595/cycling-manager/issues/35) trainers — hired and fired for free, pricing deferred to [#69](https://github.com/mario595/cycling-manager/issues/69) |

**Two of these were never in the plan.** Rider attributes and trainers were both
pulled forward. Worth noticing rather than tidying away: the roadmap is a
argument about order, not a commitment, and it has been overridden twice without
obvious harm.

---

## In flight

**[#36](https://github.com/mario595/cycling-manager/issues/36) — weekly training
focus.** Spec and plan are written and committed; no work items ticked yet.

It completes the trainer: [#35](https://github.com/mario595/cycling-manager/issues/35)
shipped the hire, this is the thing a trainer actually does week to week. It also
gives [#58](https://github.com/mario595/cycling-manager/issues/58)'s growth curve
a lever the manager controls, rather than riders improving at the game's
discretion.

## Next — [#59](https://github.com/mario595/cycling-manager/issues/59), freshness

**The single highest-value item left**, and the argument has strengthened since
it was written.

Squad selection exists and is currently trivial: the best four riders are the
best four riders, every race, forever. Freshness is what turns a repeated
non-choice into rotation and planning — it cashes in work already shipped rather
than adding a system.

It has also gained a second job. Now that riders improve (#58) and training is a
weekly decision (#36), freshness is the cost that stops "race everyone always"
being free. Without it, both of those systems are strictly one-directional.

**#36 and #59 are also the two halves of a weekly rhythm.** Pick a focus, manage
fatigue, choose a squad — that is the loop a manager repeats, and #59 is the only
piece of it missing.

## After that — the economy, starting properly

The economy has been deferred as a group since the first roadmap. **That
deferral is now the thing holding several finished features half-built:**

- [#35](https://github.com/mario595/cycling-manager/issues/35) ships trainers
  that cost nothing, with pricing parked in
  [#69](https://github.com/mario595/cycling-manager/issues/69).
- [#46](https://github.com/mario595/cycling-manager/issues/46) decided a claimed
  team's money resets to a standard amount — recorded, unimplementable.
- [#62](https://github.com/mario595/cycling-manager/issues/62)/[#27](https://github.com/mario595/cycling-manager/issues/27)
  cannot fire their economic trigger.

The original argument — "money is dull until there is something to spend it on" —
has expired. There is now something: trainers to pay, and #69 waiting on it.

**The internal order is fixed and unchanged:**
[#20](https://github.com/mario595/cycling-manager/issues/20) ledger →
[#21](https://github.com/mario595/cycling-manager/issues/21) fanbase →
[#22](https://github.com/mario595/cycling-manager/issues/22)/[#23](https://github.com/mario595/cycling-manager/issues/23)
sponsorship. #21 before #22/#23 is not negotiable; sponsor offers price off
fanbase. [#25](https://github.com/mario595/cycling-manager/issues/25) rider
salaries and [#69](https://github.com/mario595/cycling-manager/issues/69) trainer
pricing follow the ledger directly and are what make it bite.

**Start with #20 alone.** A ledger with two outgoings (rider wages, trainer
salary) and one income (prize money, #19) is a complete small system. Fanbase and
sponsorship can wait for it to prove itself.

---

## Explicit deferrals

Recorded because each has a plausible-sounding case for going first.

### Divisions, promotion and relegation — #10, #11, #13

[#12](https://github.com/mario595/cycling-manager/issues/12) shipped standings
against a single Group, as planned. The pyramid stays deferred until there are
enough players to fill more than one Division — building it now means balancing a
structure nobody is in.

**#13 is additionally meaningless until
[#45](https://github.com/mario595/cycling-manager/issues/45) exists** — see below.

**#11 gates two small tickets:**
[#14](https://github.com/mario595/cycling-manager/issues/14) (which Division a new
player lands in) and [#56](https://github.com/mario595/cycling-manager/issues/56)
(team code collisions). Neither question can even be asked with one Division.

### Heuristic AI for unmanaged teams — #45

Deferred, **with a hard expiry rather than an open-ended one: the first full
Season played with real users.**

[#44](https://github.com/mario595/cycling-manager/issues/44) leaves unmanaged
teams weak in a predictable, unchanging way. A Season ending with every human
team above every unmanaged one is not a competition, and it makes promotion and
relegation meaningless — teams would move by headcount rather than merit.

**The expiry is closer than it was.** #58 (riders improve) and #36 (managers
direct that improvement) both widen the gap, and #59 will widen it again. Every
system that rewards active management accelerates this.

### Losing a team — #62, #63

A manager stops managing; the team returns to the unmanaged pool.
[#62](https://github.com/mario595/cycling-manager/issues/62) (the mechanism) is
buildable now — it depends only on #46, which has shipped — and closes that
spec's deferred question about abandoned teams.

Deferred not because it is blocked but because **nothing yet triggers it**.
[#63](https://github.com/mario595/cycling-manager/issues/63) (inactivity) is the
trigger to build first; it needs only a timestamp and the clock.

**Pull both forward the moment there is a real playtest.** Inactivity is the
condition that will actually occur: players sign up, drift, and hold a place in a
fixed-size Division while #44 races their team badly forever.

### Sprint and mountain points — #70, #16, #17, #18

Four issues, with [#70](https://github.com/mario595/cycling-manager/issues/70)
(course markers) as the foundation. Order within the group is fixed: #70 markers
→ #16/#17 points → #18 classifications. #18 additionally needs
[#9](https://github.com/mario595/cycling-manager/issues/9) (stage races).

The cost is real: `race_engine` has **no event concept at all** — it emits
per-tick positions, so markers mean a new kind of log record and a change to the
season declaration format. Worth pairing with the log slimming
`racing/README.md` already wants.

**#18 earns its place sooner than this position suggests** — it is the first
feature that makes a *squad of specialists* worth assembling, which is what makes
a roster interesting to build.

### Account self-service — #51

Password reset, change password, change email, delete account. Split from #50 so
the blocking half could ship, which it has.

**Revisit before any playtest with real users who can lock themselves out** —
nearer now than when it was parked. It still drags in email delivery, a
deployment and cost decision, and deployment is still TBD.

### Team tactics — #38

Still the most expensive item on the board, for the same engine-balance reason as
#70. The right thing to build after squad selection, but it needs its own spec
session before it can be estimated at all.

### Race detail view — #47

Buildable — "who is racing" became answerable when #37 landed, and #12 gave it
standings worth showing. It displays the game rather than advancing it, so it
waits for a lull or a playtest that needs it to look finished.

### Development squad and transfers — #28–#34

Unchanged and genuinely far out. Both need the economy, and transfers need
[#31](https://github.com/mario595/cycling-manager/issues/31) (market value),
which needs riders to have been observed improving — which #58 has only just made
possible.

---

## How to use this file

Work the order above. For each issue, the next step is a spec, not code:

```
/product-spec #<issue>
```

Order of work is **spec → plan → code → review** (`specs/README.md`,
`.claude/ticket-workflow.md`).

Revisit this file whenever a phase completes, **or whenever a decision about how
a feature works reorders it** — that is the normal way it goes stale, not the
passage of time. Three precedents so far: deciding registration *claims* a team
moved account work later; #57's spec pass split out #58 and #59; and shipping
trainers unpriced (#35 → #69) put a hole in the economy deferral that #20 now has
to fill.
