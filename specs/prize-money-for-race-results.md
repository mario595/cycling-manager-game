# Prize money for race results

**Status:** proposed
**Domain(s):** `economy`, `competitions`, `racing`
**One-liner:** Finishing in the top 10 of a race pays a team real money, on the same table every race, the moment the race is scored.

## Why this exists

Every balance in the game currently only goes down — the ledger (#20) charges
wages every week and nothing has ever paid in. Prize money is the game's
first *instant* income: unlike fanbase-driven merchandise (#21), which
deliberately lags a week's results, and sponsorship (#22/#23), which is fixed
for a season, prize money lands the moment a race finishes and is won or lost
on that result alone. It is also the most obvious of the three, since results
and points already exist — a manager who finishes 3rd already sees points on
the standings table; this ticket makes that same result put money in the
account.

## Player experience

Before a race is run, a manager looking at it sees what it pays: a table
naming each of the ten paying positions and the amount that position is
worth, the same table for every race on the calendar. It reads like a race's
prize list always has — known in advance, independent of who shows up to
race it.

Once the race has been simulated, that same information reappears next to
the result, in the same place a manager already looks to see what a result
was worth in points. A team that put two riders into the top 10 sees both
positions' money, the same way it would see both positions' points. A team
that finished 11th or worse — or whose whole squad abandoned — sees nothing
there, the same way it scores no points.

Separately, in the team's financial history, a manager sees a dated line for
each rider who placed — "Prize money — <race name>," sitting alongside
"Weekly wages" the same way any two entries in that history do. Two riders
placing in the same race means two lines, not one combined figure, so the
history reads the same way the result does.

A team with no manager still races, still places, and still gets paid —
prize money does not check who, if anyone, is running the team. If that team
is later claimed, the claim's balance reset wipes any prize money it earned
while unmanaged, the same way it already wipes everything else.

## In scope

1. A race that finishes pays out to every team with a rider in the top 10
   classified finishing positions, by the same fixed table for every race —
   no race pays more or less than any other.
2. The payout table has the same shape as the points table: ten paying
   positions, nothing below 10th.
3. A team with more than one rider in the top 10 is paid for each of them
   separately — prize money does not reduce a team to its best finisher the
   way points do.
4. A rider who did not finish the race is never paid, regardless of the
   position they were numbered.
5. A rider with no team is never paid.
6. An unmanaged team is paid exactly as a managed one is.
7. Once a race has paid out, running the payout again for the same race
   changes nothing — a race is paid exactly once, however many times the
   system revisits it.
8. What a race already paid, or will pay, is never changed by a later
   change to the payout table. A race keeps what it was worth when it
   finished.
9. A manager can see the payout table for a race before it has run.
10. A manager can see what each placed team actually earned once the race
    has run, presented the way that race's points are already presented.
11. A manager can see each prize as its own dated entry in their team's
    financial history, naming the race it came from.
12. Claiming an unmanaged team clears any prize money it earned while
    unmanaged, the same moment and for the same reason the balance and (once
    #21 ships) fanbase reset does.

## Out of scope

- **Classification payouts.** Points classifications (#18) don't exist yet
  and are blocked behind #16, #17 and #9. There is nothing to pay out on.
  When #18 ships, it will need to say whether it pays and how much — this
  ticket does not pre-decide that.
- **Stage races: per-stage vs. overall payouts.** Stage races (#9) don't
  exist yet. This ticket pays every race that finishes, which for a one-day
  calendar means every race; #9 will need to decide whether a stage pays,
  the overall pays, or both — this ticket does not pre-decide that either.
- **Payout varying by race prestige.** Every race pays the same table.
  `competitions/README.md` already defers race tiers as a separate concern
  ("every race currently awards from the same table"); this ticket does not
  quietly invent one.
- **A start or finishing fee for merely entering a race.** Only the top 10
  are paid. A team that races and finishes 40th earns nothing from the race
  itself — that gap is intentionally left for fanbase (#21) and sponsorship
  (#22/#23) to fill, not patched over here.
- **A season-to-date prize money total anywhere in the UI.** The standings
  table already tells the season story in points; this ticket doesn't add a
  parallel one in money.
- **Any player choice about prize money** — nothing to configure, opt into,
  or spend differently. It is paid automatically, like wages are charged
  automatically.

## Rules and edge cases

- **Same table, every race.** No notion of a bigger or smaller race exists
  yet for prize purposes, the same as it doesn't for points.
- **Position-based, not best-finisher-based.** Where points score a team
  once per race (its best-placed rider only), prize money scores every
  placed rider independently. A squad with two riders in the top 10 is paid
  twice; a squad with none is paid nothing, no matter how many riders it
  started.
- **Non-finishers never count**, even though a non-finisher still holds a
  numbered position in the result. This mirrors the existing points rule
  exactly, and for the same reason: a team should never be rewarded for a
  rider who abandoned.
- **Frozen at the moment a race is scored.** If the payout table is retuned
  later, races already paid keep what they were worth at the time — the
  same rule points already follow, and the only rule a permanent financial
  history could follow.
- **Exactly once per race**, even if the system revisits an already-scored
  race — the same guarantee scoring itself already makes.
- **Unmanaged teams are paid in full.** Wages already charge every team
  regardless of who manages it; prize money follows the same shape so a
  team's ledger never silently diverges from what actually happened to it
  on the road.
- **A claim wipes it.** Claiming a team already resets its balance to a
  fresh starting figure; prize money earned before the claim disappears
  into that reset exactly the way starting balance, wages, and (once
  shipped) fanbase already do. Nothing new to build here — this is a
  statement that prize money doesn't need an exception.

## Decisions taken

- Prize money pays every placed rider independently, not just a team's
  best finisher — the opposite of how points work, so money rewards squad
  depth in a way points structurally cannot.
- The payout table mirrors the points table exactly: 10 paying positions,
  nothing below.
- All races pay the same table — no prestige scaling, no per-race payout.
- Payout is "meaningful, not sufficient": a strong week should visibly help
  a team's balance without covering its wage bill outright, so fanbase and
  sponsorship stay necessary rather than decorative once they exist. Exact
  figures are a tech-plan concern, not a product one — this spec deliberately
  gives no numbers.
- Classification payouts and stage-race per-stage/overall payouts are both
  cut: neither classifications (#18) nor stage races (#9) exist yet, and
  designing their payout shape before the features themselves exist would
  be guessing.
- A start/finishing fee for entering a race (not placing) is cut — it
  dilutes the "top 10 or nothing" position taken above, and a income floor
  for non-scoring teams is fanbase's (#21) job, not this ticket's.
- Prize money must be visible in two places: the payout table on a race
  (before and after it runs, in the same spot both times) and as dated
  lines in the team's financial history. A season-to-date total is cut.

## Open questions

- **Where the wiring lives.** `racing/` must never import `competitions/`,
  and `economy/` may not import `racing/` or `competitions/` at module
  scope. Scoring already crosses this boundary by having `world/` (which is
  allowed to know about everything) call `score_race` right after
  `simulate_race`. Whether prize money is paid by `world/` the same way, or
  some other shape, is `/tech-plan`'s call — this spec only requires that
  a race being scored and a race being paid out are the same event and
  cannot come apart.
- **Exact payout amounts per position.** Left to the tech plan, bounded by
  the "meaningful, not sufficient" decision above and the existing figures
  in `economy/README.md` (`STARTING_BALANCE = 500_000`,
  `WEEKLY_WAGE_PER_RIDER = 1_200`).

## Deferred

- Classification payouts — waiting on #18.
- Stage-race per-stage vs. overall payouts — waiting on #9.
- Prize money scaling with race prestige — waiting on a race-tier design
  that doesn't exist yet, and would also affect points.
- A season-to-date prize money figure in the UI — not until there's reason
  to think the ledger history and standings table aren't enough.
