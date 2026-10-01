# Cancel listings on claim

**Status:** approved
**Domain(s):** transfers, teams, api
**One-liner:** When a player claims a team, every rider that team had up for auction is taken off the market, so the new manager never inherits a sale they did not start.

Issue: #114.

## Why this exists

Claiming a team resets its present: the old roster is released to the free-agent pool and a fresh one is generated. Bids the team had placed are already withdrawn (#30), so a new manager never inherits an in-progress purchase. Listings are the other half of that sentence, and they are not handled. An auction the team was running for a rider who has now left stays open, still shown as the new manager's own listing for a rider who is not on their roster.

The visible damage is confusion and tied-up AI money. The new manager sees a listing they never made, and an AI team may bid on it, locking its budget for up to three days. No money moves wrongly, because the auction is cancelled at its deadline. About one claim in ten hits this.

## Player experience

A player claims an unmanaged team. Some of that team's riders were up for auction. The moment the claim completes, those auctions are gone. The new manager opens the Transfers screen and sees no listing of their own. The riders the old roster had listed are ordinary free agents like the rest of the released roster, and can be signed at the usual fee. Other teams that had bid on those auctions find the listing has disappeared from the market and from their list of auctions they are bidding on. Nobody is charged or paid anything.

The new manager's first screen is clean: a fresh roster, no listings, no bids.

## In scope

1. Claiming a team ends every open listing that team was selling, as part of the same step as the claim. There is no moment where the claim has happened and the listing is still open.
2. An ended listing leaves the market screen and every bidder's list of auctions they are bidding on.
3. No money moves: no bidder is charged and the team is not paid.
4. The listed rider stays a free agent, as the claim already makes them. They are not returned to the team.
5. The rule covers every open listing the team was selling, whether an AI team or a human created it.
6. An AI team whose reserve bid was sitting on such a listing has that budget available again immediately.
7. If the claim cannot complete, the listings are not cancelled either. The claim is all or nothing.

## Out of scope

- **Returning the listed rider to the team.** Cut: it undoes the claim's reset.
- **Telling bidders their auction was cancelled.** Later: needs a general notification feature the game does not have.
- **A distinct "cancelled by claim" status.** Cut: not visible to the player. Existing cancelled covers it.
- **Cancelling listings when a team is released** (inactivity or admin). No: release touches nothing but the manager link by design. A listing still open on a released team keeps running, and the next claim cleans up.
- **A general rule that a listed rider can never be a free agent.** No: this claim path is the only known way to produce that state.

## Rules and edge cases

- A team with no open listings is unaffected.
- Closed auctions (sold, unsold, cancelled earlier) are left as they are.
- Withdrawn bids stay as history, as today. Cancelling does not change them.
- Listings may be on riders already released by the claim in the same step. Order of operations is not visible to the player.
- Developer seeding that claims a team directly (not through the API) is not covered. It only runs on freshly seeded teams, which have no listings.
- Claiming twice cannot cancel anything the second time: the first claim already emptied the team's listings.

## Decisions taken

- Rider fate: the claim's release stands; the rider is a free agent and the auction is cancelled.
- Bidders: the listing disappears quietly, no notice.
- Release (inactivity/admin) does not cancel listings; claim only.
- No general "listed riders are never signable" guard in this ticket.

## Open questions

None.

## Deferred

- Bidder notification that an auction was cancelled: waits for a general notification feature.
