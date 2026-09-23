# Free agents

**Status:** proposed
**Domain(s):** `transfers/` (new), `riders/`
**One-liner:** A manager can browse riders with no team and sign one onto their roster for an upfront fee plus the wage; they can also release a rider the other way, back into that same pool.

## Why this exists

Riders without a team already exist in the game — every time someone claims
a team, that team's previous roster (~12 riders) is released to sit with
`team = null`, invisible and inert. Today nothing can happen to them. A
manager has no way to add a rider to a thin roster except by claiming a
team, and no way to shed one except that roster resetting out from under
them.

This gives that standing pool of riders a purpose, and gives a manager two
levers they don't have today: bring in a specific rider they want, and drop
one they don't. It's the first piece of the transfer market
([#28](https://github.com/mario595/cycling-manager/issues/28)) to ship —
the simplest possible one, since a free agent has no other team competing
for them.

## Player experience

A manager opens a new screen — the free agent market — and sees a list of
riders with no team, each shown the way their own roster is shown: the five
attributes, speciality, age, freshness, weekly salary, and now also a market
value ([#31](https://github.com/mario595/cycling-manager/issues/31)). They
can sort or scan for someone who fills a gap in their squad — a second
Climber, a younger rider to build around.

Signing one costs an upfront fee, on top of the wage they'll now be paying
every week. The screen is honest about both before the manager commits: the
fee they'll pay today, and the weekly cost from tomorrow. If the team
can't afford the fee, or is already at the roster size limit, signing is
refused with a plain reason — not a confusing failed request.

The other direction: from their own roster, a manager can release a rider.
Their own roster screen already shows what releasing each rider would cost
— including "$0" for a rider they can still drop for free — so the choice
is never a guess. The rider leaves immediately — the wage stops that week —
and the manager pays whatever fee was shown, smaller than a signing fee
would be, except right after claiming a team: for one week after a claim,
releasing any rider inherited from that claim costs nothing. A team that
just took over a roster it didn't choose shouldn't be punished for tidying
it up.

Riders sit in the pool as long as someone might plausibly want them. A
rider who's been unattached a long time and is worth very little quietly
drops out of the pool — not sold, not visible anywhere, just gone. A
manager watching the market never sees this as a rug pull, because the
riders it happens to were never going to be a live prospect for anyone
in the first place: strong riders don't sit long enough for it to matter,
weak riders were clutter.

## In scope

1. A screen listing every rider with no team, showing the same visible
   attributes their own roster shows, plus market value.
2. A manager can sign any listed free agent onto their own roster, paying
   an upfront fee plus taking on the rider's existing weekly salary from
   that point on.
3. Signing is refused, with a clear reason, if the team can't afford the
   fee, or if signing would put the roster over its size limit.
4. The roster screen shows, for every rider, what releasing them would cost
   right now — including "$0" for a rider still inside its free claim
   cooldown.
5. A manager can release a rider from their own roster, sending them to the
   free agent pool. This costs whatever severance fee was shown, except for
   a rider inherited from a team claim, which is free to release within one
   week of that claim.
6. A released rider's wage stops immediately; they no longer count toward
   the releasing team's roster.
7. A free agent who has sat unattached a long time, and whose market value
   is low, eventually drops out of the pool on its own — not sold, just
   removed. Riders with real market value are not subject to this; nothing
   here is about players losing access to a rider they'd want.
8. The riders released by a team claim ([#46]) land in this same pool and
   are signable like any other free agent — no separate handling.

## Out of scope

- **Contested signings.** Whoever signs first gets the rider; there's no
  bidding, no reservation, no queueing. Two teams wanting the same free
  agent race for it exactly the way claiming a team already does. Real
  competition for a rider is the auction ([#28](https://github.com/mario595/cycling-manager/issues/28)).
- **AI teams signing or releasing.** Until
  [#30](https://github.com/mario595/cycling-manager/issues/30), human
  managers are the only participants; most teams are unmanaged and will
  neither sign nor release. The pool can only grow (via claims and
  releases) and shrink (via signings and expiry) through human action plus
  expiry.
- **Any scouting or hidden information about a free agent.** They're shown
  exactly what your own roster shows — nothing more, nothing less. Limited
  visibility is the scout's job ([#40](https://github.com/mario595/cycling-manager/issues/40)),
  not this ticket's.
- **A signing window or schedule.** The market is open every week of the
  season.
- **Selling a free agent, or any money changing hands between teams.**
  A free agent has no owning team to pay — the fee is paid to acquire
  them, not to another manager. Team-to-team transactions are the auction's
  territory.
- **Retirement.** Age-driven decline of a rider still on a roster is
  [#42](https://github.com/mario595/cycling-manager/issues/42)'s. What
  this ticket calls "dropping out of the pool" only ever applies to
  unattached riders and is a different mechanism with a different name,
  on purpose — see *Rules and edge cases*.
- **Rider market value itself.** Provided by
  [#31](https://github.com/mario595/cycling-manager/issues/31), which
  today shows it only on a manager's own roster. This ticket extends that
  visibility to free agents (see *Decisions taken*) but does not change
  how value is computed.

## Rules and edge cases

- **The signing fee is a percentage of the rider's market value**, in a
  fixed range (roughly 60–70%, to be calibrated in the plan against real
  generated values) — not the full value, and not a flat amount. A prized
  young rider costs real money to bring in; a mediocre one is cheap. The
  exact percentage is a tuning number, not a product commitment.
- **The severance fee is smaller than the signing fee**, as a percentage of
  the same market value. Releasing is a real cost, not a free lever for
  shedding wages — but it costs less than acquiring, since the team is
  giving up an asset rather than buying one.
- **What releasing would cost is always visible, even at $0.** The roster
  screen shows each rider's severance figure plainly rather than a manager
  discovering the number only after clicking release — the same standard
  the signing fee is held to on the free agent screen.
- **The claim cooldown is free, not discounted.** Any rider still on the
  roster a manager inherited from claiming their team can be released at
  zero severance for one in-game week after that claim. After that week,
  or for any rider the manager signed or generated themselves, full
  severance applies.
- **A roster size limit applies to signing, not to a team's existing
  roster.** A team already at or above the cap (however it got there) can
  still race, train and release riders — the cap only blocks bringing in
  more. The exact number is a tuning detail for the plan, sized comfortably
  above a starting twelve-rider squad.
- **Affordability is checked against the fee alone**, not the future wage
  bill — the same way the game doesn't stop a manager overspending on
  anything else. A team that signs its way into a wage bill it can't sustain
  finds out at the next wage run, same as today.
- **A released rider keeps their existing weekly salary and market value
  unchanged.** Nothing about leaving a team recalculates either number —
  salary is already frozen for the season regardless, and value is a live
  read of attributes and age, neither of which a release touches.
- **Pool expiry is gated on both time and value.** A free agent must be
  unattached for a while (roughly 8 weeks, tuning detail) *and* sit in the
  low end of the pool's value range before they're removed. A rider whose
  value is genuinely low clears out on schedule regardless of why nobody's
  signed them yet; a rider with real value never auto-expires just because
  the market happens to be thin — with no AI bidders yet
  ([#30](https://github.com/mario595/cycling-manager/issues/30)), an
  unsigned strong rider says more about how few people are playing than
  about the rider.
- **Expiry is silent.** No countdown, no warning shown anywhere. The riders
  it removes were never a live prospect for a manager who was actually
  looking — the point is pool hygiene, not a ticking clock a player needs
  to react to.
- **A team cannot be left without any riders.** Releasing already reduces a
  roster one at a time with nothing stopping it at zero — this ticket
  doesn't add a floor, since none exists today for any other reason a
  roster might shrink. If that turns out to matter, it's a squad-selection
  concern, not a free-agent one.

## Decisions taken

- Fee is a percentage of market value (not flat, not full value) — cost
  scales with quality without needing a separate pricing formula. Decided
  in scoping.
- Free agents are shown market value, extending
  [#31](https://github.com/mario595/cycling-manager/issues/31)'s
  own-roster-only scope — a fee derived from a number the player can't see
  isn't a real decision. Decided in scoping.
- Releasing costs severance, not free — preserves the pressure
  [#27](https://github.com/mario595/cycling-manager/issues/27) is designed
  around (listing/shedding a rider is a real cost, not a free reset).
  Decided in scoping.
- Claimed riders are exempt from severance for one week after the claim —
  a manager shouldn't pay to clean up a roster they didn't choose. Decided
  after review.
- Severance is always shown, including $0 during the cooldown — a manager
  should never have to click release to find out what it costs. Decided
  after review.
- Signing is limited by a roster cap plus affordability, not either alone —
  legible before the manager commits, and doesn't rely on a system
  (insolvency, [#27](https://github.com/mario595/cycling-manager/issues/27))
  that doesn't exist yet to catch an unbounded roster. Decided in scoping.
- Signings are first-come-first-served, no contention — real competition
  for a rider is the auction's job
  ([#28](https://github.com/mario595/cycling-manager/issues/28)), and
  building a mini-version of it here duplicates that ticket. Decided in
  scoping.
- Pool expiry is named and scoped separately from rider retirement
  ([#42](https://github.com/mario595/cycling-manager/issues/42)) — same
  underlying idea (stop accumulating riders nobody will ever use) but a
  different mechanism for a different situation: this one only ever
  touches unattached riders. Decided after review.
- Expiry requires both time unattached *and* low value, not time alone —
  with no AI demand yet, "nobody signed them" isn't evidence a rider is
  unwanted if their value says otherwise. Decided after review.
- No visible countdown on expiry — it's pool hygiene for riders nobody
  was seriously considering, not a deadline a manager needs to plan
  around. Decided after review.

## Open questions

- Exact signing-fee percentage, severance percentage, roster cap, and the
  time/value thresholds for expiry — all tuning numbers for the plan to
  calibrate against real generated rosters and starting balance, the same
  way salary's constants were calibrated.

## Deferred

- **AI teams signing and releasing free agents.** Needed before the pool
  sees any real churn from the unmanaged majority of teams.
  [#30](https://github.com/mario595/cycling-manager/issues/30).
- **Contested signings / bidding.** The auction itself.
  [#28](https://github.com/mario595/cycling-manager/issues/28).
- **Scouted or limited visibility into a free agent's attributes.**
  [#40](https://github.com/mario595/cycling-manager/issues/40).
- **A minimum roster size.** Not addressed here; revisit only if releasing
  a team down to zero riders turns out to be a real problem.
