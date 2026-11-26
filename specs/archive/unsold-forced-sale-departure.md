# An unsold forced sale is a departure

**Status:** implemented
**Domain(s):** transfers, riders, api, frontend
**One-liner:** When a rider put up for a forced sale finds no buyer, the seller's departures feed says so, the same way it reports a sale.

Issue: #170 (a follow-up from the review of #169, which built #158 and #162).

## Why this exists

During insolvency (#27) a manager can force a rider's sale. The rider leaves the roster at once, and if the auction ends with no buyer they become a free agent. #169's departures feed recorded the forced sale that *sold*, but not the one that did not, so the second outcome left no trace. The listing is a click the manager makes, but the auction ends days later, often while they are away, which is exactly what the feed exists to explain.

## Player experience

A manager under insolvency force-sells a rider and logs off. The auction ends with no bids. When they come back, the dashboard's **Riders who left** card reads: *Pablo Fernandez (ROU, 24) found no buyer at a forced sale and joined the free agents in Season 4, Week 3.* The roster screen's card shows the same line for the rest of the season, and the API returns it with the other departures.

## In scope

1. A forced sale that ends with no buyer, whether nobody bid or the winning bidder's roster was full, records a departure against the team that listed the rider.
2. It is dated to when the auction ended, not when the rider was listed.
3. It shows wherever the other departures show: the dashboard's last two weeks, the roster's season list, and the API's history.
4. It is its own kind, separate from a graduate's release, because it is a different event and the development squad screen lists graduate releases only.

## Out of scope

- **Recording the listing itself.** No: the manager clicked it, and the departures feed deliberately leaves out what the manager did themselves.
- **A voluntary auction ending unsold.** No: the rider never left the roster.
- **A forced-sale rider who retires before the auction ends** (the auction is cancelled). Later, if ever: it needs a season close to fall inside a two-day auction, and the rider's retirement already shows on their profile.

## Decisions taken without asking

The issue offered "a new kind or `released` with a note". A new kind, `unsold`, was chosen: `released` already means a graduate's release, and the squad screen filters on it, so reusing it would list a forced-sale rider as a squad release.
