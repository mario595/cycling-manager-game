# Race Player / Visualizer

A standalone React-based web application for visualizing race simulations produced by `race_engine`.

## Project Goals

- **Primary:** Provide a sophisticated, interactive visualization of race logs (`.jsonl` files).
- **Design:** Mimic professional cycling visualizers like Strava or VeloViewer (elevation profile + rider markers).
- **Integration:** Must be modular and portable enough to integrate into the future Django-based game web app.

## Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| **Build Tool** | Vite | Fast HMR, excellent React support. Dev server also serves the `/api/races` listing endpoint. |
| **UI Library** | React 19+ | Functional components and hooks. |
| **Language** | TypeScript | Strict typing for race data and props. |
| **Styling** | Tailwind CSS | Utility-first CSS for rapid UI development. |
| **UI Components** | Ant Design (antd) | UI kit (Segmented, Button, Space). |

## Data Source & Format

### Input
- **File:** `.jsonl` files in `public/` (produced by `race_engine`).
- **Structure:** One JSON object per line, representing a full snapshot of the race at a specific tick (1 tick = 1 second).

### Key Data Fields
- **Segments:** Array of `{ length, gradient }` objects. Used to derive the elevation profile.
- **Teams:** Top-level `teams` object on every tick line, sibling to
  `course_length`/`segments` — **not** per-rider: `{ "t1": { "code": "ALP",
  "name": "Alpine Racing" }, ... }`, a `team_id -> {code, name}` map. `code`
  is the UCI-style 3-letter TV abbreviation; `name` is the full team name
  (engine-enforced non-empty whenever a team block exists — see
  `race_engine/config.py`'s `_parse_teams`). Written even when no teams are
  configured (`"teams": {}`) — **optional** in TypeScript only because logs
  predating this change lack the field entirely; `parseRaceLog` reads it
  once from the first snapshot (both are static for the race) into
  `ParsedRace.teamCodes`/`teamNames`, defaulting to `{}`. See `teamCode()`/
  `teamName()` in `utils/teamColors.ts`.
- **Riders:** Array of rider objects containing:
  - `id`, `name`
  - `team` (string team id, e.g. `t1`-`t4`) — **optional.** Absent on logs
    predating team tactics; falls back to a neutral colour (`teamColor()` in
    `utils/teamColors.ts`).
  - `role` (`"leader"` | `"support"`) — **optional.** Absent riders default to
    leader (`isLeader()` in `utils/teamColors.ts`), matching the engine's own
    dataclass default. Exactly one leader per team when present.
  - `pos` (meters from start)
  - `speed` (m/s)
  - `energy`, `stamina` (0-100)
  - `pulling`, `surging` (booleans) — `pulling` is set only for the rider
    setting the pace at the front of a pack; there is no separate "drafting"
    flag (shelter degree in a pack is continuous, not a meaningful boolean —
    every non-pulling pack member is assumed to be benefiting to some
    degree; see `race_engine/DOMAIN.md`'s "Drafting & pack cohesion")
  - `finished`, `finish_time`

### Elevation Derivation
Since absolute altitude is not stored in the engine logs, it must be derived from the segment data:
1. Initialize `elevation = 0`.
2. For each segment in the course:
   - Calculate `elevation_change = segment.length * (segment.gradient / 100)`.
   - Add to cumulative `elevation`.
   - Store as part of the profile coordinate data.

## Core Features

### 1. Elevation Profile Visualization
- **Type:** Custom SVG area chart (`ElevationProfile.tsx`).
- **Coloring:** Gradient-colored area based on the slope (green for flat, blue for descents, yellow→red for climbs).
- **Gradient Labels:** Shows `%` labels below each segment (only for segments wide enough to avoid overlap).
- **Rendering unit is the pack, not the rider.** The profile consumes
  `Pack[]` from `computePacks` (the same packs `RiderList` renders), not a
  flat rider list — a bunch of 40+ riders at one x-coordinate is otherwise
  unreadable. **Adaptive rule:** packs of 1-2 riders render as individual
  `RiderMarker`s; packs of 3+ collapse into a single `PackMarker` blob at the
  pack's `frontPos`. The size boundary is damped with hysteresis (become a
  blob at 3, split back to individuals at 1) to avoid flicker for a pack
  hovering at the threshold — see `BLOB_SPLIT_SIZE`/`BLOB_MERGE_SIZE` in
  `ElevationProfile.tsx`.
- **Rider Markers (`RiderMarker.tsx`):** Team-coloured circle (`teamColor()`).
  Leaders are larger (radius 7 vs 5, or 9 vs 7 when active) and carry a white
  inner dot — never an emoji at this scale. Team identity is colour; leader
  identity is shape, kept orthogonal per design.
- **Pack Blobs (`PackMarker.tsx`):** A single glyph per bunched pack:
  - **Size** scales sub-linearly (∝ √riders) so a 40-rider bunch doesn't
    dwarf a small break, clamped to a min/max radius.
  - **Composition** is a segmented donut ring, one arc per team coloured and
    sized by that team's share of the pack (segments sorted by team id for
    tick-to-tick stability).
  - **Leaders present** get a small coloured pip around the ring, capped at a
    few pips with the ring carrying the rest.
  - **Rider count** is centred in the donut hole once the blob is large
    enough to fit it legibly.
