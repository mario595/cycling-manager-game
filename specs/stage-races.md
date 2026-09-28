# Stage races as an entity

**Status:** proposed
**Domain(s):** `schedule`, `racing`, `competitions`, `riders`
**One-liner:** A stage race is a run of consecutive-day races that shares one squad and adds up to a general classification, so a manager can win a multi-day battle even without winning a single stage.

## Why this exists

Every race today is a one-day event, scored and paid on its own. Real cycling's
biggest events — and its biggest storylines — are stage races: a rider losing a
sprint on day one but grinding out the overall lead by day five. Without that
shape, the calendar can only ever be a sequence of unrelated one-off results;
there's no race a manager plans a whole week around, and no way to reward a
team that's steady across several days rather than explosive in one.

This gives the calendar its first entries that are bigger than a single day,
and gives "squad selection" its first real stakes: pick wrong at the start of
a stage race and you're stuck with that choice for the whole thing.

## Player experience

A manager opens the calendar and sees, instead of a single Saturday race, a
banner spanning several days: **Alpine Tour, Stages 1–5, Week 6**. Underneath,
each stage is listed with its own day and a short course description — a flat
opener, a mountain stage mid-week, a rolling finale.

Before Stage 1 starts, the manager picks their four riders and names a leader,
exactly as for any race. That's the only squad decision for the whole race —
once Stage 1 begins, the same four riders and the same leader carry the team
through every remaining stage. A manager who wants a climber leading into the
mountains has to decide that up front, not day by day.

Each stage runs and finishes like a normal race day: a result, prize money,
and points. But there's a second scoreboard building alongside it — the
**general classification**, each rider's times added together across every
stage raced so far. After Stage 1 it's just that day's result reordered. By
Stage 3 it's telling a different story: a rider who was 8th on the road but
lost no time in the bunch might already lead the tour outright.

When the final stage finishes, the tour has two winners on record: whoever
won that last stage, and whoever leads the general classification — usually
different riders, sometimes the same one. The GC winner is the one the team
built the week around, and earns the bigger reward: more points and more
prize money than any single stage, on top of what each stage already paid.

If a rider can't finish a stage — cut by the time limit or abandoning — the
team rides on with three, or fewer, for the rest of the race. There's no
swapping in a replacement mid-tour; a manager whose leader goes down before
the mountains has to watch someone else finish the job, if anyone can.

A one-day race looks exactly as it does today — no banner, no GC, just a
result. Nothing about the existing calendar changes for it.

## In scope

1. A stage race is a named, ordered group of 2–7 races run on consecutive
   calendar days, entirely within one calendar week.
2. The calendar shows a stage race as a single entry spanning its days,
   listing each stage; those days carry no other race.
3. A team selects its squad — four riders and one leader — once, before the
   first stage, exactly as for a one-day race today. That squad and leader
   carry through every remaining stage; there is no reselecting between
   stages.
4. A rider entered in a stage race cannot also be entered in any other race
   until the stage race finishes.
5. Each stage produces its own result, exactly like a one-day race today —
   its own finishing order, its own points, its own prize money — at a
   reduced rate per stage.
6. Riders who finish a stage in the same group (i.e. cross the line with no
   meaningful gap) are given the same time for that stage, the same way a
   bunch sprint is read in real cycling. This applies to stage results and
   feeds the general classification; it does not change how a stage's
   finishing *order* (and therefore its points and prize money) is decided.
7. A general classification accumulates each rider's stage times as the
   race progresses, and is visible to players as the race goes — a manager
   can see who's leading the tour after each stage, not only at the end.
8. When the final stage finishes, the general classification is final. The
   leading rider's team earns a general-classification award — points and
   prize money on top of what its stages already paid, and larger than a
   single stage's award.
9. A rider who does not finish a stage (cut by the time limit or abandons)
   takes no further part in the stage race — no replacement is added, and
   the team continues with whoever remains.
10. Each stage costs a rider's race fatigue, same as today, but at a
    reduced rate per stage than a full one-day race — so a full stage race
    costs meaningfully more than one race, without wrecking a squad by the
    midpoint.
11. A stage race whose squad was never chosen by the manager still starts —
    the game picks one automatically, once, before Stage 1 — the same
    fallback that already exists for a one-day race.

## Out of scope

