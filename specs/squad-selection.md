# Squad selection for a race

**Status:** proposed
**Domain(s):** `racing/`, `teams/`, with a widget on the race screen (`frontend/`)
**One-liner:** Before each race, a manager picks which four of their riders start and which one of them the team rides for.

## Why this exists

Everything built so far happens *to* the player. The clock advances, the season
turns over, the calendar fires a race, and the result arrives — and at no point
did the manager do anything that changed it. Today the simulation races every
rider in the game, so a team's result is a property of its roster, not of its
management.

This is the first decision in the game that a player can get right or wrong. Four
riders start out of a roster that holds more; one of them is the rider the team
works for. A manager who looks at the course before choosing beats one who does
not, and two teams with identical rosters can now finish in a different order.

## Player experience

It is Tuesday. The calendar says Saturday's race is a hilly one-day classic, and
the manager opens it. The race screen shows the course and, alongside it, their
squad for Saturday: four riders, already filled in with whoever rode last week,
with one of them marked as the rider the team is riding for.

The manager looks at the profile — this one climbs — and reconsiders. The sprinter
who led last week is a passenger here. They drop him, bring in the second climber,
and move the leader's mark onto the rider who can actually win on this finish. The
other three are there to work for him. The screen makes it plain that exactly four
ride and exactly one leads: it will not let them leave with five names or with
nobody nominated.

They change their mind again on Thursday, and again on Saturday morning, and each
time it just saves. When the clock reaches the race, whatever was showing is what
starts. The riders left out simply do not appear in the race; the manager watches
four riders in team colours, not their whole roster.

A manager who never opens the screen at all still has a team at the start line —
four riders, picked by the game with no thought behind it. They finish, and they
finish worse than they would have. Nothing is forfeited, but nothing is earned
either, and the result makes the difference visible.

## In scope

1. For any race that has not yet started, a manager can see their team's squad
   for that race and change it.
2. A squad is exactly four riders, drawn from that team's own roster.
3. Exactly one rider in the squad is nominated as the leader; the other three
   ride in support.
4. A squad that is not exactly four riders with exactly one leader cannot be
   saved.
5. A squad can be changed as many times as the manager likes, at any point up
   until the race starts. There is no separate deadline.
6. When a manager opens a race they have not yet picked for, the squad is
   pre-filled with the one they used for their previous race, so a manager who
   is happy with it changes nothing.
7. Only the four selected riders from each team take part in the race. A rider
   left out does not appear in the race, in its replay, or in its results.
8. A team whose manager never made a selection still starts the race, with a
   squad the game picks for them.
9. A game-picked squad is chosen without regard to the course, and a manager who
   chooses deliberately can expect to do better than one who does not.
10. Once a race has started, its squads are fixed and shown as a record of who
    rode, not as something still editable.

## Out of scope

