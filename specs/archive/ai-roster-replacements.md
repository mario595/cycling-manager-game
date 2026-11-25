# Replacement riders for unmanaged teams

**Status:** implemented
**Domain(s):** world
**One-liner:** At each season close, a team nobody manages gets young riders back up to a full roster, so retirements stop emptying the AI's side of the transfer market.

Issue: #157.

## Why this exists

The trader beta tester checked the auction market on every visit from season 2 week 11 to season 4 week 6 and never saw an AI listing. AI teams were listing as designed in season 1, but the rule that lets them list keeps every roster at 10 riders or more after a sale, and nothing ever gave an unmanaged team a rider back. Retirement (#42) takes about one rider a season from each team; the AI does not sign free agents (deferred in #30 until retirement existed), a fresh world has no free agents anyway, and the AI only buys from humans. A local run of the staging world took AI rosters from 12 to between 9 and 12 at the first season close. By season 4 almost no AI team could list, and a few seasons later AI teams could no longer field a full squad.

## Player experience

A player never sees the top-up happen. They see an auction market where teams they do not compete with keep putting veterans up for sale, season after season, and AI teams that keep racing with full squads. A player browsing an AI team's roster after a season close may notice a couple of new young names where retired veterans used to be.

## Rules

1. At each season close, after the season's retirements, every unmanaged team with fewer than 12 riders gets one new rider for each missing place.
2. Each new rider is of the speciality the team is shortest of at that moment, so a retired climber tends to be replaced by a climber.
3. New riders are aged 19 to 23, with quality rolled like any other generated rider's. They are fresh faces, not guaranteed stars.
4. They cost the team nothing to acquire, like the roster a seeded team starts with. Their wages are paid from the next payday like everyone else's.
5. A team with 12 riders or more is left alone. A managed team is never topped up: a human replaces riders through the market and the development squad.
6. Only at the season close. A rider an AI team sells mid-season is not replaced until the close, so selling to a human never hands the AI a free rider.

## Out of scope

- **AI teams signing free agents.** Still deferred: a fresh world has no free agents, so it would not have fixed this.
- **AI teams running a development squad.** Truer to the rules, but much bigger and costs them money. Mario chose the simpler top-up (2026-11-25).
- **Loosening the listing rule** (letting AI teams list below 10 riders). It would only postpone the problem while rosters kept shrinking.
- **When AI listings appear during the week.** All AI listings open at the week boundary and an auction lasts three game days, so on the 24× staging clock they are open for 3 of every 7 real hours. A visit can still find the market empty. Noted on the PR as a possible follow-up.