- **Sprinters'/climbers' classifications, jerseys.** Belongs to #18, which
  is a separate feature layered on top of markers (#70) that stage races
  don't need to wait for.
- **Time-trial stages.** Waits on #89/#90; a stage race can exist entirely
  out of ordinary road stages first.
- **Rest days.** Cut by keeping a stage race inside one calendar week — see
  *Rules and edge cases*.
- **Choosing or changing the leader stage by stage.** One decision, made
  once, before Stage 1. A manager who wants to protect a different rider on
  a different day has to wait for team tactics (#38).
- **Bonus seconds, time gaps as a tactical resource, GC-aware racing.** The
  simulation runs each stage as its own race; nobody "defends the jersey."
  That's #38's territory once tactics exist at all.
- **Reward scaled by how big a stage race is** — a 7-stage tour paying more
  than a 3-stage one. Every stage race pays and scores the same way
  regardless of length. Belongs with race tiers, already deferred in
  `competitions/README.md`.
- **A different squad size for stage races.** Four riders, same as every
  race today.
- **Injuries forcing a withdrawal beyond a normal DNF.** Waits on #41.
- **The general classification appearing in the race replay/visualizer.**
  The replay shows each stage as it does any race today; a running GC
  overlay is a `race_player/` feature for later (#94 territory).
- **Prize money or points for anything other than a stage result and the
  final GC** — no "most consistent," no combativity award, no other
  sub-competition. That's what the classifications in #18 are for.

## Rules and edge cases

- **Length:** 2 to 7 stages. A single "stage" would just be a one-day race,
  so 2 is the floor; 7 is a full calendar week, so a stage race can never
  need a rest day or spill into the next week's tick.
- **Placement:** entirely within one calendar week, on consecutive days.
  Whether it starts mid-week or fills the whole week is up to whoever
  builds the calendar — the same freedom a one-day race already has.
- **One thing happens on a stage race's days.** A day inside a stage race
  cannot also hold a separate one-day race or a stage of a different stage
  race — same rule as today's calendar, extended to cover every day the
  stage race occupies.
- **Squad lock:** once Stage 1 starts, the squad is fixed for every
  remaining stage. This holds even if the manager never touches the squad
  screen again — nothing about the lock is optional.
- **Rider exclusivity:** a rider committed to a stage race is unavailable
  for any other race — for their own team or anyone else's — until that
  stage race's last stage finishes. A rider cannot straddle two races at
  once.
- **A team can start a stage with fewer than four riders**, or none at all,
  if riders were cut or abandoned in earlier stages. A team with zero
  remaining riders simply scores nothing for that stage and the GC, the
  same way a whole squad not finishing scores nothing today.
- **The general classification is time-based**, not points-based: it's the
  sum of each rider's finishing time across every stage they completed.
  Their *best* remaining rider's cumulative time represents the team, the
  same way a single rider represents a team in today's one-stage points and
  prize logic — a tour is still won by a rider, not by summing a whole
  squad.
- **Same-time groups only affect the GC clock, never the finishing order.**
  A stage's points and prize money are still awarded by strict finishing
  order (today's rule, unchanged); only the *time* attributed to a rider
  for GC purposes is shared across their group.
- **GC ties:** if two riders somehow finish with the identical accumulated
  time (a stage race entirely of tied group finishes, for instance), the
  rider with the better individual stage placings wins the tie. This is a
  genuine edge case, not the common path.
- **Visibility mid-race:** the standing GC is computed and shown after each
  stage finishes, not just at the end — a manager watching a tour unfold
  can see who's leading before the final stage runs.
- **A stage race that never gets a manager's squad choice** still runs,
  using today's auto-pick fallback, applied once before Stage 1 rather than
  once per stage.
- **A one-day race is unaffected.** Nothing about its calendar entry,
  squad selection, scoring, payout, or fatigue cost changes. Whether
  one-day races are internally modeled as a stage race of length one is an
  implementation question, not a player-facing one — either way, a player
  never sees a "Stage 1 of 1" label or any other seam.

## Decisions taken

- **A stage race fits inside one calendar week, 2–7 stages.** Keeps every
  weekly system (wages, recovery, training, fanbase) landing between stage
  races rather than mid-tour, and removes rest days as a question entirely.
- **Stages score and pay at a reduced rate; the final GC scores and pays
  more than a one-day race.** A team that only ever finishes mid-pack still
  earns something every stage, and the GC award is worth building a squad
  around — without a 7-stage tour paying out seven times a classic.
- **Each stage costs reduced fatigue; the total for a full tour still
  exceeds a single race.** Fatigue visibly accumulates stage by stage
  without a squad being wrecked by the midpoint of a long tour.
- **Riders in the same finishing group get the same GC time.** Matches how
  real stage racing is read and avoids a GC decided by fractions of a
  second in a bunch sprint. Stage finishing order (points, prize money)
  stays strictly ordered regardless.
- **Squad and leader are chosen once, before Stage 1, and locked for the
  whole race.** Gives squad selection real weight for the first time and
  matches the brain-dump's original H1 intent; per-stage changes wait for
  team tactics (#38).
- **A rider is exclusive to one stage race while it's running.** Prevents
  a rider racing two events on the same calendar day by construction, and
  was already flagged during squad-selection's own scoping as belonging
  here.
- **Reward does not scale with how many stages a race has.** Length-scaled
  reward is race-tier territory, already deferred elsewhere; not
  reinvented here.

## Open questions

None outstanding — the length, scoring split, fatigue cost, and same-time
GC questions were all resolved in the question round above.

## Deferred

- **Sprinters'/climbers' classifications and jerseys (#18)** — layered on
  top once markers (#70) exist; stage races don't need to wait for it.
- **Time-trial stages (#89/#90)** — a stage race works with ordinary road
  stages first.
- **Per-stage leader changes and any GC-aware racing (#38)** — needs team
  tactics to exist at all.
- **Length-scaled GC reward** — waits on race tiers, already deferred in
  `competitions/README.md`.
- **Injury-forced withdrawal beyond a normal DNF (#41)**.
- **GC shown in the race replay (#94)**.
