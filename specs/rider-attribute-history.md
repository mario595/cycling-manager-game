# Rider attribute history

**Status:** proposed
**Domain(s):** `riders/`
**One-liner:** Every rider's five displayed attributes are recorded over time, so a career arc can eventually be shown.

## Why this exists

`riders.Rider` stores only each attribute's current value. Growth and decline
(#58) move those values every week, but nothing records where a rider has
been — a rider who climbed from 6 to 8 over two seasons looks, today, exactly
like a rider who was always an 8. The hidden-attribute design promises that a
player who watches a rider over time can form a justified opinion about them;
without a record of that time passing, there is nothing to watch.

This has to start before anything consumes it. History only accumulates
forward — a season not recorded is gone permanently — so the cheapest version
shipped now beats a considered version shipped once the rider page (#96)
wants it.

## Player experience

Nothing changes on screen. This feature is invisible on its own — it exists
so that a future screen (#96's rider detail view) has something to plot. The
player experience it enables, once #96 ships, is a line graph on a rider's
page: five lines, one per attribute, each a step whenever that attribute's
shown rating changed. A manager who has followed a young rider for two
seasons can look at that graph and see the climb; a manager looking at a
rider they just signed sees only the flat stretch before they owned them,
because the rider's whole career — every team, every season — is on the
record, not just the time since it was bought.

## In scope

1. Every rider in the game world — on a managed team, an unmanaged team, or
   a free agent — has their five displayed attributes (climb, sprint, flat,
   resistance, positioning, each 0-10) recorded at the moment they are
   generated.
2. After generation, a new record is added for a rider only in a week where
   at least one of their five displayed attributes actually changed from the
   previous record. A week where nothing moved adds nothing.
3. A rider's full attribute history can be read back in chronological order.
4. History is permanent. It is never deleted as a side effect of anything
   that happens to the rider it belongs to.

## Out of scope

- **Any screen or API that shows this history to a player.** That is #96's
  job, once this ticket has something for it to read.
- **Snapshotting anything other than the five displayed attributes** —
  freshness, salary, hidden traits. Hidden traits by design never appear
  anywhere a player can see them, this included.
- **Making retirement a real, non-destructive state.** See *Conflicts*,
  below — that decision belongs to #42, not here.
- **Changing what `reset_riders` does today.** It remains a destructive
  pre-launch dev tool; see *Conflicts*.
- **A configurable or per-feature cadence.** One rule, always: on change,
  checked every week.

## Rules and edge cases

- **The record is of the displayed value, not the stored one.** The display
  scale exists precisely so a rider can improve without the shown number
  moving; recording the finer stored value would show the player movement
  the design deliberately hides. A record is exactly what the player could
  have seen on the roster that week.
- **"Changed" means the displayed value, not the stored one, moved.**
  Several weeks of stored-value movement that never crosses a display
  threshold produce no record, by the same logic.
- **A late tick still records at the right moment.** If the game clock falls
  behind and a tick processes several missed weeks at once, each week's
  change (if any) is still attributed to that week, not bunched into the
  week the tick happened to run.
- **A rider's very first record exists the moment they exist.** Generation
  writes a baseline record immediately, so a graph never starts empty and a
  rider who never changes still plots as a flat line rather than nothing.
- **History is never deleted by anything this ticket does.** A rider's
  record survives whatever the rider survives.

## Conflicts

**"Riders are never deleted" is a bigger decision than this ticket, and it
belongs to retirement (#42), not here.** Today, `reset_riders` deletes every
rider (and their race results) outright, and `riders/README.md` defends that
explicitly as correct for a pre-launch world with no real players attached —
revisit it, the README says, once the game has real accounts. Making history
permanent does not require making riders themselves permanent; it only
requires that nothing *this* feature does destroys a record early. The
decision to turn retirement into a state a rider enters rather than a row that
gets deleted — and to make an old race result link through to a rider who is
no longer on any roster — is #42's to make. This spec commits to history
outliving whatever happens to the rider record it describes, once riders stop
being deleted; it does not itself change `reset_riders`, and does not
implement retirement.

## Decisions taken

- Cadence: weekly, recorded only when a displayed value changes — not every
  week unconditionally, not once per season.
- Resolution: the displayed 0-10 value, never the stored finer-grained value.
- Coverage: every rider in the world, not just those on managed teams.
- Player-visible surface: none. This ships silently; #96 is the consumer.
- Baseline: a rider gets a first record at generation, not only on first
  movement.
- Deletion: history is meant to be permanent, but making rider rows
  themselves permanent is #42's decision, not this ticket's — see
  *Conflicts*. `reset_riders`'s current destructive behaviour is unchanged
  here.
- Row-count estimate: a 200-team, ~2,400-rider world would produce roughly
  29,000 records a season even under unconditional weekly recording, and
  proportionally less under on-change recording. Not a constraint on any
  decision above — change-only recording is chosen for graph honesty, not
  storage size.

## Open questions

None outstanding.

## Deferred

- **#96's line graph and any other player-visible surface** — the reason
  this exists, but not this ticket's job.
- **Retirement as a non-destructive state (#42)** — needed before "history
  is permanent" is fully true, since a deleted rider's history currently
  goes with it via cascade.
- **Snapshotting freshness, salary, or anything beyond the five displayed
  attributes** — no current need identified.
