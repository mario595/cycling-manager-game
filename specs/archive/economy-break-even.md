# Economy: the average team breaks even

**Status:** implemented
**Issue:** #125
**Domain(s):** `economy/`, `competitions/`, `world/`
**One-liner:** A team that races about as well as the field average, with a sponsor and a trainer, ends a season slightly ahead instead of steadily losing money.

## Why this exists

Today every team loses money by default. In a settled season the average team
pays about $14,000 a week in wages and about $2,500 for a trainer, and earns
about $8,400 in prize money, about $4,250 from a steady sponsor and about $400
from merchandise. That comes to roughly $40,000 lost per season, whatever the
manager does. Over enough seasons the insolvency ladder reads as a clock
counting down for everyone, not as the consequence of bad management.

Most of all, this blocks the staging beta. In a 3.5-day accelerated season,
every LLM manager would report the same deficit, and teams would start walking
the insolvency ladder before anything else got tested. With this change the
money tells a manager how well they are doing. Racing well pays, racing
averagely breaks even, and racing badly slowly costs money.

## Player experience

A new manager claims a team and signs a sponsor. The three offers on the
Sponsors screen are noticeably larger than they used to be, and they still
differ in the same way: the steady sponsor pays a flat amount, and the
results-hungry one swings with results. Prize money for a top-ten finish is a
little bigger too.

Through the season the Finances screen shows weeks that go up and weeks that
go down. Wages and the trainer go out every week. Prize money arrives in race
weeks, and the sponsor's payment arrives every week. A manager whose riders
finish around the middle of the field ends the season slightly ahead. A
manager who wins often ends it clearly ahead, with money to spend on a
development squad or a signing. A manager whose team finishes near the back
ends it somewhat behind. If that goes on season after season, the team drifts
toward insolvency, which is a consequence of how it raced and not of a pricing
mistake.

No new screens, controls or messages exist. The change shows only in the
numbers.

## In scope

1. In a settled season, the average team (a steady sponsor, the cheapest
   trainer available to it, no development squad, no transfer activity) ends
   the season roughly flat to slightly ahead: about $10,000 to $20,000 up.
2. The top quarter of the field ends a season with a clear profit, several
   times the average team's surplus.
3. The bottom quarter ends a season behind, but by little enough that it takes
   several seasons to burn through a starting balance, not one or two.
4. Sponsor offers are larger, and all three offer types grow together, so the
   choice between steady, performance-driven and results-hungry is the same
   trade-off as before.
5. Prize money for placings is larger, so results matter more in money terms
   than they did, but most of the new income comes from sponsorship, which every
   team gets.
6. Rider wages, merchandise, trainer costs, development squad prices and the
   starting balance are unchanged.
7. The result is checked by a repeatable measurement: two seeded seasons on the
   accelerated clock, reporting the average team and the top and bottom
   quarters. A future balance change can re-run it against the same targets.
8. The documented balance figures in the game's docs, which are stale today,
   are replaced with the new measurement, and the targets above are written
   down beside them.

## Out of scope

- **Cutting wages.** Rejected. It would reprice every rider at the next season
  close and change every Finances screen, and raising income gives fanbase more
  weight as well.
- **Merchandise.** It stays as it is. One lever too many for this ticket.
- **A "weeks of money left" projection** on the Finances screen. A separate
  feature, for later.
- **Development squad prices.** Unchanged. They become a little cheaper in
  relative terms, which is accepted.
- **A flat weekly top-up for every team.** No. It would hide the deficit, not
  fix it.
- **Insolvency for unmanaged teams.** Still not assessed. It belongs with the
  pyramid or a later ticket.
- **Prize money that scales with the number of teams.** Deferred to the
  pyramid (see below).

## Rules and edge cases

- **Signed contracts keep their terms.** A sponsor contract signed before the
  change goes on paying what it promised. Only offers generated after the
  change are larger.
- **Prize money already paid is not topped up.** Only races finished after the
  change pay the new amounts.
- **Rider salaries are untouched**, so the season-close salary review behaves
  exactly as before.
- **The staging world starts fresh,** so none of the above applies to it. It
  matters only for an existing development database.
- **Unmanaged teams** get the same new numbers. They always sign the steady
  sponsor, so they sit at or slightly below the average and should no longer
  drain over the long run.
- **The prize pot is shared.** Prize money is a fixed amount per race split by
  placing, so if the field grows, each team's average share shrinks. The
  targets above hold for a field of about the size the seed creates today
  (sixteen teams).

## Decisions taken

- **Who breaks even:** the average team, with a steady sponsor and the
  cheapest trainer, ends a season slightly ahead. Top teams profit, and bottom
  teams lose slowly.
- **Where the money comes from:** raised income, not cut wages.
- **Balance between sponsors and prizes:** most of the increase goes to
  sponsorship and a smaller part to prizes, so the gap between strong and weak
  teams widens a little, not a lot.
- **Merchandise:** left alone.
- **Optional spends** (development squad, transfers): not covered by break-even.
  They are funded by racing above average or by spending the starting balance.
- **Existing worlds:** only new offers and new races use the new numbers.
  Nothing is paid retroactively.

## Open questions

None.

## Deferred

- **Prize money for the pyramid.** More teams share the pot, so prizes will
  need re-tuning when divisions arrive.
- **Merchandise as a real income source.** Only worth it once there is a
  player lever on fanbase.
- **Insolvency for unmanaged teams.** Revisit once the economy has been seen
  holding steady in staging.
