# Sponsorship contracts

**Status:** implemented
**Domain(s):** `economy/`
**One-liner:** a manager picks one of three sponsor offers each season, trading
a steady weekly payment against a bigger one that swings with results.

## Why this exists

Money only leaves a team today. `#20` built the ledger and its wage bill,
`#21` gave it a first income (merchandise, paid off a team's fanbase), and
this is the third and largest income stream `specs/roadmap.md` scopes for
the economy's first circuit. Prize money (`#19`) rewards a single race;
sponsorship is the reliable, season-long base a team's budget is actually
built on.

The two-line ticket asked for a fixed payment known at signing. In
discussion, that was replaced with something more interesting: sponsors
differ in how much of their money is guaranteed versus tied to how the team
performs. This makes signing a real bet on the season ahead, not a "pick the
biggest number" dropdown — **this spec supersedes the ticket's "fixed weekly
payment, unchanged for the season" line.**

## Player experience

Before a season starts — or the moment a manager claims a team mid-season —
three companies want to sponsor the team. Each is shown as a card: a weekly
baseline payment, a one-line character ("steady," "performance-driven,"
"pays big for big results"), a low–high range for what a bad or a great week
actually pays, and the contract's length. A team with a bigger fanbase sees
bigger numbers across all three cards — sponsors want to be seen on a
popular jersey.

The manager reads the three side by side and picks one, or signs none. A
cautious manager rebuilding a squad takes the steady, lower offer. A manager
confident in a strong roster and a good calendar takes the volatile one,
betting the highs outweigh the lows. There's no wrong answer visible on the
card alone — that's the point.

Once signed, "Sponsorship" appears as its own line in the team's weekly
financial history, next to wages and merchandise. The amount moves week to
week with how the team raced, staying within the range the offer promised,
never dropping catastrophically even on a bad week. A quiet week with no
scored points — the off-season week, or a squad that came home empty-handed —
pays the baseline, not zero.

The contract runs for the rest of the season and cannot be broken, renewed
early, or swapped. A manager who signs and then goes on a losing streak
lives with the sponsor they picked; a manager who declines all three simply
has no sponsorship income and no penalty beyond that. If the team changes
hands mid-season — claimed fresh by a new manager — any existing contract
ends there, and the new manager is offered three fresh contracts of their
own, priced for the weeks that remain.

## In scope

1. Three sponsor offers are generated for a team at season start, and again
   whenever the team is claimed by a manager.
2. Each offer displays: a weekly baseline payment, a plain-language
   character description of how much it swings with results, a low–high
   weekly range, and the contract's length (season, or remaining weeks on a
   mid-season claim).
3. Offer size — baseline and range alike — scales with the team's current
   fanbase: a bigger fanbase produces bigger offers across all three cards.
4. A manager signs at most one of the three offers. Signing is optional.
5. A team with no signed sponsor receives no sponsorship income and suffers
   no other consequence.
6. Once signed, the weekly sponsorship payment varies with that week's race
   results, staying within the signed offer's stated range.
7. A week in which the team scored no points (an off-season week, or a
   squad that raced and scored nothing) pays the offer's baseline for that
   week, not zero.
8. However a demanding, high-swing contract computes a bad week, the
   payment never falls below a floor fraction of that offer's baseline —
   stated to the player as part of the offer's range, not a hidden rule.
9. The contract is fixed for its full term: no early exit, no
   renegotiation, no switching sponsors mid-contract.
10. Sponsorship income appears in the team's financial history as its own
    line, distinguishable from wages and merchandise.
11. Claiming a team — whether it was previously unmanaged or had a
    different manager — ends any sponsorship contract already in force and
    immediately offers the new manager three fresh offers, as in the
    season-start case, priced for the season's remaining weeks.

## Out of scope

- **More than one sponsor per team.** Considered and rejected: a
  main-plus-secondary structure doubles every rule here (generation,
  signing, weekly payment, mid-season resets) for a decision that would
  just collapse to "sign both." One slot is already a meaningful budget
  commitment at this scale. **No.**
- **Sponsor-imposed conditions on team behaviour** — racing specific riders,
  entering specific races, avoiding certain outcomes. The most flavourful
  version of this idea, and the one with no supporting machinery: there is
  no race-entry choice and no tactics system to hook a condition to (`#38`
  is explicitly unsized for exactly this reason). **No**, not until those
  exist.
- **A considered decline.** All three offers can simply be ignored, with
  the same "no income" outcome as running out the clock. There is no "wait
  for a better round" — offers are generated once per season-boundary
  event, not on a rolling market. **No.**
- **Sponsor renewal at season end (`#23`).** Whether the same company
  re-offers, and at what price, stays its own ticket. It is now narrower
  than originally scoped: this spec already makes in-season payment
  performance-sensitive, so `#23` only has to decide what happens *between*
  seasons, not invent that mechanic. **Later**, and it needs a completed
  season to design against sensibly.