- **Z-order:** Larger packs paint first so smaller packs/individuals paint on
  top — a lone attacker off the front must never render behind the bunch it
  escaped.
- **Interactivity:** Clicking a rider marker or pack blob selects it (packs
  select their front rider, reusing the existing selection path). Hovering
  shows a stats tooltip (individual rider) or a composition tooltip (pack:
  size, per-team counts, leaders named) — both tooltip boxes size themselves
  to their actual content.
- **Team colours:** 12-colour palette in `utils/teamColors.ts`, validated for
  perceptual separation and contrast — do not substitute hues without
  re-validating (see `race_player/TEAM_VISUALIZATION_PLAN.md`). Riders/packs
  with no team use a neutral slate, not part of the 12.

### 2. Playback Controls
- **Start/Pause:** Toggle button to start/stop the simulation.
- **Keyboard:** `←` steps back, `→` steps forward, `Space` toggles play/pause.
- **Speed Selector:** Options for x1, x2, x5, x10, x25, x50 playback speeds.
- **Seek Slider:** Native `<input type="range">` (not antd `Slider`, see known issue below) spanning `0..maxTicks`; scrubs to any tick regardless of play state.
- **Elapsed/Total Display:** Ticks (1 tick = 1s) formatted as `Hh Mm Ss / Hh Mm Ss` (hours/minutes omitted when zero).
- **Logic:** `useEffect` with `setInterval` advances ticks based on selected speed.

### 3. Rider Leaderboard (Packs)
- **Pack Grouping:** Riders are grouped into packs mirroring the race engine's cohesion algorithm: BFS connected components over riders within `PACK_COHESION_DISTANCE (60m)` on draft-allowed terrain (gradient ≤ 5%). A single rider is its own pack. Finished riders are included (frozen at their finish `pos`), so they naturally separate into their own pack as the field behind them keeps moving.
- **Ranking tie-break:** Rows (and pack membership) sort by `pos` descending,
  but once several riders finish they all share the same `pos`
  (`course_length`) — ties are broken by `finish_time` ascending
  (`comparePosition()` in `computePacks.ts`) so the actual first-across-the-
  line rider ranks #1, not whoever happens first in the source array.
