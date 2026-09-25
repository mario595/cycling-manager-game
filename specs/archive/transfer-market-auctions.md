# Transfer market with rider auctions

**Status:** implemented
**Domain(s):** `transfers/`, `economy/`, `world/`
**One-liner:** A manager can list any rider from their own roster for auction; other managers bid over a few real days, and the highest bid at the deadline buys the rider — money and rider changing hands automatically.

## Why this exists

Free agents ([#29](https://github.com/mario595/cycling-manager/issues/29))
give a manager a way to pick up an unwanted rider cheaply and shed one they
don't want, but nothing lets two managers who both want the *same* rider
compete for them. Today a roster is either what a claimed team came with or
what the free agent pool happened to offer — never something actively
fought over. This is the feature that makes a roster something you build by
outbidding someone else for a rider you specifically want, not just
something you assemble from what's lying around.

It's also the second half of what `transfers/README.md` calls market value's
real purpose: [#31](https://github.com/mario595/cycling-manager/issues/31)
computes a number with nothing yet reading it back except free agent
pricing. An auction is where that number gets tested against what another
manager is actually willing to pay.

## Player experience

From their roster screen, a manager picks a rider and lists them for
auction. They see the reserve price the game has set — a fraction of the
rider's market value, the same value already shown on their roster — and
confirm the listing. The rider stays on their roster, still racing, still
training, still earning their wage, for as long as the auction runs.

The listing appears on a market screen alongside every other team's live
auctions: rider, reserve or current bid, and a live countdown to the
deadline (`dd hh mm ss`, ticking down in real time rather than a static
date). A manager browsing for a specific need — a second Climber, a young
rider to build around — scans the list the same way they'd scan the free
agent pool, but here every rider has a price that's moving. Every auction
the manager's own team is involved in — a rider they're selling, or one
they've bid on — also surfaces on the Dashboard, so neither is buried
inside the Transfers screen.

Placing a bid needs the team to have that much in the bank right now — no
future income counted, no fee added on top, just the number they bid. If
someone else bids higher, they see they've been outbid and by how much, and
can bid again. Each listing shows its full bid history — every bid placed,
and which team placed it — so a manager can see exactly who they're bidding
against and how the price got there.

A bid placed close to the deadline pushes the deadline back a little,
rather than ending the auction on the spot. This is invisible engineering
to the player — what they see is: bidding right at the wire keeps the
auction open a bit longer instead of slamming shut, so a genuine contest
plays out instead of being decided by who happened to be looking at their
screen in the final second.

When the deadline finally passes with no further bids, the auction
resolves the next time the game checks — usually within the hour. If
someone bid, the rider moves to the winning team's roster, the winning
bid leaves their balance, and it lands in the seller's. The seller sees
the sale in their finances the way any other income shows up. If nobody
bid at all, the rider simply stays where they were — no cost, no
consequence, as if the listing never happened.

## In scope

1. A manager can list any rider currently on their own roster for auction,
   from their roster screen.
2. The auction runs for a fixed real-time duration from listing.
3. The listing shows a reserve price — the auction's starting bid — derived
   from the rider's market value.
4. Any other manager can place a bid at or above the current price (the
   reserve, or the current high bid plus a minimum increment, whichever
   applies).
5. A bid is refused if the bidding team's current balance can't cover it.
6. A bid placed within a short window of the deadline extends the deadline
   by that same window, so a last-second bid never ends the auction
   unanswered.
7. The market screen shows every live auction: rider (with the same
   attributes shown elsewhere), current price, a live countdown to the
   deadline, and the full bid history — every bid and which team placed
   it.
8. A manager who has been outbid on an auction they bid on can see that
   they've been outbid and what the new price is. Auctions the manager's
   team is selling or has bid on also appear on the Dashboard.
9. The listed rider stays on the seller's roster — racing, training,
   earning their wage as normal — for the full duration of the auction.
10. At the deadline (subject to extensions), the auction resolves
    automatically: the highest bidder pays their bid, the rider transfers
    to their roster and begins earning their existing weekly salary there,
    and the seller receives the winning bid as income.
11. An auction that reaches its deadline with no bids resolves to nothing:
    the rider stays with the seller, no money moves, the listing is gone.
12. A rider can only be listed by the team that currently owns them, and
    only once at a time.

## Out of scope

- **AI teams bidding or listing.** [#30](https://github.com/mario595/cycling-manager/issues/30).
  Until it ships, most teams — the unmanaged majority — never appear in the
  market at all, as participants or as competition for a human bidder.
- **Rider consent or refusal.** The game has no contract or loyalty model to
  hang a refusal on. The highest bid always wins.
- **Held or escrowed funds.** A bid checks the bidder's balance at the
  moment it's placed, not continuously, and nothing is ring-fenced while a
  bid stands. A manager can be outbid, or can win an auction that leaves
  them short elsewhere if they spent the money in between — the same way
  nothing today stops a manager overspending generally. Belongs with
  [#27](https://github.com/mario595/cycling-manager/issues/27)'s insolvency
  ladder if it turns out to matter.
- **Any social layer beyond bid history.** No messaging, no following a
  manager's activity, no reputation. Bidder identity and full bid history
  are shown (see *Rules and edge cases*) — that is the extent of it.
- **Buy-it-now, or any way to end an auction early.** A listing always runs
  its full course (plus any extensions).
- **Selling to a specific team, or a private/invite-only auction.** Every
  listing is visible and biddable by every manager.
- **A cap on how many riders one team can list or bid on at once.** Not
  asked for, and nothing about the game today needs it. Revisit only if it
  turns out to be a problem in practice.
- **Relisting an unsold rider automatically, or at a discount.** An unsold
  auction just ends; listing again is a fresh decision the manager makes,
  same as the first time.

## Rules and edge cases

- **The listed rider is unavailable to a second listing, but otherwise
  unaffected.** They keep racing, training and earning their wage exactly
  as before. Nothing about being listed changes anything except that the
  same rider can't be listed again until this auction ends.
- **The seller can't bid on their own listing.** Obvious, but worth stating
  since nothing else in the game currently blocks a team from transacting
  with itself.
- **A rider who leaves the roster some other way while listed — released,
  or (later) sold in a forced sale — cancels the auction.** Whichever
  mechanism moves the rider first wins; the loser is a no-op, not an
  error. This should be rare in practice today since #29's release flow and
  this auction are both manager-initiated actions on the same roster.
- **Bidding shows full identity, not anonymous.** The market shows every
  bid and which team placed it, alongside the current price and a live
  countdown. The original scoping decision was to hide identity, reasoning
  that a thin, early market with few human players and no AI bidders yet
  ([#30](https://github.com/mario595/cycling-manager/issues/30)) would be
  easy to coordinate around if bidders could see each other. That was
  reversed during implementation review: the coordination risk was judged
  smaller than the value of a transparent market, and revisiting it once
  #30 ships (rather than before) is straightforward if it turns out to
  matter.
- **Deadline extension is bounded by nothing except itself.** Every
  qualifying late bid pushes the deadline again — an auction with genuine,
  sustained competition can run longer than its nominal duration. This is
  the expected, desired behaviour: the deadline exists to give a real
  contest room to finish, not to cut one off.
- **A won auction pays the seller as ordinary income**, and the buyer's
  payment as an ordinary cost — both visible in each team's finances the
  way any other ledger entry is, not as a special transaction type the
  player needs to understand separately.
- **A rider's wage is unaffected by the sale.** Their `weekly_salary` was
  set at generation and frozen for the season ([#25](https://github.com/mario595/cycling-manager/issues/25));
  moving teams doesn't change it, the same way #29's free agent signing
  doesn't.
- **The reserve price is a fixed fraction of market value, not the seller's
  choice.** Consistent with free agents' fee (also a fixed fraction of
  value, per #29) rather than inventing a second pricing mechanism the
  player has to reason about differently.
- **What counts as a valid next bid is the current price plus a minimum
  increment**, not simply "any higher number" — this stops a bidding war
  being decided by whoever is willing to type one more currency unit than
  the last bid, and keeps the price moving in visible steps.

## Decisions taken

- Auction runs a fixed real-time duration (not tied to the week boundary)
  — decouples the market from the race calendar and is fair to managers in
  different timezones. Decided in scoping.
- Late bids extend the deadline rather than ending the auction outright —
  the only anti-snipe approach that works given an hourly production tick;
  a hard deadline would let whoever happens to be online at the right
  moment win regardless of valuation. Decided in scoping.
- The rider has no say in the move — no contract or loyalty model exists to
  hang a refusal on, and the highest bid always wins. Decided in scoping.
- Reserve price is a fixed percentage of market value, not seller-chosen —
  one fewer decision for the manager, consistent with #29's fee shape, and
  the number is already computed by #31. Decided in scoping.
- An unsold auction returns the rider unchanged, at no cost — keeps this
  feature distinct from #27's forced sales, where listing is a deliberate
  one-way commitment. A voluntary market test must stay reversible or
  managers won't use it. Decided in scoping.
- Bidding and the market screen show full identity — every bid and which
  team placed it. Originally scoped anonymous (see *Rules and edge cases*
  for the reasoning); reversed during implementation review in favour of a
  transparent market. Revised post-implementation.
- A bid is checked against the bidder's balance at the moment it's placed,
  with no escrow or hold — simplest rule that's always legible; the
  overspend loophole is accepted for now and left to #27 if it becomes a
  real problem. Decided in scoping.
- This spec assumes [#29](https://github.com/mario595/cycling-manager/issues/29)
  (free agents) ships first, per the roadmap's forced order
  (`#31 → #29 → #28`). The auction reuses #29's reserve/fee shape (a fixed
  fraction of market value) rather than inventing a second pricing rule,
  and leans on #29 having already answered "what does a roster cap mean
  for acquiring a rider" so this spec doesn't have to re-decide it.
  Implementation of this ticket is blocked on #29's implementation, not
  just its spec. Decided in scoping.

## Open questions

- Exact auction duration, extension window, reserve percentage, and minimum
  bid increment — all tuning numbers for the plan to calibrate, the same
  way #29's fee percentages and #31's calibration constants were.
- Whether the roster cap from #29 also applies to *winning* an auction (a
  team at the cap presumably can't win one either) — should fall out
  naturally from #29's cap existing, but the plan should confirm it applies
  uniformly to every way a roster grows.

## Deferred

- **AI teams bidding and listing.** Needed before the market has any real
  activity from the unmanaged majority of teams. [#30](https://github.com/mario595/cycling-manager/issues/30).
- **Escrowed or held funds while a bid stands.** Would close the overspend
  loophole properly, but is real ledger machinery an MVP doesn't need yet.
  Revisit with [#27](https://github.com/mario595/cycling-manager/issues/27).
- **A cap on concurrent listings or bids per team.** Not needed until the
  game has evidence it's a problem.