- **A visible payroll/income rollup** on the finances screen, summing
  sponsorship with wages and merchandise. Each stays its own line; a total
  is presentation on top, the same deferral `#69`'s trainer salary spec
  made. **Later.**
- **Division-tailored offers.** The backlog flagged this as open; fanbase
  is the single number sponsors already read for merchandise (`#21`), and
  keeping sponsorship on the same number avoids a second, competing measure
  of team stature. **No** for now — revisit only if same-fanbase teams in
  different Divisions feel like they should be treated differently once
  there's a second Division to compare against (`#10`).
- **Sponsorship for AI/unmanaged teams.** They do not make any economic
  decisions yet (matches `#69`'s trainer spec deferring the same for
  trainers) — belongs to `#45`. **Later**, gated on `#45`.

## Rules and edge cases

- Offer sizing reads the team's fanbase at the moment offers are generated.
  Fanbase moving after signing does not reprice an existing contract — only
  a fresh offer round (next season, or a new claim) sees the new number.
- The three offers on one card span a range of character, from steady and
  lower-paying to volatile and higher-paying, so the choice is never
  three near-identical cards.
- A signed contract's weekly payment is bounded on both sides by the range
  shown at signing: it can spike toward the top on a strong week, but a
  demanding sponsor's floor keeps a bad week from paying near nothing. The
  floor is a player-facing guarantee, not a hidden implementation detail.
- The season's off-season week, and any week where the team scored zero
  points from racing, pays the contract's baseline — the payment mechanism
  needs a defined result for "no signal that week," and baseline is it.
- A team with no sponsor produces no sponsorship line in that week's
  history — not a zero-amount row — matching how trainer salary already
  treats an unfilled slot.
- Claiming a team always ends whatever sponsorship situation it was in
  (contract or none) and starts a fresh offer round. This applies the same
  way regardless of whether the team was unmanaged or had a previous
  manager — claiming already resets balance and fanbase the same way
  (`teams/README.md`'s takeover entries); sponsorship resetting alongside
  them keeps one consistent rule for what claiming does to a team's
  finances, rather than a special case.
- A contract cannot be renegotiated, extended, or broken early by either
  side once signed. The only way a contract changes is the season ending or
  the team being claimed by someone else.

## Decisions taken

- Payment is not fixed, despite the ticket's wording — it swings with
  weekly results within a stated range, because a flat number makes signing
  a non-decision (pick the biggest). This is the central change this spec
  makes to the ticket as filed.
- Offer size (baseline and range) is driven by team fanbase, not by
  Division position — matches the backlog's decision taken under `#21`
  that fanbase is the one prestige number the economy reads from.
- Exactly one sponsor slot, not several — keeps the decision meaningful
  instead of "sign everything available."
- A downside floor on a demanding sponsor's payment is in scope as a
  player-facing rule, specifically to blunt the compounding risk raised
  below (a struggling team should not also lose sponsor income on top of
  everything else going wrong) — the upside is deliberately left
  uncapped, since a hot streak paying out big is the reward this contract
  type is selling.
- A scoreless week pays baseline rather than zero or the prior week's
  value — the simplest well-defined fallback, and consistent with races
  happening most weeks so this stays a true edge case rather than a
  frequent one.
- Claiming a team resets sponsorship the same way it already resets balance
  and fanbase, rather than carrying a contract over to a new manager who
  never agreed to it.
- `#23` (renewal) stays a separate ticket, now narrower given payment is
  already performance-sensitive within a season.

## Open questions

- **The exact formula translating weekly results into a payment within the
  signed range** — left to the implementation plan. Flagged here as a
  design risk: sponsorship (biggest stream), prize money (`#19`), and
  fanbase (`#21`) all move in the same direction with good results, so a
  strong team's income compounds from three sources at once. Nothing in
  this spec solves that; it should be watched once a season is actually
  played, and the plan should say what "relative to" means for computing
  swing (the team's own recent form vs. the field) since that choice
  affects whether a struggling team can claw back with a single good race.
- **How income is computed given `economy/` may not import `competitions/`**
  (`AGENTS.md`'s dependency graph) — `apply_weekly_fanbase` already takes
  points as an injected argument from `world/` rather than querying
  `RacePoints` directly; the implementation plan should follow the same
  pattern for sponsorship's weekly payment. Not a product question, noted
  here so the plan doesn't have to rediscover it.

## Deferred

- `#23` sponsor renewal at season end — needs a completed season to design
  against, and is now a narrower decision than before this spec.
- A visible payroll/income rollup on the finances screen — presentation,
  once there are enough income/expense lines to make summing them useful.
- Division-tailored offers — no second Division exists yet to compare
  against.
- Sponsorship for AI/unmanaged teams — gated on `#45`.
