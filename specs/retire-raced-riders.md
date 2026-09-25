# Retire raced riders instead of deleting them

**Status:** proposed
**Domain(s):** `transfers/`, `riders/`, `world/`
**One-liner:** A free agent who has ever raced is retired, not deleted, when the pool expires them — their history stays put; only a rider nobody ever fielded is removed outright.

## Why this exists

Pool expiry (#29) removes a long-unattached, cheaply-priced free agent from
the market by deleting the `Rider` row. That deletion cascades to every
`RaceResult` and squad-membership row the rider ever had. If the rider was
once claimed onto a team, raced for it, and was later released and left
unsigned, expiry erases their name from every past race they rode — races
that already happened, whose result tables a player may have already seen
and could reload later with a row missing.

It also breaks the rider page (#96): a race result links to the rider who
earned it, and that link should keep working for as long as the race itself
is remembered. A rider who genuinely never got a look — generated into the
pool, never claimed, never raced — carries nothing worth keeping, and
removing them is exactly what expiry is for.

## Player experience

A manager scrolls back through an old race's results and clicks a name they
don't recognise — someone who rode for a rival months ago. The page opens
normally: attributes, career totals, every race they ever finished. In place
of a team, it says **Retired**, with the week and season they left the
pool. Nothing on the page is stale or broken — it's exactly how the rider
looked on the day they retired, because a retired rider never changes
again: no more growth, decline, training or recovery.

The manager cannot sign this rider, release them, or find them on the
free-agent market — retirement took them out of circulation for good.
Nobody was notified when it happened; expiry has always been quiet pool
hygiene, and this is no different.

A different old race, a different name clicked — this one really is gone.
Nothing links to a page for them anymore because they never raced, so
there's no dedicated history for the game to keep. This case is already
handled: the page says the rider is no longer part of the game.

## In scope

1. When weekly expiry (the existing time-unattached-and-low-value check)
   selects a free agent who has **at least one race result**, that rider is
   **retired** instead of deleted: removed from the free-agent pool for
   good, but the `Rider` row and every `RaceResult` / squad-membership row
   referencing them are kept exactly as they were.
2. A retired rider is never a free agent again. They cannot be signed,
   cannot be released (they aren't on any roster), and do not appear in the
   free-agent pool or any listing of it.
3. A retired rider's attributes are frozen from the moment of retirement
   onward: no further weekly growth, decline, training effect, or freshness
   recovery. Their age also stops advancing.
4. A retired rider's page (#96) shows exactly what an active rider's page
   shows — attributes, career totals, full race history — with **Retired**
   in place of a team, and the week and season retirement happened.
5. Every past race's result table and squad list keeps the retired rider's
   row, and their name keeps linking to their (now-retired) page.
6. A free agent who expires under the existing condition and has **never**
   appeared in a `RaceResult` continues to be deleted outright, unchanged
   from today.
7. Retirement, like expiry today, is silent — no notice to anyone, no
   countdown, nothing on the free-agent market hinting it's coming.

## Out of scope

- **Any list or count of retired riders.** A manager reaches a retired
  rider only by already having a link to them (a race result, a bookmark).
  There is no "browse retired riders" screen. Later, if it turns out to
  matter.
- **Telling a retired rider apart from an active free agent on any pool
  screen.** They're never on a pool screen — retirement removes them from
  it entirely, the same way expiry's deletion does today. Not needed.
- **Re-signing a retired rider, at any cost.** No. Retirement is as final
  as deletion is today; a "comeback" mechanic is a different feature and
  would immediately raise questions this ticket has no reason to answer.
- **Any notification that a rider retired**, to their former manager or
  anyone else. No — matches expiry's existing silence.
- **Restoring riders already deleted by expiry before this ships.** No —
  that data is gone; this changes behaviour going forward only.
- **Age-based retirement** ([#42](https://github.com/mario595/cycling-manager/issues/42)) —
  belongs to its own spec, and reuses the "Retired" state this ticket
  defines rather than inventing a second one. Later.
- **A visible marker on old race-result rows showing a name is retired**
  (versus just clicking through and finding out). Later — waits until
  retirement is common enough (post-#42) that it's worth the space on the
  results table.

## Rules and edge cases

- "Has raced" means the rider has at least one `RaceResult` row, including
  a did-not-finish. Being named to a squad without ever getting a result
  recorded does not count — that rider is treated as never having raced.
- The time-and-value expiry condition itself (unattached long enough, and
  priced in the pool's low end) is unchanged — this only changes what
  happens once a rider is selected by it, and only distinguishes the outcome
  by race history.
- A rider already in the pool when this ships is judged by the new rule
  the next time expiry runs — nothing is retroactive to riders already
  deleted.
- A retired rider keeps whatever attribute values, age, and freshness they
  had at the moment of retirement, forever. They are a historical record,
  not a rider anyone can field, train, or otherwise affect.
- Retirement does not touch the ledger. No fee is paid or refunded — the
  rider was already a free agent, exactly as an expiry-deletion pays and
  refunds nothing today.
- A rider retired this way and a rider retired later by #42 end up in the
  same state. This spec is where "what a retired rider is" gets decided;
  #42 only adds a second path into it.

## Decisions taken

- A raced free agent is retired, not exempted from expiry outright —
  otherwise nearly every released rider (almost all of whom have raced)
  would stop expiring at all, and the pool would only grow. Decided in
  scoping.
- A never-raced free agent is still deleted outright, unchanged from
  today's behaviour — nothing about them is worth keeping, and the ticket's
  own split (delete vs. some other resolution) is kept rather than
  retiring everyone. Decided in scoping.
- Retirement is final — no re-signing, at any cost, ever. Matches the
  finality retirement will need once #42 makes it an age-driven, common
  outcome. Decided in scoping.
- A retired rider's page is the full, normal rider page — not a stripped
  history-only view — with attributes frozen and "Retired" standing in for
  a team. One page layout for every rider, not a second one for retired
  riders. Decided in scoping.

## Open questions

None outstanding.

## Deferred

- **A visible "retired" marker on old race-result rows.** Waits until #42
  ships and retired riders show up in results often enough to be worth
  the row space.
- **Age-based retirement** (#42) — the other path into the same "Retired"
  state, its own product spec.
