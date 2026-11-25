# Free-agent intake, and unmanaged teams signing from it

**Status:** implemented
**Domain(s):** riders, world, transfers
**One-liner:** New riders join the free-agent pool every other week, and teams nobody manages sign from it to replace their retirees, so the AI keeps a full roster and keeps selling at auction.

Issue: #157.

## Why this exists

The trader beta tester checked the auction market on every visit from season 2 week 11 to season 4 week 6 and never saw an AI listing. AI teams listed as designed in season 1, but they only list while a sale leaves them at least 10 riders, and nothing ever gave an unmanaged team a rider back. Retirement (#42) takes about one rider a season from each team. The AI did not sign free agents (deferred in #30 until retirement existed), and there was nobody to sign anyway: the pool filled only when a rider left a team, so a fresh world's pool was empty. A local run of the staging world took AI rosters from 12 to between 9 and 12 at the first season close, with the pool still empty. By season 4 almost no AI team could list, and a few seasons later AI teams could not have fielded a full squad.

## Player experience

Every other week, six new riders appear among the free agents. Most are ordinary, a few are worth signing. A manager who checks the pool regularly gets first pick: a new arrival is theirs alone for a week. After that, teams nobody manages may sign them, one rider per team per week, if they are short of a full roster of 12. Riders nobody signs within eight weeks and who are among the weakest in the pool leave it, as before.

Players see AI teams keep full rosters season after season, and keep putting surplus and ageing riders up for auction.

## Rules

1. Every other week of a season (weeks 2, 4, 6, 8, 10 and 12), six new riders join the free-agent pool. They are aged 19 to 28, of any speciality, with quality rolled like any other generated rider.
2. They count as unattached from the week they arrive, so the existing expiry rule (eight in-season weeks unsigned, bottom 20% of the pool by value) applies to them like anyone else.
3. Each week, every unmanaged team with fewer than 12 riders may sign one free agent. The teams with the fewest riders go first.
4. An unmanaged team signs only riders under 33, who have been in the pool since before that week began, and whose signing fee fits within half its balance (less what its winning auction bids already promise). It prefers the speciality it has fewest of, then the strongest rider.
5. An AI signing costs the same 60% signing fee a human pays.
6. Managed teams are never signed for: a human chooses their own riders.

## Decisions

- **Intake into the shared pool, not riders handed straight to AI teams.** First built as replacements generated at each season close for unmanaged teams only. Mario preferred a periodic free-agent intake that humans and AI both draw from (2026-11-25), since expiry already removes the riders nobody wants.
- **Every other week, six riders.** Mario offered weekly or every two weeks. Thirty-six a season is about twice what retirement takes from a 16-team world, so AI teams can fill their gaps and humans still have a choice.
- **A week's head start for humans**, so the AI never takes the best new arrival in the same tick it appears.

## Out of scope

- **AI teams running a development squad.**
- **Loosening the listing rule** (letting AI teams list below 10 riders). It would only postpone the problem.
- **When AI listings appear during the week.** All AI listings open at the week boundary and an auction lasts three game days, so on the 24× staging clock they are open for 3 of every 7 real hours. Noted on the PR as a possible follow-up.