- **Gap Dividers:** Time gap displayed between adjacent packs (front-to-rear distance / trailing pack speed), formatted as `+Xm Ys (Zm)` — minutes/seconds with the raw meter gap in parentheses.
- **Columns:** Rank, Team, Name, Km, Speed, Result, Energy/Stamina bars.
- **Finished Riders:** Stay in the list (not removed) with a ✅ prefix on their name; speed cell shows `✓` instead of km/h.
- **Leader Highlight:** Visual distinction for the current race leader (highest `pos`).
- **Team Colour Bar:** 3px left border on each row in the rider's team colour
  (`teamColor()`), cheap enough to survive rows re-sorting into packs every
  tick.
- **Team Code Column:** The rider's 3-letter UCI code (`teamCode()`), coloured
  to match the row's team colour bar. Shows `—` when the rider has no team or
  the log predates team codes — same optional-field fallback as team colour.
  Hovering the cell shows the full team name (`teamName()`) via a native
  `title` attribute — no custom tooltip component, since it's one line of
  plain text.
- **Team Leader Crown:** 👑 prefix on the rider name (via `isLeader()`),
  alongside the ✅ finished prefix.
- **Result Column:** Per-row, independent of every other row — blank
  (`—`) while that rider is still racing (`rider.finished === false` in the
  *currently displayed* tick; note the precomputed results map holds a
  finish time regardless of tick, so the cell must gate on the live
  `finished` flag, not just presence in the map). Once a rider finishes:
  the winner (earliest `finish_time` across the whole race) shows their
  finish time as `hh:mm:ss`; every other finished rider shows their time gap
  to the winner as `+mm:ss` (`formatGapTime`/`formatFinishTime` in
  `utils/formatTime.ts`). Km/Speed are never replaced — they keep showing
  live data for every row for the whole race; Result is a pure addition.
  - **Group finishes:** riders who cross in the same bunch as the finisher
    immediately ahead of them get `+0`, chained down the group (3rd/4th+
    riders in a bunch sprint inherit it too, not just the 2nd). "Same group"
    reuses the existing `PACK_COHESION_DISTANCE` (60m) rather than a new
    threshold: at rider X's finish tick, is X within 60m of the previous
    finisher's position at that same tick? See `computeRaceResults()` in
    `utils/raceResults.ts`. A tight bunch sprint can legitimately collapse
    the *entire* field to `+0` this way if each successive gap stays under
    60m — that mirrors real UCI bunch timing, not a bug.
  - Computed once per loaded race (`useMemo` keyed on `raceData`, not on
    `tick`) since results never change as playback proceeds.
- **Legend:** Footer legends `pulling`/`surging`/👑, plus one swatch per team
  actually present in the loaded race (not all 12 when fewer are racing);
  wraps onto multiple lines at the 12-team ceiling rather than truncating.

### 4. File Explorer (Sidebar)
- **Location:** `FileExplorer.tsx` — standalone dev tool, decoupled from player logic.
- **Endpoint:** `GET /api/races` returns `{ files: [{ name, mtime }, ...] }` listing all `.jsonl` in `public/`, `mtime` as an ISO timestamp; the sidebar shows each file's last-modified date/time below its name.
  - Dev: Vite plugin in `vite.config.ts` (middleware, not built into the app).
  - Prod: custom `RaceHandler` in `serve_viewer.py` + copies all `.jsonl` into `dist/`.
- **Refresh button:** Re-fetches the file list without page reload.
- **Selection:** Clicking a file loads and parses it via `App.tsx`; the `RaceViz` component receives parsed data as a prop — zero coupling to the file system.

## Architecture

