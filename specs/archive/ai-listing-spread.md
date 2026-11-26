# AI listings spread across the week

**Status:** implemented
**Domain(s):** world, transfers
**One-liner:** Teams nobody manages put riders up for auction on different days of the week, and sell a little more than just their veterans, so a manager who opens the transfer market usually finds AI riders for sale.

Issue: #172.

## Why this exists

Every AI auction opens on the first day of a week and lasts three game days. For the other four days of every week the market holds no AI riders at all. On staging's fast clock that leaves AI listings live for about three hours in every seven, and the beta testers keep visiting an empty market. In real time the same thing happens over a week: a flurry of listings on Monday, nothing from Thursday to Sunday.

The second half of the problem is what the AI is willing to sell. Since the free-agent intake (#157) keeps AI rosters at twelve, an AI team only sells a veteran of 33 or more who isn't among its best two of their speciality. A team whose turn comes round often has nobody like that, so it lists nothing.

## Player experience

A manager opens the transfer market on any day of the week and usually finds a few AI riders up for auction, some opened today, some yesterday, some ending soon. Most are still veterans, but some are younger riders an AI team has more of than it needs: a third climber, a fourth sprinter. Nothing about how an auction runs changes. It still lasts three game days, bidding works as before, and the market is no busier over a month than it was. The same listings are just spread out instead of arriving in one batch.

## In scope

1. Each unmanaged team has its own listing day inside its four-week turn, so AI listings open on every day of the week rather than all on the first.
2. Each unmanaged team still lists at most one rider per four-week turn, and still never has two open listings at once.
3. If a team's listing day passes while the world isn't ticking (a catch-up, or the server down), the team lists once when the world catches up within that same week, not once per missed day.
4. If a team has nothing it is willing to sell on its day, it may still list later in the same week if that changes. It never lists in a week that isn't its turn.
5. An unmanaged team may also sell a rider who is third-best or lower in a speciality where it has at least three riders, after first considering its surplus and its veterans. It keeps at least ten riders, as today.
6. Auctions stay on game time, with the same three-day length and the same rules for everyone.

## Out of scope

- **A minimum number of AI listings on the market.** Proposed, and rejected by Mario (2026-11-26): no team lists early to fill a quiet market.
- **A message when the market has no AI listings.** No: the aim is that this rarely happens.
- **Longer auctions.** No: it would slow human sales too, and the problem is when listings open, not how long they last.
- **More listings per team.** Later, if spreading the same number still feels thin.
- **AI teams trading with each other.** Unchanged: the AI only bids on human listings.

## Rules and edge cases

- A team's listing day is fixed. It does not move from one turn to the next, so the pattern is predictable to the team, and teams sharing a turn get different days.
- The widening in rule 5 only reaches riders outside a team's best two of their speciality, so an AI team still never sells a rider it would itself want to buy.
- A team that sells a depth rider drops below twelve and signs a free agent the following week (#157). The market sees a little more movement and the free-agent pool drains a little faster. That is accepted.
- The relisting cooldown still applies: a rider who went unsold isn't put up again for four weeks.
- Managed teams are untouched: a human decides what they sell.

## Decisions taken

- Spread listings, rather than lengthen auctions: spread (Mario, 2026-11-26).
- Keep each team at most one listing per four weeks: yes.
- A minimum number of open AI listings: no.
- Let AI teams sell a depth rider of a speciality they have plenty of: yes, keeping at least ten riders.
- Show something when the market has no AI listings: no.

## Open questions

None.

## Deferred

- Listing more often per team: wait to see whether spreading alone fills the market.
