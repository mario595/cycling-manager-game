# Watch a finished race

**Status:** implemented
**Domain(s):** `racing/`, `frontend/`, `race_player/`
**One-liner:** A finished race's screen lets the player watch a tick-by-tick replay of how it actually unfolded.

## Why this exists

The game already simulates every race in full detail and keeps the record of
it — `race_engine/` produces a tick-by-tick log and `race_player/` is a
complete visualizer built to show it: elevation profile, rider markers, pack
grouping, playback controls. None of that reaches a player. A finished race
today is only a scoreboard — a result table and a static course profile —
even though the game already knows exactly how the race was won.

Watching a race turns a race day from a number appearing in the standings
into something that happened. It gives the manager's squad choices and
tactics somewhere to be seen paying off (or not), rather than only inferred
from a finishing order.

## Player experience

A manager opens a race that finished earlier in the day. The screen shows
the race's name, date, distance and course profile — but, unlike today, it
does not immediately show who won. Instead there is a "Watch race" button
and, separately, a "Show results" toggle that's off by default.

Clicking "Watch race" opens the replay. It fills the screen with room to
breathe: the elevation profile with riders spread along it as coloured
markers, bunching into blobs where the pack is tight and spreading out where
the race has split. A short loading moment while the replay's data arrives,
then it opens paused at the start line. Playback controls let the manager
press play, jump to any point with a seek bar, and speed through the boring
flat kilometres. A list below shows every rider, grouped into the packs they
are actually riding in at that instant, with time gaps between groups.

The manager's own riders are easy to pick out from the other 60-odd —
highlighted in the profile and the list, the way "your team" is already
highlighted elsewhere in the game (the league table). A rider who was pulled
from the race by the time cut is shown as out of contention, not left
frozen mid-road looking like they're still fighting for position.

The manager can scrub straight to the finish, or press "Show results" at
any point — on the replay or back on the race screen — to see the finishing
order and prize money without watching a second of the race. Nothing is
forced; the hidden-by-default state is a courtesy for someone who wants to
watch it unfold, not a lock.

If a finished race has no replay to show — an older race recorded before
this shipped, or one whose log could not be read — the race screen says so
plainly next to where the "Watch race" button would be, and everything
else on the screen (results, once revealed) still works normally.

The whole thing looks and feels like part of the game: the same typography,
colours and control style as the rest of the app, not a separate tool
bolted on.

## In scope

1. A finished race's screen offers a "Watch race" action.
2. Results (rider results, team points, prize money) on the race screen are
   hidden by default and revealed by an explicit "Show results" action.
   The course profile, and the race's name/date/distance/status, are always
   visible.
3. "Watch race" opens a full replay of that specific race: elevation
   profile with rider positions, pack grouping, playback controls
   (play/pause, speed, seek to any point), and a list of every rider
   grouped by pack with time gaps.
4. The replay's controls, typography and colours match the rest of the
   game rather than looking like a separate tool.
5. The manager's own team's riders are visually distinguished from every
   other rider in both the profile and the rider list.
6. A rider removed from the race by the time cut is shown as out of the
   race, distinctly from a rider still riding.
7. "Show results" is reachable both from the race screen directly and from
   inside an open replay, and reveals the same thing either way.
8. Any logged-in player can watch any finished race, regardless of which
   team (if any) they manage.
9. A finished race with no usable replay tells the player so, in place of
   the "Watch race" action, without affecting anything else on the screen.

## Out of scope

- **Spoiler protection anywhere other than the race screen.** Standings,
  finances, and a rider's own race history continue to show results as
  they do today. Hiding results everywhere is a much larger feature and
  fights against results being public information. **No.**
- **Remembering which races a player has already watched or revealed.**
  Results start hidden on every visit to the race screen; the player
  reveals them again if they return. **Later** — needs a place to persist
  per-player state that doesn't exist yet.
- **Linking from a rider marker or the rider list to that rider's profile.**
  Not needed to watch a race play out. **Later.**
- **Watching a race while it is in progress, or "live."** The game
  simulates an entire race in one step when its scheduled time arrives;
  there is no in-progress state to watch. **No.**
- **Team jersey colours in the replay.** The replay keeps its own
  12-colour palette rather than switching to each team's actual jersey
  colours — with up to 16 teams in a race, colours already repeat, and
  jersey colours have never been checked for being distinguishable from
  each other. The own-team highlight (item 5, above) is how a player finds
  their riders instead. **Later**, and only once team colours have a
  distinguishability rule of their own.
- **A rider's individual pull/surge tactics, or any explanation of *why*
  the race unfolded as it did.** The replay shows what happened, not a
  narrated account of it. Belongs to a different feature, if ever.

## Rules and edge cases

- Results being hidden is a per-visit UI state, not a stored preference —
  reloading the race screen or returning to it later starts hidden again.
- "Show results" and "Watch race" are independent: a player can reveal
  results without ever opening the replay, or watch the whole replay
  without revealing results, or do both in either order.
- The own-team highlight marks the riders who **raced for the player's
  team in that race** — not the riders the team has under contract today,
  and not whoever managed the team on race day. A rider sold since still
  shows highlighted in the old replay (they rode for this team that day);
  a rider signed since does not (they rode for someone else). A team
  claimed after the race still sees its riders from that day highlighted.
  A race where the player's team did not field a squad shows no
  highlighted riders at all, not an error.
- A rider who did not finish because of the time cut is visually distinct
  from both a still-racing rider and a rider who finished — the replay
  must not represent "pulled from the race" as if they simply stopped
  making progress on their own.
- Missing or unreadable replay data is expected to happen for some
  historical races and must degrade gracefully — the rest of the race
  screen (name, date, distance, course, and results once revealed) is
  unaffected.
- The replay is a complete, already-decided record. Nothing about it
  changes based on when the player watches it, and watching it never
  affects results, standings or anything else in the game.

## Decisions taken

- Replay opens on its own screen, not inline on the race page or as a
  full-screen overlay — a replay needs room, and a dedicated screen keeps
  the race screen itself uncluttered. **Decided in scoping.**
- Results are hidden by default on the race screen, with an explicit
  toggle to reveal them, rather than shown immediately (today's behaviour)
  or fully hidden until an explicit "watch first" flow. **Decided in
  scoping.**
- The manager's own team is found via a highlight, not by switching every
  team to its jersey colours — cheapest fix for the thing a manager
  actually looks for when watching. **Decided in scoping.**
- The highlight follows the team a rider **raced for** that day, not their
  current contract — the same way the results table labels teams, and
  the only reading consistent with the replay's own team colours.
  **Decided while planning** (corrects an earlier wording in this spec).
- The replay must visually match the rest of the game (typography, colour,
  controls) before this ships, rather than shipping with its current,
  separate look. **Decided in scoping.**
- Spoiler protection is scoped to the race screen only; every other screen
  that already shows results (standings, finances, rider history) is left
  as is. **Decided in scoping** — game-wide spoiler protection is a much
  larger feature.
- Any logged-in player can watch any finished race — races and their
  results are already public information in this game. **Decided in
  scoping**, matching how results already work.

## Open questions

None outstanding — the scoping conversation resolved every open question
from the original ticket.

## Deferred

- **Remembering watched/revealed state per player** — needs a persistence
  mechanism that does not exist yet; a courtesy default (hidden) is enough
  for now.
- **Rider links from the replay to rider profiles** — not needed to watch
  a race; adds real value later with little urgency.
- **Team jersey colours in the replay, with a distinguishability rule** —
  depends on a colour-management feature for teams that doesn't exist yet;
  the own-team highlight covers the immediate need.
