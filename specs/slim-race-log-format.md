# Slim and compress the race log format

**Status:** proposed
**Domain(s):** `racing/`, `race_engine/`, `race_player/`
**One-liner:** A saved race replay becomes a small file that loads instantly, instead of a 75 MB one that does not.

## Why this exists

Every simulated race writes a replay file, and that file is the only record of
what happened — it cannot be regenerated, because the engine keeps changing and
a re-run would disagree with the standings already recorded. A single mountain
stage currently writes 75.7 MB. A season of them is tens of gigabytes, on a
project whose entire hosting budget is free tiers.

Nothing about the race needs that much space. The file repeats the course
profile, the team names and every rider's name on all 18,961 lines, stores
positions to a millionth of a metre, and is not compressed at all. Removing
only the waste — no change to what a viewer can see — takes the same race
under 1 MB. Doing it now, before the game is deployed and before there is any
stored history to protect, costs nothing; doing it later means either living
with the size or migrating real player data.

## Player experience

A player opens a finished race from the calendar and clicks to watch the
replay. The race appears essentially at once — the file arrives in well under
a second even on a slow connection — and plays exactly as it does today: the
elevation profile, the packs forming and splitting on the climbs, the gaps
opening, the finish.

They cannot tell anything has changed. The riders move as smoothly, the energy
and stamina bars read the same, the finishing times and the gaps between them
are identical to the result table on the previous screen. The replay covers the
same race at the same length; a stage that took four hours still takes four
hours of race time to play through, and the speed controls behave as before.

The only difference they could ever notice is that a replay no longer takes a
visible moment to load, and that races they watched before this change are gone
— the game has no stored history yet, so in practice there are none.

## In scope

1. A saved replay of a full mountain stage is under 2 MB, down from 75.7 MB.
2. A replay begins playing without a perceptible wait on a normal connection.
3. The replay shows the same course, the same teams and the same riders, by
   name, team and role, as it does today.
4. Rider positions, speeds, energy and stamina during a replay are visually
   indistinguishable from today's.
5. Every rider's finishing time in the replay matches the finishing time in
   the race result table exactly, and the gaps between riders are unchanged.
6. The replay covers the whole race from the neutral start to the last rider
   home, at the same race duration as today.
7. Replays play, pause, seek, step and run at every speed setting exactly as
   they do now, and the elapsed/total race time readout stays correct.
8. A race simulated before this change is no longer viewable. No replay from
   the old format is offered, converted, or partially rendered.
9. The sample races bundled for development are regenerated so the replay
   viewer works out of the box.

## Out of scope

- **Regenerating a replay from a stored seed.** Already rejected in
  `racing/README.md` and not revisited — a replay regenerated on a newer engine
  would contradict the results recorded at the time.
- **Moving replays to external object storage.** Deliberately Later. At the
  new size, a whole season fits comfortably where replays already live. This
  feature is what turns that move into a configuration change rather than a
  project.
- **Converting or reading old replays.** Cut. The game is not deployed; there
  is no player-owned history to protect, and supporting two formats would
  permanently double the viewer's parsing for data nobody has.
- **A replay that streams or loads in parts.** Cut — engineering for a wait
  that this feature removes.
- **Squeezing the file further at high compression cost.** Later; roughly a
  further quarter off, paid for with a long pause at the end of every
  simulated race.
- **Course markers on the replay timeline.** Belongs to
  [#70](https://github.com/mario595/cycling-manager/issues/70), which adds a new
  kind of record on top of whatever format exists. Sequenced after this, not
  merged into it.
- **Deciding how long replays are kept.** No. Nothing needs expiring at this
  size.

## Rules and edge cases

**Everything constant is stated once.** The course, its segments, the teams in
the race and each rider's identity do not change during a race and are
recorded once per replay rather than on every moment of it. A replay with no
teams configured is still valid and still states so.

**Positions and efforts are recorded to the precision a viewer can show.**
Sub-centimetre position and fractional-percent energy are recorded no more
finely than a screen can draw them. This is a deliberate, permanent reduction
in stored precision, chosen because no current or planned view consumes it.

**The replay samples the race every two seconds rather than every second.**
This halves the recorded moments. It is the one change in this feature that
loses information, and it cannot be undone after the fact. It was chosen
knowingly: at every available playback speed the viewer cannot show the
difference, and the finishing data that results depend on is preserved exactly
(below).

**Finishing times stay exact.** A rider's finishing time is recorded as the
simulation computed it, never snapped to a sampled moment. The visible instant
at which a rider's marker stops moving may therefore fall up to two seconds
after they actually crossed the line, but every time, gap, position and
group-finish grouping is identical to today's. Snapping finishing times to the
sample grid is explicitly forbidden — it would manufacture ties in a bunch
sprint that did not happen and contradict the recorded results.

**A replay states its own sampling interval.** The viewer must not assume it.
Elapsed time, the seek control, and the playback loop all derive race time
from the stated interval, so the readout stays in real race seconds however
the replay was sampled.

**Nothing about a rider is optional any more.** Today the viewer tolerates a
missing team, a missing role and missing team names, falling back to a neutral
colour and assuming leadership, purely because replays predating those features
existed. With a single format those fallbacks are removed: a replay that fails
to state a rider's team or role is malformed, and should be treated as such
rather than quietly rendered wrong.

**A replay's recorded metadata means what it says.** The stored count of
recorded moments is a count of samples, not of race seconds, and the stored
size is the size of the file as kept. Neither may be presented as the other.

**Compression is invisible to the viewer.** A replay is stored compressed and
delivered so that the browser unpacks it on arrival. The viewer fetches and
reads a replay exactly as it does now; it does not unpack anything itself.

**A race is still simulated at full resolution.** The sampling described here
is about what gets written down, not about how the race is computed. The
simulation itself is unchanged, and so are its results.

## Decisions taken

- **Include coarser sampling?** Yes — two-second sampling, overruling the
  recommendation to keep every second. Accepted as a permanent information
  loss.
- **How precisely are positions and efforts stored?** To roughly the precision
  a viewer can render, not to full floating-point.
- **Do old replays get converted?** No. New format only; no reader, no
  migration. Bundled development samples are regenerated.
- **How is a replay compressed and delivered?** With a compression method every
  current browser unpacks natively, delivered so the browser does the
  unpacking. The viewer's loading code is unchanged.
- **Do finishing times move to the sample grid?** No. They stay exactly as the
  simulation computed them.
- **Where do replays live?** Where they live today. External object storage
  stays a later configuration change, which this feature makes easy rather than
  necessary.
- **Does a replay load all at once?** Yes. At the new size there is nothing to
  stream.
- **Ship together with course markers (#70)?** No. This defines the format;
  #70 then adds to a format that is already clean.

## Open questions

None.

## Deferred

- **Higher-effort compression** — roughly a further quarter off the file, at
  the cost of a substantial pause at the end of every simulated race. Revisit
  if that pause proves acceptable, or if storage ever becomes pressing.
- **Moving replays to external object storage** — unnecessary at the new size;
  reduced to a configuration change by this feature.
- **Course markers on the replay** — [#70](https://github.com/mario595/cycling-manager/issues/70), sequenced after this.
