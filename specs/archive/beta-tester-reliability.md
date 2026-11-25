# Beta testers that probe, report and visit on time

**Status:** implemented
**Issues:** #159, #160
**Domain(s):** `beta_agents/`, `deploy/` (the staging machine's schedule)
**One-liner:** the five LLM beta testers visit staging every eight hours as promised, notice what changed since their last visit, dig into one part of the game each time, and report what they can't explain.

## Why this exists

The testers have been live on staging since 2026-11-18. In seven days they made
75 visits and filed **no reports**. Each visit used 5 to 21 tool calls out of a
budget of 30, and nearly every diary entry ends "everything is running
smoothly". Meanwhile the accountant's balance fell from $451,700 to $355,512
over fourteen visits, losing about $6,000 a game week, and every one of those
entries says "finances and ledger check out perfectly". The testers write the
numbers down but never compare them, and they stop as soon as the visit's
chores are done. A beta tester that never reports anything is not testing (#159).

They also visit less often than promised. Between 2026-11-18 and 2026-11-25
GitHub ran 20 of the workflow's roughly 170 hourly schedules, about one every 6
to 10 hours. Five of those runs came less than 7½ hours after the last visit and
found nobody due, so the regular testers averaged about 10½ hours between
visits, with gaps of up to 15. On the 24× staging clock, 15 hours is more than
two game weeks, so a tester misses races, auctions and whole paydays between
looks (#160).

## Player experience

Here the "player" is the operator, Mario, reading diaries and triaging reports.

Every hour the staging machine reads the testers' diaries, and when one is due
it asks GitHub to start the testers' workflow. GitHub's own hourly schedule
stays on as a backup. Whichever starts a
run, the run visits the testers who are due, as it does today, so each regular
tester now visits about every eight hours and the casual one once a day.

At the start of a visit, before the model does anything, the harness reads the
tester's team as it stands: its balance, how the balance moved, its roster (who
is on it and how many), its league position, and the season and week. It puts
this next to the same reading from the tester's previous visit and gives the
tester a short list of what changed: "balance $441,908 → $429,927 (−$11,981);
roster 10 → 10; position 14th → 12th; Season 3 Week 5 → Week 7". The tester's
first job is to account for each change from the ledger, the results and its own
diary. A change it can't account for is a report.

Each visit also has a **focus area**, which rotates from visit to visit:
finances, roster and riders, the auction market and free agents, races and
results, the development squad, or staff and sponsors. The tester still plays in
its persona, but it spends the rest of the visit digging into its focus area,
cross-checking one endpoint against another and against the player's guide, and
trying the edges of the rules a careful player would try.

If a tester tries to end the visit after only a handful of tool calls, the
harness tells it once that it has barely looked and should keep going on its
focus area. The casual tester is exempt, since short visits are its persona.

The diary entry now has to name at least one critical observation: something
confusing, surprising, missing or suspicious. "Everything is smooth" doesn't
count. The testers are told plainly that a report dismissed in triage costs
nothing, that "looks wrong" exists for exactly the things they can't explain,
and that going three visits without a report means they aren't looking hard
enough.

The operator sees the result in the diaries, which show the change list and the
focus area of each visit, and in the triage queue, which should start to fill.

## In scope

1. Once an hour the staging machine checks whether any tester is due, and if
   one is, starts the testers' workflow. It does so only where it has been
   given a GitHub token for that purpose, so production and local runs do
   nothing.
2. A run started that way, or by GitHub's schedule, visits whoever is due. A
   manual run can still name one tester.
3. Each visit opens with the team's state as the harness read it, and the
   changes since the previous visit's reading. The reading is saved with the
   diary entry so the next visit can compare against it.
4. The tester is told to account for every change and to report any it can't
   explain.
5. Each regular tester's visit has one focus area, rotating through a fixed
   list, shown in the opening message and recorded in the diary entry. The
   casual tester gets none: its visits stay short by design.
6. A regular tester that tries to finish before a minimum number of tool calls
   is pushed back once. The casual tester is exempt.
7. Every diary entry includes at least one critical observation.
8. The instructions state the reporting bar: a dismissed report costs nothing,
   use "looks wrong" for what can't be explained, and three visits without a
   report is a warning sign.
9. A visit's diary footer records its focus area, and how many hours had passed
   since the previous visit, so the operator can see at a glance whether the
   cadence holds.

## Out of scope

- **A quota of reports per visit.** Forced reports would be noise that the
  operator has to triage. The bar in item 8 pushes without forcing. (No.)
- **The harness filing reports itself** from the change list. Whether a change
  is wrong is the tester's judgement, made from the ledger. The harness only
  lays out the facts. (No.)
- **A bigger step budget** than 30 model calls a visit. The testers use about
  half of what they have. (No, for now.)
- **A second model, or a fallback model**, for the free tier's daily limit. At
  eight-hourly visits and at most 30 calls each, the testers stay inside the
  500 free calls a day. (Later, if the limit is ever hit.)
- **Changing the cadence** from eight hours. (No: it is set by the free tier.)
- **An external cron service.** The staging machine already runs a scheduler.
  (No.)

## Rules and edge cases

- **Two triggers in one hour.** If the machine's run and GitHub's scheduled run
  both arrive, they run one after the other, never together, and the second
  finds nobody due. Nothing visits twice.
- **The machine is down or the trigger fails.** GitHub's schedule is still
  there, so the testers fall back to today's patchy cadence rather than
  stopping. A failed trigger shows in the machine's logs and never affects the
  tick.
- **No previous reading.** On a tester's first visit, after an old diary entry
  with no saved reading, or after losing its team, there is nothing to compare
  with. The opening message says so, and gives the current reading only.
- **The team changed.** If the tester now manages a different team than at its
  last reading, the comparison is skipped and the message says the team
  changed.
- **An unreadable part.** If one part of the reading fails (for example the
  league table errors), that part is shown as unavailable. The error is itself
  something the tester may report. The visit goes ahead.
- **Pushing back on an early finish** happens only once a visit. A tester that
  insists ends its visit.
- **Only asking GitHub when someone is due.** The machine checks the diaries
  before it starts a run, so an hour with nobody due costs nothing. A run that
  only finds nobody due would still use some of the repository's Actions
  minutes, which are limited on a private repository.
- **Paused means paused.** While the testers are paused, the machine's hourly
  runs do nothing, exactly like GitHub's schedule.
- **The focus area and the persona.** The focus is added on top of the persona.
  A trader whose focus is the development squad still checks its bids.
- **Daily allowance.** Pushing for longer visits must keep the five testers
  within the free model tier's daily calls at the eight-hourly cadence.

## Decisions taken

- Trigger: the staging machine's scheduler starts the workflow hourly, with
  GitHub's cron kept as a backup (Mario, default).
- The harness lays out the changes since the last visit, read from the game
  itself (Mario, default).
- A rotating focus area per visit, on top of the persona (Mario, default).
- At least one critical observation in every diary entry (Mario, default).
- A minimum effort pushback, once, with casual exempt (Mario, default).
- The reporting bar stated plainly, with no quota (Mario, default).
- Stay on the one free Gemini Flash-Lite model, at $0 (Mario, default).

## Open questions

None.

## Deferred

- **A fallback model** for a hit daily limit: not needed at today's volume.
