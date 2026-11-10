# Roadmap

**Status:** agreed 2026-09-11, last revised 2026-11-10 (rollout milestones)
**Scope:** ordering only. This file says *what to build next, in what order, and
what blocks what*. It does not say what any feature does — that is each issue,
and later each spec.

32 open issues.

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
| **Racing decisions** | [#37](https://github.com/mario595/cycling-manager/issues/37) squad selection · [#64](https://github.com/mario595/cycling-manager/issues/64) leadership is per-race · [#39](https://github.com/mario595/cycling-manager/issues/39) absent-manager default · [#44](https://github.com/mario595/cycling-manager/issues/44) unmanaged-team squads · [#9](https://github.com/mario595/cycling-manager/issues/9) stage races |
| **Signing up** | [#50](https://github.com/mario595/cycling-manager/issues/50) accounts · [#46](https://github.com/mario595/cycling-manager/issues/46) claiming a team · [#62](https://github.com/mario595/cycling-manager/issues/62) losing a team · [#63](https://github.com/mario595/cycling-manager/issues/63) inactivity trigger |
| **The competitive loop** | [#15](https://github.com/mario595/cycling-manager/issues/15) race points · [#12](https://github.com/mario595/cycling-manager/issues/12) standings · [#70](https://github.com/mario595/cycling-manager/issues/70) course markers · [#16](https://github.com/mario595/cycling-manager/issues/16) sprint points |
| **Transfers** | [#31](https://github.com/mario595/cycling-manager/issues/31) market value · [#29](https://github.com/mario595/cycling-manager/issues/29) free agents · [#28](https://github.com/mario595/cycling-manager/issues/28) auctions · [#30](https://github.com/mario595/cycling-manager/issues/30) AI teams trade |
| **Riders as assets** | [#1](https://github.com/mario595/cycling-manager/issues/1)/[#57](https://github.com/mario595/cycling-manager/issues/57) attributes · [#58](https://github.com/mario595/cycling-manager/issues/58) growth and decline · [#59](https://github.com/mario595/cycling-manager/issues/59) freshness · [#95](https://github.com/mario595/cycling-manager/issues/95) attribute history · [#96](https://github.com/mario595/cycling-manager/issues/96) rider detail view · [#42](https://github.com/mario595/cycling-manager/issues/42) retirement · [#104](https://github.com/mario595/cycling-manager/issues/104) raced riders are never deleted |
| **Youth** | [#32](https://github.com/mario595/cycling-manager/issues/32) development squad · [#33](https://github.com/mario595/cycling-manager/issues/33) youth intake |
| **Staff and training** | [#35](https://github.com/mario595/cycling-manager/issues/35) trainers · [#36](https://github.com/mario595/cycling-manager/issues/36) weekly training focus |
| **Money** | [#20](https://github.com/mario595/cycling-manager/issues/20) ledger · [#19](https://github.com/mario595/cycling-manager/issues/19) prize money · [#21](https://github.com/mario595/cycling-manager/issues/21) fanbase and merchandise · [#22](https://github.com/mario595/cycling-manager/issues/22) sponsorship · [#23](https://github.com/mario595/cycling-manager/issues/23) sponsor renewal · [#25](https://github.com/mario595/cycling-manager/issues/25) per-rider salaries · [#26](https://github.com/mario595/cycling-manager/issues/26) post-season salary renegotiation · [#69](https://github.com/mario595/cycling-manager/issues/69) trainer fee and salary |
| **Engine performance** | [#101](https://github.com/mario595/cycling-manager/issues/101) cached total_distance · [#102](https://github.com/mario595/cycling-manager/issues/102) death spiral bounded |
| **Screens and plumbing** | [#88](https://github.com/mario595/cycling-manager/issues/88) log slimming · [#94](https://github.com/mario595/cycling-manager/issues/94) watch a race · [#47](https://github.com/mario595/cycling-manager/issues/47) race detail · [#77](https://github.com/mario595/cycling-manager/issues/77) results screen · [#73](https://github.com/mario595/cycling-manager/issues/73) mock UI stripped, login required · [#80](https://github.com/mario595/cycling-manager/issues/80) CI · [#52](https://github.com/mario595/cycling-manager/issues/52) sidebar fix |

**The whole middle of the old roadmap has landed** — the transfer market, the
AI trading in it, youth intake, retirement and salary renegotiation, all since
2026-09-24. A roster is now something a manager builds, sells from, develops
and watches age out, rather than something they were handed.

---

# Part 0 — Rollout: staging, production, beta

Agreed 2026-11-10. **Rollout runs alongside Part 2, and its gates win.**
Each phase is a GitHub milestone: a release gate, i.e. what has to be true
before that phase starts. Milestones are used for nothing else. Labels carry
the domain, the board's Status carries spec → plan → code, and this file
carries order and reasons. Game features (Part 2) get no milestone unless a
beta finding makes one block a phase.

| Milestone | Issues | Why it gates the phase |
|---|---|---|
| **1 — Staging beta (LLM managers)** | [#128](https://github.com/mario595/cycling-manager/issues/128) production-ready image · [#129](https://github.com/mario595/cycling-manager/issues/129) staging world on an accelerated clock · [#136](https://github.com/mario595/cycling-manager/issues/136) provision the host and deploy staging, with CI deploy · [#130](https://github.com/mario595/cycling-manager/issues/130) API tokens and OpenAPI docs · [#131](https://github.com/mario595/cycling-manager/issues/131) report a problem · [#132](https://github.com/mario595/cycling-manager/issues/132) LLM manager harness · [#125](https://github.com/mario595/cycling-manager/issues/125) weekly deficit | Staging runs the **production image** with a single difference, `staging.py` on `MockClock`, advanced so that one game day passes per real hour. A season then lasts about 84 hours, so season closes get exercised several times a week. LLM agents play through the API on a game-time cadence and report through the in-game channel. [#125](https://github.com/mario595/cycling-manager/issues/125) comes first: otherwise every agent reports the same deficit, and in a 3.5-day season teams walk the insolvency ladder before anything else is tested. |
| **2 — Production launch** | [#133](https://github.com/mario595/cycling-manager/issues/133) production deploy | The same image on the **real** clock, as a second compose project on the host [#136](https://github.com/mario595/cycling-manager/issues/136) already proved, with the hourly tick, backups and monitoring live. It follows a clean staging season. The email provider is chosen here, which unblocks [#51](https://github.com/mario595/cycling-manager/issues/51). |
| **3 — Real-time beta (humans and LLMs)** | [#134](https://github.com/mario595/cycling-manager/issues/134) invite-only registration and an agent flag · [#51](https://github.com/mario595/cycling-manager/issues/51) account self-service · [#65](https://github.com/mario595/cycling-manager/issues/65) unique display names · [#137](https://github.com/mario595/cycling-manager/issues/137) Spanish frontend | A few human testers join the LLM managers in the production world. The testers play in Spanish, so the SPA ships with a Spanish catalogue behind an i18n layer, with English kept alongside it for the agents, specs and tests. Humans need to be able to recover a lost password, and names need to be unique once strangers share a table. |
| **4 — The pyramid** | [#10](https://github.com/mario595/cycling-manager/issues/10) · [#11](https://github.com/mario595/cycling-manager/issues/11) · [#13](https://github.com/mario595/cycling-manager/issues/13) · [#14](https://github.com/mario595/cycling-manager/issues/14) · [#56](https://github.com/mario595/cycling-manager/issues/56) | Only makes sense once there are enough players to fill more than one Group, so it follows the beta. Order within it is in 2.4. |

The order inside milestone 1: [#128](https://github.com/mario595/cycling-manager/issues/128) → [#129](https://github.com/mario595/cycling-manager/issues/129) → [#136](https://github.com/mario595/cycling-manager/issues/136) → [#132](https://github.com/mario595/cycling-manager/issues/132), with [#130](https://github.com/mario595/cycling-manager/issues/130) and
[#131](https://github.com/mario595/cycling-manager/issues/131) in parallel, since neither depends on the infrastructure. Bugs found
by the staging agents go into milestone 1 if they block a clean staging season,
and into milestone 3 if they only block humans.

---

# Part 2 — What to build next, in order

## 2.1 — Finish what shipped half-working

Two gaps in features that are live now. Cheap, and both make a shipped system
behave the way it claims to.

| Order | Issue | Why | Blocked by |
|---|---|---|---|
| 1 | [#114](https://github.com/mario595/cycling-manager/issues/114) cancel a claimed team's open listings | **A bug in shipped code, found reviewing [#30](https://github.com/mario595/cycling-manager/issues/30).** A claim withdraws the team's bids but not its listings, so the new manager sees a "their own" listing for a rider no longer on their roster, and AI teams bid the reserve on it — tying up their headroom for up to three days. No money moves wrongly; about one claim in ten hits it. A few lines inside the existing claim transaction. Shipped — see `transfers/README.md`, *Withdrawal and cancellation on claim*. | — |
| 2 | [#34](https://github.com/mario595/cycling-manager/issues/34) promote, retain or discard youth riders | **The development squad is currently a dead end.** [#33](https://github.com/mario595/cycling-manager/issues/33) delivers two riders every four weeks, and nothing moves one onto the senior roster short of closing the squad. It is also the payoff of the hidden-attribute design — triage is a judgement only because potential is hidden — and the thing that gives a scout ([#40](https://github.com/mario595/cycling-manager/issues/40)) something to sell. | [#33](https://github.com/mario595/cycling-manager/issues/33) ✅ · [#29](https://github.com/mario595/cycling-manager/issues/29) ✅ |

## 2.2 — Unmanaged teams stop bleeding

| Order | Issue | Why | Blocked by |
|---|---|---|---|
| 3 | [#45](https://github.com/mario595/cycling-manager/issues/45) unmanaged teams: simple heuristic AI ✅ | **Built** — unmanaged teams pick squads for the course, hire the cheapest affordable trainer, rotate a training focus by roster speciality and sign the steady sponsor. It narrows their loss rather than closing it; see `world/README.md`, *Balances, measured*. Original note: **Moved out of the pyramid block — it now has a clock on it.** `world/README.md` measures it: unmanaged teams pay wages and earn prize money but no sponsorship, so a seeded season 1 leaves the average one with about **$330,000 and roughly three seasons** before AI buying in the market dries up. It names [#45](https://github.com/mario595/cycling-manager/issues/45)'s sponsorship as the fix. [#30](https://github.com/mario595/cycling-manager/issues/30) already covered the market half of this ticket; what remains is squad choice by course, a training focus, a trainer, and signing a sponsor. | [#28](https://github.com/mario595/cycling-manager/issues/28) ✅ · [#36](https://github.com/mario595/cycling-manager/issues/36) ✅ |
| 4 | [#27](https://github.com/mario595/cycling-manager/issues/27) insolvency ladder ✅ | **Built, for managed teams only** — unmanaged teams are excluded until [#45](https://github.com/mario595/cycling-manager/issues/45) gives them income, so that decision no longer gates it. Original note: now fully unblocked — [#28](https://github.com/mario595/cycling-manager/issues/28) gives forced sales somewhere to sell. **Needs one decision it did not have before:** unmanaged teams only spend, so if the ladder applies to them, every one of them eventually walks it. Either it excludes unmanaged teams, or [#45](https://github.com/mario595/cycling-manager/issues/45) lands first so they have income. That is the reason for this order. | [#25](https://github.com/mario595/cycling-manager/issues/25) ✅ · [#62](https://github.com/mario595/cycling-manager/issues/62) ✅ · [#28](https://github.com/mario595/cycling-manager/issues/28) ✅ |

The expiry named for [#45](https://github.com/mario595/cycling-manager/issues/45) was *the first full Season played with real
users*. It is now also an economic one, and every shipped system that rewards
active management — training, youth, the market — widens the gap it closes.

## 2.3 — Racing gets richer

| Order | Issue | Note | Blocked by |
|---|---|---|---|
| 5 | [#17](https://github.com/mario595/cycling-manager/issues/17) mountain points | The twin of [#16](https://github.com/mario595/cycling-manager/issues/16), which shipped on [#70](https://github.com/mario595/cycling-manager/issues/70)'s markers. The mechanism exists; this is the second marker kind. | [#70](https://github.com/mario595/cycling-manager/issues/70) ✅ |
| 6 | [#89](https://github.com/mario595/cycling-manager/issues/89) races have a type, one is a TT | Cheap, and [#9](https://github.com/mario595/cycling-manager/issues/9) probably wants it — real Grand Tours are often decided by a TT stage. Changes no simulation. | [#9](https://github.com/mario595/cycling-manager/issues/9) ✅ |
| 7 | [#18](https://github.com/mario595/cycling-manager/issues/18) classifications | **First feature that makes a squad of specialists worth assembling.** | [#17](https://github.com/mario595/cycling-manager/issues/17) · [#9](https://github.com/mario595/cycling-manager/issues/9) ✅ |
| 8 | [#41](https://github.com/mario595/cycling-manager/issues/41) injuries | Gives the stage-race squad lock its teeth, and the physio ([#40](https://github.com/mario595/cycling-manager/issues/40)) a job. | [#9](https://github.com/mario595/cycling-manager/issues/9) ✅ |
| 9 | [#90](https://github.com/mario595/cycling-manager/issues/90) engine support for a solo effort | **The large one.** Every mechanic that decides a race today assumes a bunch — 221 references to drafting and pack behaviour in `race_engine/`. A TT is the deliberate absence of all of it, and not simply drafting switched off. | [#89](https://github.com/mario595/cycling-manager/issues/89) |
| 10 | [#108](https://github.com/mario595/cycling-manager/issues/108) courses have an altitude | Display only, no simulation change. **One starting altitude, derived from there** — per-segment start/end heights duplicate what gradient and length already encode, so the two can silently disagree. Independent of everything above; fits wherever there is a gap. | — |

## 2.4 — The pyramid

Deferred as a block until there are enough players to fill more than one
Division. Building it now means balancing a structure nobody is in.

| Order | Issue | Blocked by |
|---|---|---|
| 11 | [#10](https://github.com/mario595/cycling-manager/issues/10) Divisions and Groups | [#12](https://github.com/mario595/cycling-manager/issues/12) ✅ (shipped against one Group) |
| 12 | [#11](https://github.com/mario595/cycling-manager/issues/11) opening a Division | [#10](https://github.com/mario595/cycling-manager/issues/10) |
| 13 | [#13](https://github.com/mario595/cycling-manager/issues/13) promotion and relegation | [#10](https://github.com/mario595/cycling-manager/issues/10) · **[#45](https://github.com/mario595/cycling-manager/issues/45)** |
| 14 | [#14](https://github.com/mario595/cycling-manager/issues/14) which Division a new player lands in | [#11](https://github.com/mario595/cycling-manager/issues/11) |
| 15 | [#56](https://github.com/mario595/cycling-manager/issues/56) team code collisions | [#11](https://github.com/mario595/cycling-manager/issues/11) |

**[#13](https://github.com/mario595/cycling-manager/issues/13) is meaningless without [#45](https://github.com/mario595/cycling-manager/issues/45).** Unmanaged teams that never improve
put every human team above every unmanaged one, and teams move by headcount
rather than merit.

---

# Part 3 — Deferred, with reasons

| Issue | Why it waits |
|---|---|
| [#38](https://github.com/mario595/cycling-manager/issues/38) team tactics | Still unsizeable, and the most expensive item on the board: new in-race inputs invalidate the audited six-course realism balance. Needs its own spec session before it can be estimated at all. |
| [#40](https://github.com/mario595/cycling-manager/issues/40) physio and scout | **Split in readiness now.** The scout is close — [#34](https://github.com/mario595/cycling-manager/issues/34) is what it sells information into, and the market ([#28](https://github.com/mario595/cycling-manager/issues/28)) exists. The physio still needs injuries ([#41](https://github.com/mario595/cycling-manager/issues/41)). Worth splitting when [#34](https://github.com/mario595/cycling-manager/issues/34) lands rather than waiting for both. |
| [#43](https://github.com/mario595/cycling-manager/issues/43) season awards and history | Cheap, and mostly what makes a long-running world feel like it has a past. Wants several Seasons to have happened first. |
| [#51](https://github.com/mario595/cycling-manager/issues/51) account self-service | **Revisit before any playtest with real users who can lock themselves out.** Drags in email delivery — a deployment and cost decision, and deployment is still TBD. |
| [#65](https://github.com/mario595/cycling-manager/issues/65) unique display names | Small, no dependencies, genuinely low priority. Grab it in a lull. |
| [#8](https://github.com/mario595/cycling-manager/issues/8) admin season tool | A file loaded by a command already declares a season. A purpose-built editor for one admin is premature. |
| [#24](https://github.com/mario595/cycling-manager/issues/24) merchandising investment | Explicitly deferred in its own ticket — a decision about a spreadsheet rather than about bike racing. |
| [#109](https://github.com/mario595/cycling-manager/issues/109) altitude tolerance attribute | Depends on [#108](https://github.com/mario595/cycling-manager/issues/108), and carries the same in-race attribute cost as the rest: a full re-derivation of the six-course realism balance. **Worthless until courses actually go high enough for it to bite**, so mountainous courses must exist first. Open: public or hidden — **visible is probably the honest answer**, since twelve-week seasons with a handful of mountain races give a player too little to infer it from. |
| [#110](https://github.com/mario595/cycling-manager/issues/110) altitude training | Depends on [#109](https://github.com/mario595/cycling-manager/issues/109). **Where it lives is the open question:** the off-season week already carries promotion/relegation, contracts and salary reviews, while a focus option on the shipped weekly training ([#36](https://github.com/mario595/cycling-manager/issues/36)) reuses a system that exists. Unless the off-season is being deliberately built into a phase with its own decisions. **Settle that first; it changes the ticket's shape.** |
| [#91](https://github.com/mario595/cycling-manager/issues/91) time-trialling attribute | Last stage of [#2](https://github.com/mario595/cycling-manager/issues/2), and **may prove unnecessary** — a time trial might be adequately decided by the existing `flat` and `resistance`. Test that before paying for a sixth in-race attribute. |
| [#3](https://github.com/mario595/cycling-manager/issues/3), [#4](https://github.com/mario595/cycling-manager/issues/4) new rider attributes | Each is an *in-race* attribute, so each costs a re-derivation of the six-course balance. Judged individually, never added by default. |

---

# Dependency summary

The chains that still constrain order:

```
#30 AI market ✅ ──→ #114 claim cancels listings ✅

#33 intake ✅ ──→ #34 triage ──→ (#40 scout)

#28 market ✅ ──→ #45 heuristic AI ✅ ─┬──→ #27 insolvency ✅ (managed teams only; unmanaged wait for #45)
                                    └──→ #13 promotion/relegation ←── #10

#70 markers ✅ ──→ #16 sprint ✅ / #17 mountain ──┐
#9 stage races ✅ ────────────────────────────────┴──→ #18 classifications
    ├──→ #41 injuries ──→ (#40 physio)
    └──→ #89 race types ──→ #90 TT engine ──→ (#91 TT attribute)

#108 altitude (display) ──→ #109 tolerance attribute ──→ #110 altitude training

#10 Divisions ──→ #11 ──→ #14, #56
```

**One ticket now unblocks disproportionately:**

- **[#45](https://github.com/mario595/cycling-manager/issues/45) heuristic AI** gates insolvency and promotion/relegation, and is on
  an economic clock of its own.

**[#9](https://github.com/mario595/cycling-manager/issues/9) stage races shipped** — see `racing/README.md` and
`competitions/README.md`, *Stage races* — unblocking classifications, injuries,
race types and through them the physio, time trials and the TT attribute.

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
