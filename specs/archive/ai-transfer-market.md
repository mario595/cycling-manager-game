# AI teams participating in the transfer market

**Status:** implemented
**Domain(s):** `transfers/`, `world/`
**One-liner:** Unmanaged teams bid on human listings they need and can afford, and occasionally list their own surplus riders, so the auction market has real activity even though most teams have no human manager.

## Why this exists

Auctions ([#28](https://github.com/mario595/cycling-manager/issues/28)) let
one manager buy from another, but most teams in a world have no manager —
`Team.manager` is nullable by design, and a fresh world is mostly unmanaged.
Today that means most listings face no competition at all: a human lists a
rider and either another human happens to want the same rider, or nobody
bids and the auction goes unsold. With the current seed of 16 teams and one
claimed for a demo account, that's 15 teams that can never appear in the
market as a bidder or a seller. The market is only as alive as the human
population, which at launch is close to zero.

This gives every unmanaged team a simple, predictable buying and selling
presence, so a rider a human lists is likely to get looked at, and a human
shopping the market finds more than just what other humans happen to be
selling.

## Player experience

A manager lists a rider they no longer want. Within the next tick or so, if
the rider would improve some AI team's lineup and that team can afford it,
a bid appears in the auction's history under that team's name — one bid, at
the listing's starting price. If a human later outbids it, the AI does not
respond further; that auction is now a contest between humans, the same as
if the AI had never bid. If nobody outbids it, the AI wins at the deadline
like any other buyer, and the seller gets paid.

Browsing the market, a manager also sees listings from teams with no
manager alongside human ones — an AI team occasionally puts a rider up
because its roster has grown past what it fields, or because a rider is
getting old. These are ordinary listings: same reserve price, same
deadline, same rules, nothing marked as different.

If a manager claims a team that currently has the top bid in some auction,
that bid is withdrawn the moment they take over — they start managing a
team with money in the bank, not one mid-transaction for a rider they
never chose. The auction carries on for whoever is left.

Nothing else about the market changes. A human who never touches the
market still sees the price a rider could fetch move over a season, because
somebody is actually buying and selling.

## In scope

1. An unmanaged team can bid in an auction listed by anyone.
2. An unmanaged team bids at most once per auction, at that auction's
   current asking price at the time it decides to bid.
3. An unmanaged team only bids on a rider who would be among its stronger
   riders for their speciality, or on any usable rider if its roster is
   thin.
4. An unmanaged team never bids more than it can afford while keeping a
   safety cushion in its balance.
5. An unmanaged team occasionally lists one of its own surplus or ageing
   riders for auction.
6. An unmanaged team never lists a rider if doing so would leave it unable
   to field a full squad.
7. If a team stops being unmanaged (a human claims it) while it holds the
   current top bid in an open auction, that bid is withdrawn and the
   auction continues among the remaining bids.
8. AI listings and AI bids are visible on the market exactly like a human's
   — same screens, same information, nothing labelled specially.

## Out of scope

- **Unmanaged teams trading with each other.** No human ever sees it, and a
  claim resets the team's roster anyway (`teams/README.md`), so it would be
  activity with no payoff. Belongs to nothing — simply not built.
- **Unmanaged teams releasing riders for severance.** Costs the team money
  for no player-visible benefit. An unmanaged team's roster only shrinks
  through a sale.
- **Unmanaged teams signing free agents.** Without retirement
  ([#42](https://github.com/mario595/cycling-manager/issues/42)) an
  unmanaged roster never needs replacing, so buying free agents would only
  ever grow it. **Later**, alongside #42.
- **Different AI teams behaving differently from each other.** Every
  unmanaged team uses the same buying and selling rule. **Later.**
- **AI bids that rise, or that compete against each other.** One bid, once,
  at the asking price, is the entire strategy. **Later**, if a flat market
  presence turns out to feel too predictable.
- **Any indication in the UI that a bid or listing came from an AI team.**
  A market that's visibly half-fake defeats the point. If it ever becomes
  useful to know, that's a separate, later decision.
- **Unmanaged teams signing a sponsor.** Raised as a possible dependency
  below (see *Rules and edge cases*) — out of scope for this ticket unless
  that dependency turns out to be real.

## Rules and edge cases

- **An AI bid never chases a human.** It places one bid, at the price the
  auction is asking when it decides to bid, and never raises it again in
  that auction — even if outbid. This is deliberate, not a missing
  feature: a bid that only ever matches the reserve, never exceeds it,
  means a human can never profitably buy a rider from an AI team and sell
  them straight back to another AI team. Anything fancier here is Later
  work, not MVP.
- **"Would improve their lineup" is roster-relative, not value-relative.**
  An AI team looks at listed riders against its own current roster, for the
  listed rider's speciality — not against every roster in the world. Two
  AI teams can reasonably disagree about whether the same rider is worth
  bidding on.
- **A thin roster overrides pickiness.** A team well below a normal roster
  size bids on any listed rider it can afford, regardless of speciality
  fit — better a rider who's a slight mismatch than a roster too small to
  race.
- **The cushion is a fraction of balance, not a fixed number.** A poorer
  unmanaged team should still be able to occasionally buy a cheap rider; a
  fixed floor either blocks every purchase for a poor team or is meaningless
  for a rich one.
- **Selling is rare by design.** Most unmanaged teams, most of the time,
  list nothing. This is a trickle of supply into the market, not a
  second free-agent pool — a manager who wants a specific rider should
  still look to human sellers and free agents first.
- **What makes a rider "surplus."** Either the team's roster is larger than
  a normal one, or the rider is old enough that the team's better riders at
  that speciality are clearly elsewhere on the roster. A team at or below
  normal size with no clearly-ageing riders lists nothing.
- **A withdrawn bid on claim is a deletion of intent, not a sale event.**
  Nothing is charged, nothing is logged as a rejected offer — the standing
  AI bid simply stops existing, and the auction's current price and history
  reflect whatever the next-highest bid was, exactly as if the AI had never
  bid. If there is no other bid, the auction returns to having none.
- **A human claiming a team never inherits an in-progress purchase.** This
  is the reason for the rule above: a freshly claimed team's balance is
  reset to the starting amount (`teams/README.md`), and owing money for an
  auction the new manager never agreed to would be a confusing first
  moment with the team.
- **The reverse direction is unaffected.** When a human's team is released
  back to the unmanaged pool (inactivity, #63), any bids or listings it
  already placed as a human stand exactly as they were — this rule only
  fires the moment a team's manager changes from none to someone.

## Decisions taken

- AI bids are capped at the auction's asking price, never raised — not up
  to the free-agent signing fee (60% of value) as first proposed. A cap
  above the reserve (50% of value) opens a flip: buy from one AI team,
  sell to another, for a spread. A single flat bid closes it, since buying
  from an AI never nets a later sale to another AI for more. Decided in
  scoping, reversing the initial default.
- No guaranteed floor — an AI bids only when a rider fits a need it has and
  it can afford them. A listed rider is not guaranteed to sell; that stays
  a real test of the market, and keeps releasing (severance) a genuine
  alternative to listing. Decided in scoping.
- AI teams both buy and sell, in a trickle — buying alone leaves the only
  strong riders for sale coming from other humans, which is thin at
  launch. Decided in scoping.
- Spending is against the team's real ledger balance, with a cushion kept
  back — an AI's balance is meaningful money, the same as a human's, not
  an unlimited tap. Decided in scoping.
- AI-to-AI trades, AI releasing for severance, and AI signing free agents
  are all cut — none are visible to a human, and free agents in particular
  have no roster pressure forcing AI teams to buy them until retirement
  (#42) exists. Decided in scoping.
- A human claiming a team withdraws that team's standing AI bids rather
  than transferring them to the new manager — a newly claimed team starts
  with a reset balance and no manager-chosen purchases in flight. Decided
  in scoping.

## Open questions

- **Does an unmanaged team's balance hold up across a season without a
  sponsor?** Raised during scoping: unmanaged teams pay wages
  ([#25](https://github.com/mario595/cycling-manager/issues/25)) but never
  sign a sponsor ([#22](https://github.com/mario595/cycling-manager/issues/22)),
  so AI buying power could dry up well before a season ends. The plan
  should check this against the existing seed/tick tooling before
  calibrating cushion and need thresholds. If balances do bleed out, the
  fix is pulling forward part of #45 (AI signs a sponsor at season start)
  rather than loosening this ticket's budget rule — a decision for
  whoever picks that up, informed by what the check finds.
- **Exact numbers** — what counts as "surplus" roster size, how ageing is
  judged for listing, the cushion fraction, and how often an unmanaged
  team checks whether to list. Tuning detail for the plan, the same way
  #28 and #29 left their percentages to be calibrated there.

## Deferred

- **AI signing free agents.** Waits for rider retirement (#42) to give
  unmanaged rosters a reason to need replacements.
- **Per-team AI personalities** (cautious vs. aggressive buyers). The
  market needs a uniform baseline presence before it's worth varying.
- **AI bids that raise or contest each other.** Adds real strategy at the
  cost of reopening the flip risk the flat-bid rule closes. Revisit only
  if a single flat bid per auction proves to feel too inert.
- **AI signing a sponsor at season start**, pulled forward from #45 if the
  open question above finds unmanaged balances actually run dry mid-season.
- **Labelling AI activity in the UI.** Not wanted now — the market should
  read as one market — but nothing rules it out later if it turns out
  players want to tell the difference.
