# Rider retirement and roster churn

**Status:** implemented
**Domain(s):** `riders/`, `world/`
**One-liner:** Every rider retires from the game at a hidden age within a fixed window, with a full season's warning before it happens.

## Why this exists

A rider can decline indefinitely and just sit on a roster, unusable, forever
— nothing ever forces a manager to move on. #58 (growth and decline) built
the falling half of a rider's career; this feature builds the exit at the
end of it. Without it, a roster a manager assembled in week one never has to
change, which is also why the development squad (#32) and the transfer
market have nothing to prove themselves against — nobody *needs* a
replacement.

The retirement mechanism itself already exists in the game (built for #104,
which permanently retires a raced rider who expires unsigned from the
free-agent pool, keeping their profile and results but taking them out of
circulation for good). This feature is the second way a rider reaches that
same state — driven by age, not by neglect — and it is the one that reaches
every rider, not only unsigned free agents.

## Player experience

A manager opens the roster at the start of a new season and one of their
riders — a 34-year-old domestique who's been fading for a year — now carries
a small "Last season" marker next to their name. Nothing else about the
rider has changed: they still train, still race, still draw a wage, still
have a market value if the manager wants to sell rather than watch them go
for nothing. The marker is just a fact, sitting wherever the manager already
looks — the roster, the rider's own page, and, if the manager releases the
rider instead, the free-agent listing.

The manager plans around it. Maybe they push the rider hard down the
stretch, since the wage bill ends anyway. Maybe they go shopping on the
free-agent market for a replacement domestique, or make room in the budget.
Maybe they release the rider mid-season for a fresh face — the marker
follows them into the pool, so anyone browsing free agents sees the rider
is on borrowed time before signing them.

At the season's close, the rider is gone — not deleted, not returned to
some "past players" list to browse, just gone from anywhere a manager
manages a roster. Their page still opens if a manager follows an old link
from a race result: "Retired," same as any rider retired the #104 way,
with their full history intact. Nobody is notified. Nobody has to click
anything to make it happen. The manager who was paying attention already
knew it was coming; the manager who wasn't finds a smaller roster and works
out why from what they can now see on the rider's page.

A young rider is never at risk of this. Retirement only ever touches riders
already well into their thirties — it is not a random cull, and a manager
who signs a promising 24-year-old free agent never has to wonder if this
season is secretly their last.

## In scope

1. Every active rider — rostered or a free agent, managed team or
   unmanaged — can retire. No rider is exempt.
2. Retirement never happens without warning: a rider due to retire is
   marked from the moment the season they'll retire in opens, and actually
   leaves the game only when that season closes.
3. The warning is visible on the roster screen, the rider's own profile
   page, and the free-agent listing, for as long as it applies.
4. A rider carrying the warning behaves exactly like any other active
   rider until they retire: they can be selected to race, trained, signed,
   released, or sold, and their salary and market value are computed the
   normal way.
5. Once retired, a rider leaves their team's roster (if they had one) and
   the free-agent pool, permanently, the same way a rider retired by #104
   does. Their profile page and past results remain reachable and correctly
   show them as retired.
6. Retirement age is not a fixed number the same for every rider — some
   riders retire earlier in the window than others.
7. No two riders' retirement is visibly identical for the same reason —
   the player is never shown *why* one 33-year-old retires and another
   plays on. Only *that* it is about to happen.

## Out of scope

- **Persuading a rider to delay retirement** — a bigger contract, a
  personal appeal, anything that changes the outcome once the season's
  marker appears. The decision is final the moment it's shown. **No** —
  this is a second feature (something closer to contract negotiation) and
  the honest version of it needs a contracts system this game doesn't have.
- **A career summary, farewell, or retirement announcement beyond the
  marker.** No "thanks for the memories" screen, no news feed, no digest.
  **Later** — belongs to #43 (season-end awards and world history), which
  is where the game starts keeping a sense of the past on purpose.
- **Any notification, alert, or inbox message.** The game has no messaging
  system. **No** for this feature — if one gets built later for other
  reasons, retirement can hang a message on it then.
- **Retirement affecting market value or auction pricing.** #28 doesn't
  exist as a live market feature to a manager yet in a form retirement needs
  to account for. **Later** — #28's own spec should decide whether a
  retiring rider's final season discounts their price.
- **Replacing a retired rider with a new one.** Nothing generates a
  replacement rider today, for anyone. **Later** — belongs to the
  development squad and youth intake (#32, #33), already next in the
  roadmap after this ticket.
- **A rider un-retiring, or a "past players" archive to browse.** Retired
  is permanent and reachable only by following a link to that specific
  rider, exactly like #104's shipped behaviour. **No** — changing that is
  a decision about #104's design, not this ticket's.

## Rules and edge cases

- **The window is a fixed band of years, not tied to any other visible
  number.** No rider retires young, and every rider still on the roster
  eventually does — but exactly where in that band varies rider to rider,
  in a way the player can watch play out over multiple seasons but never
  predict for a specific rider ahead of time.
- **The warning covers exactly one season.** It appears the instant the
  season a rider will retire in opens, and the rider is gone the instant
  that season closes. A manager never gets less than a full season's
  notice, and never more.
- **A free agent is not exempt, and being unattached changes nothing.**
  Age and the retirement window apply to every rider in the game
  identically, whether they're on a roster or sitting in the pool.
- **A rider signed, released, or sold during their marked final season
  still retires on schedule.** The marker travels with the rider; changing
  teams does not reset or cancel it.
- **The final season plays out normally in every other respect.** A marked
  rider trains, races, earns a salary, and can be bought or sold like any
  other rider. Nothing about them is frozen or discounted until the moment
  they actually retire.
- **Retirement carries no severance and no notice pay.** The rider simply
  leaves; there is no payment associated with it in either direction, the
  same as any other retirement in the game today.
- **A brand-new roster — a freshly generated team, or one just claimed from
  the pool — can include riders already carrying the marker**, if their
  age already puts them in the window when they're generated. This is
  accepted as realistic: a real squad has veterans in their final season
  too, and hiding it would mean lying to a new manager about a roster they
  just inherited.
- **This ticket does not solve the roster running low.** A world with no
  replacement source (#32/#33 not yet built) will see unmanaged teams'
  rosters shrink season over season as retirements land and nothing
  replaces them, and the free-agent pool only ever shrinks too. This is a
  known, accepted consequence of building retirement ahead of supply — see
  `specs/roadmap.md`, which already sequences the development squad and
  youth intake immediately after this ticket for exactly this reason.

## Decisions taken

- **Trigger:** age-driven, within a fixed per-rider window — not a fixed
  age for everyone, not driven by attribute decline, and not a wholly new
  hidden trait layered on top of existing ones.
- **Warning:** a full season's notice, shown from the season's opening
  until it closes, visible on the roster, the rider's page, and the
  free-agent listing.
- **Replacement supply:** deliberately not built here. Accepted that
  rosters shrink until #32/#33 land; the roadmap already sequences them
  right after this ticket.
- **Relationship to #104:** #104 shipped first and already built the
  permanent "retired" state (`riders/README.md`, *Retirement*) — a rider
  with no team, frozen attributes and salary, kept out of every roster and
  pool, profile and history intact. This feature is the second path into
  that same state, triggered by age at a season boundary instead of by
  free-agent expiry.
- **A retiring rider's final season is unrestricted** — full play, full
  price, full salary — right up to the moment they retire. Nothing about
  them is special except the marker.
- **No replacement mechanism, no contract negotiation, no farewell
  screen** — each cut for a specific reason recorded under *Out of scope*.

## Open questions

None. The one open question the original ticket posed (does the manager get
a warning) is settled above; the trigger mechanism is settled too.

## Deferred

- **Retirement affecting market value.** Waits on #28's own market
  actually being live for a manager to price against.
- **A career summary or farewell record.** Waits on #43, which is where
  the game starts keeping history on purpose.
- **Replacing retired riders.** Waits on #32 and #33.