- **The stage-race squad lock.** The original ticket's second bullet — a squad
  locked after stage 1, with injured riders unreplaceable. There are no stage
  races (#9) and the calendar places one-day races only (#7). **Deferred to #9**,
  which inherits both this and the related rule below.
- **A rider entered in a stage race being unavailable for other races until it
  finishes.** Raised while scoping this, and correctly identified as a stage-race
  rule rather than a squad-selection one. **Deferred to #9.**
- **Any tactic beyond naming a leader.** Aggression, when to attack, whether to
  chase, sprint commitment. **Belongs to #38**, which needs its own spec.
- **A smarter fallback squad.** The game-picked squad here is deliberately naive.
  Choosing well on a team's behalf — course-aware, form-aware — **belongs to #45.**
- **Sharing one fallback mechanism between an absent manager and an unmanaged
  team.** This spec establishes the rule that every team fields a squad; building
  that once, properly, across both cases **belongs to #39 and #44.**
- **Reserves, substitutes, or late replacements.** No rider is held back as a
  stand-in. There is nothing to replace them for until injuries exist (#41).
- **A per-race squad size.** One size for every race. **No** — a variable size is
  authoring surface with no gameplay behind it yet.
- **Not starting a race as a punishment for inattention.** Considered and
  rejected: with weekly races in real time, managers will miss races, and a league
  where most teams did not start is not a league.
- **The layout of the race screen itself.** This feature is a widget on a screen
  that **belongs to #47**. What the widget does is defined here; how the screen
  around it looks is designed there, before this is implemented.

## Rules and edge cases

**Four riders, one leader — both exact.** Not a minimum or a maximum. This is the
field shape the simulation's realism was verified against: one leader and three
riders working for them. The simulation refuses a team entered any other way, so
an invalid squad must never survive to race day — which is why it cannot be saved
in the first place rather than being corrected later.

**A roster has no fixed size, and that is what gives this feature room.** A team
carries as many riders as its manager is willing to pay wages for. So the squad is
four out of *however many* — and how many is itself a management decision made
elsewhere. A manager running a lean roster of five has almost no choice to make
here; one carrying ten has a real one every week, and has paid for the privilege.
There is one floor, and it is not negotiable: **no team may hold fewer than four
riders.** A roster of three cannot field a legal squad at all, which is a broken
game state rather than an interesting predicament. Preventing it belongs wherever
riders leave a roster — selling, releasing, expiring contracts — and that is an
obligation this feature places on those tickets rather than a case it handles
itself. A team sitting exactly on the floor has no choice left but which of its
four leads; that is a consequence of how its manager spent their money, and it is
a legal position to be in.

**Every team is in every race.** Inherited from the calendar (#7) — there is no
entering or declining a race, so the only question a manager answers is *who*,
never *whether*.

**No selection is not a refusal.** A manager who never opens the screen gets a
squad, not a forfeit. The cost of ignoring the game is a worse result, and it is
paid in the standings rather than in an empty start line.

**The pre-filled squad is a suggestion, not a commitment.** A manager who opens a
race and changes nothing has, in effect, chosen last week's squad — which is a
reasonable thing to choose. It is filled in to save typing, not to make a decision
on their behalf.

**A rider unavailable for reasons that do not exist yet.** Injury, suspension and
fatigue are not modelled (#41). Every rider on a roster is selectable, always. When
availability becomes a real concept, this is where it lands.

**After the race, the squad is history.** A finished race shows who rode, forever.
It is a record alongside the result, not a setting that happens to be locked.

## Decisions taken

- **Scope: one-day races only.** The stage-race lock waits for #9 to exist.
- **Squad size: four.** Matches the field shape the simulation's realism was
  verified against; five was considered and dropped rather than re-open that
  verification.
- **The manager nominates a leader**, not just a set of riders. The simulation
  already reads a leader per team, and choosing who the team works for is the part
  of the decision that has any depth to it.
- **No selection means an auto-picked squad**, not a non-start.
- **Editable until the race starts.** No deadline ahead of the race — one fewer
  time concept for a player to learn.
- **Per race, pre-filled from the team's last used squad.** Not a single standing
  squad for the season, which would remove the per-race decision entirely.
- **Home is the race screen**, reached from the calendar. That screen is #47's to
  design, and will be designed before this is implemented.
- **Roster size has no upper bound**, limited only by what a manager can pay in
  wages. How much choice a manager has at squad selection is a downstream
  consequence of how big a roster they chose to carry.
- **Roster size has a lower bound of four.** A team that cannot field a squad is a
  broken state, not a playable one. Enforcing the floor belongs to whichever
  feature lets riders leave a roster; this spec records the requirement and assumes
  it holds.
- **Engine realism was verified at four riders per team**, and choosing four keeps
  that verification intact. A real season's field size (many more teams than the
  four the verification used) puts pressure on it regardless — that is a known
  issue with the verification, not something this feature introduces.

## Open questions

None.

## Deferred

- **Stage-race squad lock** — waits for stage races to exist at all (#9).
- **Rider exclusivity during a stage race** — same reason; belongs with the lock (#9).
- **Course-aware auto-pick** — the naive fallback is deliberate for now, so that
  managing visibly beats not managing (#45).
- **One shared fallback for absent managers and unmanaged teams** — the rule is set
  here, the single implementation is #39/#44.
- **Per-race tactics** — needs its own spec and carries an engine-rebalancing cost (#38).
