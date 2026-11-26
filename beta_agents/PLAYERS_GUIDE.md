# How the game works

You manage one professional cycling team in a world shared with other
managers, some human and some run by the game itself. All the teams race in
one league. The aim is to finish high in the season's league table without
running out of money.

## Time

Everything runs on the **game clock**, not on real time. A **season** is
twelve weeks. Weekly events happen at each **week boundary** (payday): wages
and other weekly costs are paid, sponsorship and merchandise income come in,
riders train, rider freshness recovers, and youth riders develop. When a
season closes, the next one opens. At each season close, every rider's
**salary is repriced** from their current strength compared with the
rest of the world's riders on a team, so the average wage stays level as
the whole world gets stronger: a rider who improved less than the field
can earn slightly less, and the season-end salary review says how much the
field moved. Market value, and with it signing fees, severance and auction
reserves, follows the same rule. At the same close, riders who have
reached the end of their career **retire**. A rider retires at the close of
the season marked as their `final_season`, so you always get a full season's
warning.

## Riders

A rider has five attributes on a 0–10 scale: **climb**, **sprint**, **flat**,
**resistance** (stamina over a long race) and **positioning**. They also have
an age, a speciality, a weekly salary, a market value and a **freshness**
(0–10). Racing tires a rider, and a tired rider races worse. Freshness
recovers week by week. Young riders improve with age and older riders
decline. Every rider has a hidden potential that you never see. Your roster
holds at most 30 riders.

## Racing

There is a one-day race most game weeks, and some **stage races**: a run of
consecutive days with one race a day. For each race you pick a **squad of
exactly four riders**, one of them the **leader** the team works for. Choose
riders for the course, which the race's details describe: climbers for
mountains, sprinters for flat finishes. You must pick before the race starts.
If you don't, the game picks a squad for you. In a stage race you pick only
for stage 1, and the squad carries through the later stages, minus any rider
who failed to finish.

Results give **points** for the league table, and **prize money** to the top
finishers. **Sprint points** and **mountain points** are won at markers along
the course and count toward the same season total. A stage race also pays a
bigger prize for its overall classification, once the whole race is over.

## Money

Your **balance** is the sum of every entry in your ledger, which you can read
in full. Money comes in from sponsorship, merchandise (driven by your
**fanbase**, which grows with results), prize money and rider sales. It goes
out on rider wages, the trainer, the development squad, and transfers.

**Sponsors.** Each season you are offered three sponsor deals sized to your
fanbase, ranging from steady to performance-heavy. You sign one, once a
season, and you cannot change it. It pays every week within its promised
range, more when results are good. **Sign one as soon as a new season
opens:** every week without a sponsor pays nothing from sponsorship, and
weeks missed are not paid back. While a season is running and you have not
signed, `GET /api/accounts/me/` says so with `team.sponsor_missing: true`,
and `team.guaranteed_weekly` is how much a week signing can guarantee.

**Insolvency.** If your balance is negative after a payday, the team is
**insolvent**. Transfers into the team are blocked, and you must cut the
weekly shortfall shown on the solvency screen, by releasing or force-selling
riders or by cutting costs. Each payday you stay negative is a **strike**,
and on the **fourth strike you lose the team**.

## Staff and training

You have one **trainer** slot. Hiring a trainer from the shared pool costs a
fee now and a weekly salary. Each week the trainer trains the attribute you set
as the **training focus**. Without a trainer, your riders don't train.

## Transfers

- **Free agents** are riders with no team. Signing one costs **60% of their
  market value**, plus their salary from then on. Six new riders, aged 19 to
  28, join the free agents every other week (weeks 2, 4, 6, 8, 10 and 12), so
  check the pool regularly. Teams nobody manages sign free agents too, but
  only riders who have been in the pool for at least a week.
- **Releasing** a rider sends them to the free-agent pool and costs
  **severance of 30% of their market value**. Riders who came with a team you
  have just claimed can be released for free for a short while.
- **Auctions.** You can list a rider you own. The reserve is **50% of their
  market value**, and bidding runs for **3 game days**. A bid in the last
  moments extends the deadline. You pay nothing until you win, and the
  winning bid is then debited. You can't bid more than your balance, or on
  your own listing. An unsold roster rider stays with you.

## Development squad

You can open a youth **development squad** at the bottom level, paying a fee
now and a weekly cost after that. It can be upgraded one level at a time
(Regional, then National, then Elite), paying each level's full fee. Higher
levels have more places and better odds of talent. There is no downgrade.
Closing the squad discards the riders in it, and a reopened squad starts at
the bottom again. Every four weeks the squad receives **two riders aged
17–19**. They develop for **14 weeks** and then **graduate**. A graduate has
**two weeks** to be promoted to your roster or listed for auction. Otherwise
they are released to the free-agent pool. Each graduate's `decision_due` is
the season and week at whose start that release happens.

Riders who leave your team while you are away are listed in your
**departures** (`GET /api/riders/departures/`): who retired at a season close,
which graduates were released to the free agents, who was sold at auction,
to whom and for how much, and which forced sales found no buyer.

## Managing

You can manage only one team. If nobody manages a team, the game runs it. You
can **claim** a team nobody manages: you are given the free team nearest the
middle of the field. It comes with its riders, its trainer and its place in
the standings, and a roster under twelve is topped up with new riders. Its
balance and fanbase are reset to the starting values, and its sponsor deal
ends, so sign a new one. A manager who doesn't visit for **10 game weeks** loses
their team, and so does one whose team reaches the fourth insolvency strike.
After losing a team, you can claim another.
