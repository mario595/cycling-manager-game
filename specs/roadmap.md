# Roadmap

**Status:** agreed 2026-09-11, revised 2026-09-12, revised 2026-09-15, revised 2026-09-16
**Scope:** ordering only. This file says *what to build next and why*; it does not
say what any feature does — that is each issue, and later each spec.

45 open issues. This is the order to take them in, and — more useful — the
reasons for deferring the rest.

## The question this roadmap answers

Not "what is foundational" — nearly every item in the backlog claims to be. The
filter is:

> **What is the first version a stranger can log into and lose interest in?**

The real risk is not picking the wrong issue. It is building a complete and
elegant economy for a game nobody is playing yet.

---

## Done

| Phase | Issues | What it bought |
|---|---|---|
| **1 — a race happens on its own** | [#6](https://github.com/mario595/cycling-manager/issues/6) clock, [#5](https://github.com/mario595/cycling-manager/issues/5) season, [#7](https://github.com/mario595/cycling-manager/issues/7) calendar | Races arrive because time passed, not because somebody ran a command. |
| **2 — a decision that matters** | [#37](https://github.com/mario595/cycling-manager/issues/37) squad selection | A manager picks four riders and a leader per race. The first player choice that changes an outcome. |
| **3 — somebody to race against** | [#44](https://github.com/mario595/cycling-manager/issues/44), [#39](https://github.com/mario595/cycling-manager/issues/39) | Every team fields a squad, managed or not. Built once, shared — as planned. |
| **4a — a player can exist** | [#50](https://github.com/mario595/cycling-manager/issues/50) accounts | Register, log in, log out. |
| **(unplanned)** | [#1](https://github.com/mario595/cycling-manager/issues/1)/[#57](https://github.com/mario595/cycling-manager/issues/57) rider attributes | Age, speciality, build, hidden potential/peak/decline. Not in the original phases — pulled forward, and it makes the rider work below cheaper. |

---

## Phase 4b — finish the signup path *(in progress)*

**One issue: [#46](https://github.com/mario595/cycling-manager/issues/46) —
specced, not built.**

[#50](https://github.com/mario595/cycling-manager/issues/50) shipped accounts;
`specs/claiming-a-team.md` is written and waiting on a plan. Until it lands, a
registered player has no team — the half-open state, and the only thing between
here and a stranger being able to play.

Claim an unmanaged team: keep its table position, points and history; release its
riders as free agents; hand it twelve newly generated riders of equal total
strength; the player renames it and picks a code.

**Nothing else is in this phase.** Both candidates were cleared on 2026-09-15:

- **[#56](https://github.com/mario595/cycling-manager/issues/56)** (team code
  collisions) — **deferred.** Two teams sharing a code is confusing but liveable,
  accepted explicitly rather than fixed pre-emptively. See the deferrals.
- **[#14](https://github.com/mario595/cycling-manager/issues/14)** — **answered by
  #46 and reduced to one blocked question.** #46 settled both halves: the team is
  *assigned, not chosen*, and the claim applies *immediately*, mid-Season, with
  the player free to enter the next race. All that survives is which Division a
  new player lands in when there is more than one — trivial today, and blocked on
  [#11](https://github.com/mario595/cycling-manager/issues/11). Retitled and
  shrunk rather than closed, so the "bottom Division" rule is not lost.

## Phase 5 — the loop closes

**Issues: [#15](https://github.com/mario595/cycling-manager/issues/15) points,
[#12](https://github.com/mario595/cycling-manager/issues/12) standings, and a
slice of [#10](https://github.com/mario595/cycling-manager/issues/10).**

Unchanged, and now the last thing between here and a playable game. Races happen,
squads are picked, results exist — nothing yet accumulates.

**Take only the slice of #10 that #12 needs — "one Group exists".** The doubling
pyramid, promotion and relegation ([#11](https://github.com/mario595/cycling-manager/issues/11),
[#13](https://github.com/mario595/cycling-manager/issues/13)) are not required
for a league table, and building them now means balancing a structure nobody is
in yet.

**#46 raises the stakes here.** Claiming preserves a team's table position and
points, so there must *be* a table with points in it for that promise to mean
anything. Today it carries over an empty record.

## Phase 6 — riders stop being static

**Issues: [#58](https://github.com/mario595/cycling-manager/issues/58) growth and
decline, [#59](https://github.com/mario595/cycling-manager/issues/59) freshness,
[#35](https://github.com/mario595/cycling-manager/issues/35) trainers.**

#58 and #59 split out of #57's spec pass. The attributes exist and nothing moves
them: riders have a hidden potential, peak age and decline rate that never fire,
and a freshness value that never falls.

**#35 joined this phase on 2026-09-16, moved out of the deferred economy
group.** Its spec found no reason to wait on the ledger (#20): a team can hire a
free trainer into its one fixed slot today, and pricing the hire is split out as
[#69](https://github.com/mario595/cycling-manager/issues/69) for whenever #20
lands. #35 is what [#36](https://github.com/mario595/cycling-manager/issues/36)
(weekly training focus, already specced) has been waiting on — building it here
turns that spec into playable game rather than a document sitting on a
dependency.

Not in the original roadmap, and a genuine addition to it rather than a
reordering. The argument for doing them straight after Phase 5:

- **#59 freshness makes squad selection a real decision.** Right now the best
  four riders are the best four riders, every race, forever. Freshness is what
  turns a repeated trivial choice into rotation and planning — it cashes in the
  value of Phase 2 rather than adding a new system.
- **#58 growth and decline is what makes keeping a rider interesting**, and it is
  the prerequisite for anything downstream that prices a rider
  ([#26](https://github.com/mario595/cycling-manager/issues/26) salary
  renegotiation, [#31](https://github.com/mario595/cycling-manager/issues/31)
  market value, [#42](https://github.com/mario595/cycling-manager/issues/42)
  retirement).

If only one gets built, **#59 first** — it changes what the player does weekly;
#58 changes what they think about across Seasons, and there are not yet enough
Seasons for that to land.

---

## After Phase 6

Races happen weekly, a stranger can sign up and take over a team, squads are
picked under fatigue pressure, results accumulate into a table, riders improve
and decline.

That is a game. Everything past it makes the game *better* rather than making it
*exist*, and the order becomes a matter of taste rather than dependency.

---

## Explicit deferrals

Recorded because each has a plausible-sounding case for going first.

### The entire economy — #20–#27

Deferred **as a group**, including
[#21](https://github.com/mario595/cycling-manager/issues/21) (fanbase), flagged
in the backlog as a sleeper prerequisite. It is — *within the economy*. That is a
statement about internal ordering, not about priority against the rest of the
board.

Money is only interesting when there is something to spend it on, and the things
to spend it on — [#28](https://github.com/mario595/cycling-manager/issues/28)
transfers, [#32](https://github.com/mario595/cycling-manager/issues/32)
development squad — are further out. A ledger with income and no meaningful
outgoings is a scoreboard.

**[#35](https://github.com/mario595/cycling-manager/issues/35) (trainers) is no
longer in this group.** Its spec pass on 2026-09-16 found the mechanism didn't
need to wait on money at all — hiring is free until the ledger exists, priced
later as its own follow-up ([#69](https://github.com/mario595/cycling-manager/issues/69)).
See Phase 6.

**When the economy does start, the internal order is fixed:** #20 ledger → #21
fanbase → #22/#23 sponsorship. #21 before #22/#23 is not negotiable; sponsor
offers price off fanbase.

**#27 (insolvency) is the last thing in this group, not an afterthought.** Its
ladder — embargo, then forced sales, then losing the team — needs wages (#25) and
a market with buyers (#28/#29) before any rung can fire.

### Sprint and mountain points — #16, #17

Engine changes with a stated cost: new log event types, and any new in-race input
invalidates the verified realism balance across all six bundled courses and
requires re-deriving it.

High cost, and they add **texture** rather than a loop. Do them when the work is
about making racing better, not while making it exist.

### Heuristic AI for unmanaged teams — #45

Deferred, but **with a hard expiry rather than an open-ended one: the first full
Season played with real users.**

[#44](https://github.com/mario595/cycling-manager/issues/44) leaves unmanaged
teams weak in a predictable, unchanging way. Human teams will train and buy;
these do not, so the gap widens every Season. For a small playtest that is fine —
arguably useful, as a stable baseline. For a real league it is fatal: a Season
ending with every human team above every unmanaged one is not a competition, and
it makes promotion and relegation (#13) meaningless, because teams move by
headcount rather than merit.

**Phase 6 moves this expiry closer.** Once riders improve (#58) and human
managers rotate squads on freshness (#59), unmanaged teams fall behind *faster*
than they do today.

### Losing a team — #62, #63

Added 2026-09-15. A manager stops managing; the team returns to the unmanaged
pool and is re-claimable. Split from its triggers because they have very
different dependencies.

**[#62](https://github.com/mario595/cycling-manager/issues/62), the mechanism, is
buildable now** — it depends only on
[#46](https://github.com/mario595/cycling-manager/issues/46) and closes that
spec's deferred question about abandoned teams. It is deferred not because it is
blocked but because **nothing yet triggers it**: with no inactivity rule and no
money, a mechanism for losing a team would never fire.

**[#63](https://github.com/mario595/cycling-manager/issues/63), inactivity, is the
trigger to build first** when this area comes up — it needs a timestamp and the
clock, both of which exist. Bankruptcy
([#27](https://github.com/mario595/cycling-manager/issues/27)) is the other
trigger and is deferred with the whole economy; it has nothing to operate on
until wages and a market exist.

**Worth pulling forward once there is a real playtest**, since inactivity is the
condition that will actually occur: players sign up, drift away, and hold a place
in a fixed-size Division while #44 races their team badly forever.

### Team code disambiguation — #56

**Deferred 2026-09-15.** #46 deliberately drops the uniqueness check on team
codes so a player is never told their choice is taken; #56 is the consequence —
making two identical codes readable side by side.

Accepted as liveable rather than fixed pre-emptively. Two teams sharing a code is
confusing, not broken, and the collision is theoretical until Groups exist and
put clashing codes in the same table. Revisit if it actually bites during play.

### Divisions beyond one Group — #11, #13

Deferred with Phase 5's slice of #10: a league table needs one Group, not a
pyramid. #13 is also meaningless until #45 exists — see above.

**#11 now also gates [#14](https://github.com/mario595/cycling-manager/issues/14)**
(which Division a new player lands in) and
[#56](https://github.com/mario595/cycling-manager/issues/56) (code collisions).
Both are questions that cannot even be asked with a single Division.

### Account self-service — #51

Password reset, change password, change email, delete account. Split from #50 so
the blocking half could ship, which it has.

A player who can register and log in can play. Password reset drags in **email
delivery**, a deployment and cost decision — and deployment is still TBD,
targeting low-cost/free hosting. **Revisit before any playtest with real users
who can lock themselves out**, which is a nearer horizon than it was.

### Team tactics — #38

Still the most expensive item on the board, for the same engine-balance reason as
#16/#17. It is the right thing to build after #37, but it needs its own spec
session before it can be estimated at all.

### Race detail view — #47

A per-race screen, split out of #7. Blocked in content terms rather than
technically: "who is racing" became answerable when #37 landed, so this is now
*buildable* — but it displays the game rather than advancing it. After Phase 5,
when there are standings and points worth showing on it.

---

## How to use this file

Work the phases in order. For each issue, the next step is a spec, not code:

```
/product-spec #<issue>
```

Order of work is **spec → plan → code → review** (`specs/README.md`,
`.claude/ticket-workflow.md`).

Revisit this file whenever a phase completes, **or whenever a decision about how
a feature works reorders it** — that is the normal way it goes stale, not the
passage of time. Three precedents: deciding registration *claims* a team rather
than creating one moved account work later; #57's spec pass split out #58 and
#59, which added a phase that was not here before; #35's spec pass found its
economy dependency was avoidable, pulling it out of the deferred group and into
Phase 6.
