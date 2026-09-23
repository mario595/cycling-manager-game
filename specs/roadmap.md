# Roadmap

**Status:** agreed 2026-09-11, last revised 2026-09-22
**Scope:** ordering only. This file says *what to build next, in what order, and
what blocks what*. It does not say what any feature does — that is each issue,
and later each spec.

34 open issues.

## The question this roadmap answers

Not "what is foundational" — nearly every item claims to be. The filter is:

> **What is the first version a stranger can log into and lose interest in?**

**That version exists.** A stranger can register, be given a team, pick a squad
each week under fatigue pressure, direct training, watch races run on a calendar,
and see where they stand in a table. Everything below is about making it worth
coming back to.

---

# Part 1 — Done

| Area | Issues |
|---|---|
| **Time and the calendar** | [#6](https://github.com/mario595/cycling-manager/issues/6) clock · [#5](https://github.com/mario595/cycling-manager/issues/5) season · [#7](https://github.com/mario595/cycling-manager/issues/7) race calendar |
| **Racing decisions** | [#37](https://github.com/mario595/cycling-manager/issues/37) squad selection · [#64](https://github.com/mario595/cycling-manager/issues/64) leadership is per-race · [#39](https://github.com/mario595/cycling-manager/issues/39) absent-manager default · [#44](https://github.com/mario595/cycling-manager/issues/44) unmanaged-team squads |
| **Signing up** | [#50](https://github.com/mario595/cycling-manager/issues/50) accounts · [#46](https://github.com/mario595/cycling-manager/issues/46) claiming a team |
| **The competitive loop** | [#15](https://github.com/mario595/cycling-manager/issues/15) race points · [#12](https://github.com/mario595/cycling-manager/issues/12) standings |
| **Riders as assets** | [#1](https://github.com/mario595/cycling-manager/issues/1)/[#57](https://github.com/mario595/cycling-manager/issues/57) attributes · [#58](https://github.com/mario595/cycling-manager/issues/58) growth and decline · [#59](https://github.com/mario595/cycling-manager/issues/59) freshness |
| **Staff and training** | [#35](https://github.com/mario595/cycling-manager/issues/35) trainers · [#36](https://github.com/mario595/cycling-manager/issues/36) weekly training focus |
| **Money** | [#20](https://github.com/mario595/cycling-manager/issues/20) ledger · [#19](https://github.com/mario595/cycling-manager/issues/19) prize money · [#21](https://github.com/mario595/cycling-manager/issues/21) fanbase and merchandise · [#22](https://github.com/mario595/cycling-manager/issues/22) sponsorship · [#23](https://github.com/mario595/cycling-manager/issues/23) sponsor renewal · [#25](https://github.com/mario595/cycling-manager/issues/25) per-rider salaries · [#69](https://github.com/mario595/cycling-manager/issues/69) trainer fee and salary |
| **Screens and plumbing** | [#47](https://github.com/mario595/cycling-manager/issues/47) race detail · [#77](https://github.com/mario595/cycling-manager/issues/77) results screen · [#73](https://github.com/mario595/cycling-manager/issues/73) mock UI stripped, login required · [#80](https://github.com/mario595/cycling-manager/issues/80) CI · [#52](https://github.com/mario595/cycling-manager/issues/52) sidebar fix |

**The roadmap has been overridden three times without harm** — rider attributes,
trainers and the race detail view were all pulled forward out of order. Left
visible rather than tidied away: this file argues about order, it does not commit
to it.

---

# Part 2 — What to build next, in order

## 2.1 — Make money matter

**The economy's first circuit is closed.** A team now has three income streams
(prize money, merchandise, sponsorship) and three outgoings (per-rider salaries,
trainer fee and salary). Every rider carries a real `weekly_salary` derived from
their attributes — the flat wage is gone.

What remains is consequence: a balance that can only be watched is a scoreboard.

| Order | Issue | Why | Blocked by |
|---|---|---|---|
| 1 | [#62](https://github.com/mario595/cycling-manager/issues/62) losing a team (mechanism) | Buildable since [#46](https://github.com/mario595/cycling-manager/issues/46) shipped. Closes that spec's deferred question about abandoned teams. | [#46](https://github.com/mario595/cycling-manager/issues/46) ✅ |
| 2 | [#63](https://github.com/mario595/cycling-manager/issues/63) inactivity trigger | Needs only a timestamp and the clock. **The trigger that will actually fire** — players drift. | [#62](https://github.com/mario595/cycling-manager/issues/62) |
| 3 | [#27](https://github.com/mario595/cycling-manager/issues/27) insolvency ladder | The second trigger. Embargo → forced sales → team lost. Needs somewhere to sell riders. | [#25](https://github.com/mario595/cycling-manager/issues/25) ✅ · [#62](https://github.com/mario595/cycling-manager/issues/62) · **[#28](https://github.com/mario595/cycling-manager/issues/28)/[#29](https://github.com/mario595/cycling-manager/issues/29)** |

**[#62](https://github.com/mario595/cycling-manager/issues/62) and [#63](https://github.com/mario595/cycling-manager/issues/63) jump the queue the moment there is a real playtest.** An absent
manager holds a place in a fixed-size Division while [#44](https://github.com/mario595/cycling-manager/issues/44) races their team badly
forever — a live problem the first time signups exceed teams.

## 2.3 — The transfer market

The largest coherent block left, and the first that makes a roster something you
*build* rather than something you were given.

**Internal order is forced:** [#31](https://github.com/mario595/cycling-manager/issues/31) → [#29](https://github.com/mario595/cycling-manager/issues/29) → [#28](https://github.com/mario595/cycling-manager/issues/28) → [#30](https://github.com/mario595/cycling-manager/issues/30).

| Order | Issue | Note | Blocked by |
|---|---|---|---|
| 4 | [#31](https://github.com/mario595/cycling-manager/issues/31) rider market value | Anchors every price. Needs riders to have been observed improving — [#58](https://github.com/mario595/cycling-manager/issues/58) made that possible. | [#58](https://github.com/mario595/cycling-manager/issues/58) ✅ [#25](https://github.com/mario595/cycling-manager/issues/25) |
| 5 | [#29](https://github.com/mario595/cycling-manager/issues/29) free agents | [#46](https://github.com/mario595/cycling-manager/issues/46) already releases riders on every claim, so the pool exists and is currently inert. | [#31](https://github.com/mario595/cycling-manager/issues/31) |
| 6 | [#28](https://github.com/mario595/cycling-manager/issues/28) auctions | The market itself. | [#29](https://github.com/mario595/cycling-manager/issues/29), [#20](https://github.com/mario595/cycling-manager/issues/20) ✅ |
| 7 | [#30](https://github.com/mario595/cycling-manager/issues/30) AI teams trade | Without it the market is dead at launch — most teams have no manager. | [#28](https://github.com/mario595/cycling-manager/issues/28) |

Completing this also unblocks **[#27](https://github.com/mario595/cycling-manager/issues/27)** (forced sales need buyers) and
**[#26](https://github.com/mario595/cycling-manager/issues/26)** (post-season salary renegotiation needs a value to renegotiate against).

## 2.4 — Rider supply

Riders decline ([#58](https://github.com/mario595/cycling-manager/issues/58)) and nothing replaces them. Rosters ossify without this.

| Order | Issue | Blocked by |
|---|---|---|
| 8 | [#42](https://github.com/mario595/cycling-manager/issues/42) retirement | [#58](https://github.com/mario595/cycling-manager/issues/58) ✅ |
| 9 | [#32](https://github.com/mario595/cycling-manager/issues/32) development squad | [#20](https://github.com/mario595/cycling-manager/issues/20) ✅ |
| 10 | [#33](https://github.com/mario595/cycling-manager/issues/33) youth intake | [#32](https://github.com/mario595/cycling-manager/issues/32) |
| 11 | [#34](https://github.com/mario595/cycling-manager/issues/34) promote/retain/discard | [#33](https://github.com/mario595/cycling-manager/issues/33), [#29](https://github.com/mario595/cycling-manager/issues/29) |

**[#34](https://github.com/mario595/cycling-manager/issues/34) is the payoff of the hidden-attribute design** — triage is a judgement only
because potential is hidden. It is also what gives the scout in
[#40](https://github.com/mario595/cycling-manager/issues/40) something to sell.

## 2.5 — Racing gets richer

| Order | Issue | Note | Blocked by |
|---|---|---|---|
| 12 | [#88](https://github.com/mario595/cycling-manager/issues/88) slim and compress the log format | A mountain stage is **75.7 MB**; gzip alone takes it to ~2.7 MB. Do it before storage hurts, not after. Pair with [#70](https://github.com/mario595/cycling-manager/issues/70) — that also changes the format, and doing both at once touches `race_player/` once. | — |
| 13 | [#70](https://github.com/mario595/cycling-manager/issues/70) course markers | **The foundation.** `race_engine` has no event concept at all — it emits per-tick positions. Means a new log record type and a change to the season declaration format. Pair with the log slimming `racing/README.md` already wants. | — |
| 14 | [#16](https://github.com/mario595/cycling-manager/issues/16)/[#17](https://github.com/mario595/cycling-manager/issues/17) sprint and mountain points | — | [#70](https://github.com/mario595/cycling-manager/issues/70) |
| 15 | [#9](https://github.com/mario595/cycling-manager/issues/9) stage races | Multi-day races with a GC. | [#7](https://github.com/mario595/cycling-manager/issues/7) ✅ |
| 16 | [#89](https://github.com/mario595/cycling-manager/issues/89) races have a type, one is a TT | Cheap, and [#9](https://github.com/mario595/cycling-manager/issues/9) probably wants it — real Grand Tours are often decided by a TT stage. Changes no simulation. | [#9](https://github.com/mario595/cycling-manager/issues/9) |
| 17 | [#90](https://github.com/mario595/cycling-manager/issues/90) engine support for a solo effort | **The large one.** Every mechanic that decides a race today assumes a bunch — 221 references to drafting and pack behaviour in `race_engine/`. A TT is the deliberate absence of all of it, and not simply drafting switched off. | [#89](https://github.com/mario595/cycling-manager/issues/89) |
| 18 | [#18](https://github.com/mario595/cycling-manager/issues/18) classifications | **First feature that makes a squad of specialists worth assembling.** Earns its place sooner than its position suggests. | [#16](https://github.com/mario595/cycling-manager/issues/16), [#17](https://github.com/mario595/cycling-manager/issues/17), [#9](https://github.com/mario595/cycling-manager/issues/9) |
| 19 | [#41](https://github.com/mario595/cycling-manager/issues/41) injuries | Gives the stage-race squad lock its teeth, and the physio ([#40](https://github.com/mario595/cycling-manager/issues/40)) a job. | [#9](https://github.com/mario595/cycling-manager/issues/9) |

## 2.6 — The pyramid

Deferred as a block until there are enough players to fill more than one
Division. Building it now means balancing a structure nobody is in.

| Order | Issue | Blocked by |
|---|---|---|
| 20 | [#10](https://github.com/mario595/cycling-manager/issues/10) Divisions and Groups | [#12](https://github.com/mario595/cycling-manager/issues/12) ✅ (shipped against one Group) |
| 21 | [#11](https://github.com/mario595/cycling-manager/issues/11) opening a Division | [#10](https://github.com/mario595/cycling-manager/issues/10) |
| 22 | [#45](https://github.com/mario595/cycling-manager/issues/45) heuristic AI | [#28](https://github.com/mario595/cycling-manager/issues/28), [#36](https://github.com/mario595/cycling-manager/issues/36) ✅ |
| 23 | [#13](https://github.com/mario595/cycling-manager/issues/13) promotion and relegation | [#10](https://github.com/mario595/cycling-manager/issues/10), **[#45](https://github.com/mario595/cycling-manager/issues/45)** |
| 24 | [#14](https://github.com/mario595/cycling-manager/issues/14) which Division a new player lands in | [#11](https://github.com/mario595/cycling-manager/issues/11) |
| 25 | [#56](https://github.com/mario595/cycling-manager/issues/56) team code collisions | [#11](https://github.com/mario595/cycling-manager/issues/11) |

**[#13](https://github.com/mario595/cycling-manager/issues/13) is meaningless without [#45](https://github.com/mario595/cycling-manager/issues/45).** Unmanaged teams never improve, so a Season
ends with every human team above every unmanaged one and teams move by headcount
rather than merit. **[#45](https://github.com/mario595/cycling-manager/issues/45)'s expiry is the first full Season played with real
users** — and every shipped system that rewards active management ([#58](https://github.com/mario595/cycling-manager/issues/58), [#36](https://github.com/mario595/cycling-manager/issues/36), [#59](https://github.com/mario595/cycling-manager/issues/59))
has moved that expiry closer.

---

# Part 3 — Deferred, with reasons

| Issue | Why it waits |
|---|---|
| [#38](https://github.com/mario595/cycling-manager/issues/38) team tactics | Still unsizeable, and the most expensive item on the board: new in-race inputs invalidate the audited six-course realism balance. Needs its own spec session before it can be estimated at all. |
| [#40](https://github.com/mario595/cycling-manager/issues/40) physio and scout | The physio needs injuries ([#41](https://github.com/mario595/cycling-manager/issues/41)); the scout needs youth triage ([#34](https://github.com/mario595/cycling-manager/issues/34)) and a market ([#28](https://github.com/mario595/cycling-manager/issues/28)) to sell information into. Both arrive with their blockers. |
| [#26](https://github.com/mario595/cycling-manager/issues/26) salary renegotiation | Needs [#25](https://github.com/mario595/cycling-manager/issues/25) and [#31](https://github.com/mario595/cycling-manager/issues/31) — a value to renegotiate against. |
| [#43](https://github.com/mario595/cycling-manager/issues/43) season awards and history | Cheap, and mostly what makes a long-running world feel like it has a past. Wants several Seasons to have happened first. |
| [#51](https://github.com/mario595/cycling-manager/issues/51) account self-service | **Revisit before any playtest with real users who can lock themselves out.** Drags in email delivery — a deployment and cost decision, and deployment is still TBD. |
| [#65](https://github.com/mario595/cycling-manager/issues/65) unique display names | Small, no dependencies, genuinely low priority. Grab it in a lull. |
| [#8](https://github.com/mario595/cycling-manager/issues/8) admin season tool | A file loaded by a command already declares a season. A purpose-built editor for one admin is premature. |
| [#24](https://github.com/mario595/cycling-manager/issues/24) merchandising investment | Explicitly deferred in its own ticket — a decision about a spreadsheet rather than about bike racing. |
| [#91](https://github.com/mario595/cycling-manager/issues/91) time-trialling attribute | Last stage of [#2](https://github.com/mario595/cycling-manager/issues/2), and **may prove unnecessary** — a time trial might be adequately decided by the existing `flat` and `resistance`. Test that before paying for a sixth in-race attribute, which costs a full re-derivation of the six-course realism balance. |
| [#3](https://github.com/mario595/cycling-manager/issues/3), [#4](https://github.com/mario595/cycling-manager/issues/4) new rider attributes | Each is an *in-race* attribute, so each costs a re-derivation of the six-course balance. Judged individually, never added by default. |

---

# Dependency summary

The chains that actually constrain order:

```
#20 ledger ✅ ──┬─→ #19 prize money ✅
                ├─→ #69 trainer pricing ✅
                ├─→ #25 per-rider salaries ✅ ──→ #31 value ──→ #29 agents ──→ #28 market ──→ #30 AI trades
                └─→ #21 fanbase ✅ ──→ #22 sponsors ✅ ──→ #23 renewal ✅

#46 claiming ✅ ──→ #62 losing a team ──→ #63 inactivity
                                      └──→ #27 insolvency ←── #25 ✅, #28

#58 growth ✅ ──→ #42 retirement
#32 dev squad ──→ #33 intake ──→ #34 triage ──→ (#40 scout)

#70 markers ──→ #16/#17 points ──┐
#9 stage races ──────────────────┴──→ #18 classifications
                └──→ #41 injuries ──→ (#40 physio)

#10 Divisions ──→ #11 ──→ #14, #56
#28 market ──→ #45 AI ──→ #13 promotion/relegation ←── #10
```

**Three tickets unblock disproportionately:** [#20](https://github.com/mario595/cycling-manager/issues/20) (shipped), [#28](https://github.com/mario595/cycling-manager/issues/28) (gates the
market, insolvency, the AI and renegotiation) and [#70](https://github.com/mario595/cycling-manager/issues/70) (gates all of racing's
texture).

---

## How to use this file

Work the order in Part 2. For each issue, the next step is a spec, not code:

```
/product-spec #<issue>
```

Order of work is **spec → plan → code → review** (`specs/README.md`,
`.claude/ticket-workflow.md`).

Revisit whenever something ships, **or whenever a decision about how a feature
works reorders things** — that is the normal way this file goes stale, not the
passage of time. Precedents: deciding registration *claims* a team moved account
work later; [#57](https://github.com/mario595/cycling-manager/issues/57)'s spec pass split out [#58](https://github.com/mario595/cycling-manager/issues/58) and [#59](https://github.com/mario595/cycling-manager/issues/59); shipping trainers unpriced
([#35](https://github.com/mario595/cycling-manager/issues/35) → [#69](https://github.com/mario595/cycling-manager/issues/69)) punctured the economy deferral, which [#20](https://github.com/mario595/cycling-manager/issues/20) then filled.