### File Structure
```
race-player/
├── public/
│   └── *.jsonl                 # Race data files (any number)
├── src/
│   ├── components/
│   │   ├── RaceViz.tsx         # Main container: playback loop, keyboard, pack computation
│   │   ├── ElevationProfile.tsx# Custom SVG area chart with gradient coloring + labels
│   │   ├── RiderMarker.tsx     # Custom SVG circle marker (memoized), team colour + leader shape
│   │   ├── PackMarker.tsx      # Segmented-ring pack blob (memoized): size, team composition, leader pips
│   │   ├── PlaybackControls.tsx# Play/Pause, speed selector, tick counter
│   │   ├── RiderList.tsx       # Pack-grouped table with gap dividers, team colour bar, crown
│   │   └── FileExplorer.tsx    # Dev sidebar: lists .jsonl, refresh, standalone
│   ├── types/
│   │   └── race.ts             # TypeScript interfaces (Rider, Pack, ProfilePoint, etc.)
│   ├── utils/
│   │   ├── parseRaceLog.ts     # Parses JSONL + computes elevation profile
│   │   ├── interpolateRider.ts # Maps rider.pos to (x,y) on profile
│   │   ├── computePacks.ts     # BFS pack cohesion mirroring race_engine logic
│   │   ├── gradientColors.ts   # Maps gradient % to color pairs
│   │   ├── teamColors.ts       # 12-colour team palette, teamColor()/teamCode()/isLeader() helpers
│   │   ├── raceResults.ts      # Winner finish time + gap-to-winner per rider, group-finish detection
│   │   ├── formatTime.ts       # formatGapTime (+3m 14s) / formatFinishTime (hh:mm:ss)
│   │   └── useProfileScale.ts  # Linear SVG scale with fixed margins
│   ├── App.tsx                 # Sidebar + dynamic file fetch (the only glue point)
│   └── main.tsx
├── scripts/
│   └── serve_viewer.py         # CLI tool: serves player + all .jsonl in public/ + /api/races
├── package.json
├── vite.config.ts              # Plugins: React, Tailwind, race-file-listing dev endpoint
└── tsconfig.json
```

### Component Hierarchy
```
App.tsx
├── FileExplorer (standalone, no knowledge of player)
└── main
    └── RaceViz
        ├── PlaybackControls
        ├── ElevationProfile
        │   ├── RiderMarker (memoized SVG marker, packs of 1-2)
        │   └── PackMarker (memoized SVG blob, packs of 3+)
        └── RiderList
            └── Pack groups + gap dividers
```

### Data Flow
```
App.tsx
 ├─ fetch(`/api/races`)              → FileExplorer renders sidebar list
 ├─ fetch(`/${selectedFile}`)        → parseRaceLog() → ParsedRace
 ├─ <FileExplorer onSelect={setSelectedFile} />
 └─ <RaceViz raceData={parsedRace} />
      ├─ computePacks(riders, profile)  → Pack[] → RiderList AND ElevationProfile
      │                                   (single computation, shared — not recomputed per view)
      ├─ ElevationProfile (custom SVG, consumes Pack[])
      └─ PlaybackControls (keyboard + buttons)
```

## Integration Strategy

### Current (Standalone)
- Serve via `vite dev` (HMR + `/api/races` middleware) or `serve_viewer.py` (static build + `/api/races` handler).
- Fetch any `.jsonl` from `public/` via the file explorer sidebar.

### Future (Django Integration)
- **Method A (iframe):** Embed the built React app in a Django template.
- **Method B (NPM):** Extract the visualizer as an npm package and import it into the main Django+React frontend.
- **Method C (Web Component):** Build the React app as a Web Component for direct embedding.

The primary integration point is the `RaceViz` component, which accepts a `raceData: ParsedRace` prop. Switching from local file to API data only requires modifying the data fetching logic in `App.tsx`.

## Development Guidelines

1. **Modularity:** Keep components decoupled. Data flows down from `App.tsx`.
2. **Performance:** Use `React.memo` for expensive renders (e.g. `RiderMarker`).
3. **Type Safety:** Define all data structures in `types/race.ts` and use them throughout.
4. **Styling:** Tailwind for layout; antd for complex UI elements.
5. **KNOWN ISSUE:** Antd v6 `Slider` has a bug: its `Portal` component has a `useEffect` with no dependency array that causes "Maximum update depth exceeded" when dragging. Do **not** re-add the Slider until antd is patched/upgraded. The playback seek control uses a plain native `<input type="range">` instead — see `PlaybackControls.tsx`.
