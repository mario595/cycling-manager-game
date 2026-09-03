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
- **Riders:** Array of rider objects containing:
  - `id`, `name`
  - `pos` (meters from start)
  - `speed` (m/s)
  - `energy`, `stamina` (0-100)
  - `drafting`, `pulling`, `surging` (booleans)
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
- **Rider Markers:** Custom SVG circle markers on the profile line with hover tooltips.
- **Interactivity:** Clicking a rider marker selects it; hovering shows stats tooltip.

### 2. Playback Controls
- **Start/Pause:** Toggle button to start/stop the simulation.
- **Keyboard:** `←` steps back, `→` steps forward, `Space` toggles play/pause.
- **Speed Selector:** Options for x1, x2, x5, x10, x25, x50 playback speeds.
- **Logic:** `useEffect` with `setInterval` advances ticks based on selected speed.

### 3. Rider Leaderboard (Packs)
- **Pack Grouping:** Riders are grouped into packs mirroring the race engine's cohesion algorithm: BFS connected components over riders within `PACK_COHESION_DISTANCE (60m)` on draft-allowed terrain (gradient ≤ 5%). A single rider is its own pack.
- **Gap Dividers:** Time gap displayed between adjacent packs (front-to-rear distance / trailing pack speed).
- **Columns:** Rank, Name, Meters, Speed, Energy/Stamina bars.
- **Leader Highlight:** Visual distinction for the current race leader (highest `pos`).

### 4. File Explorer (Sidebar)
- **Location:** `FileExplorer.tsx` — standalone dev tool, decoupled from player logic.
- **Endpoint:** `GET /api/races` returns `{ files: ["race.jsonl", ...] }` listing all `.jsonl` in `public/`.
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
│   │   ├── RiderMarker.tsx     # Custom SVG circle marker (memoized)
│   │   ├── PlaybackControls.tsx# Play/Pause, speed selector, tick counter
│   │   ├── RiderList.tsx       # Pack-grouped table with gap dividers
│   │   └── FileExplorer.tsx    # Dev sidebar: lists .jsonl, refresh, standalone
│   ├── types/
│   │   └── race.ts             # TypeScript interfaces (Rider, Pack, ProfilePoint, etc.)
│   ├── utils/
│   │   ├── parseRaceLog.ts     # Parses JSONL + computes elevation profile
│   │   ├── interpolateRider.ts # Maps rider.pos to (x,y) on profile
│   │   ├── computePacks.ts     # BFS pack cohesion mirroring race_engine logic
│   │   ├── gradientColors.ts   # Maps gradient % to color pairs
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
        │   └── RiderMarker (memoized SVG marker)
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
      ├─ computePacks(riders, profile)  → Pack[] → RiderList
      ├─ ElevationProfile (custom SVG)
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
5. **KNOWN ISSUE:** Antd v6 `Slider` has a bug: its `Portal` component has a `useEffect` with no dependency array that causes "Maximum update depth exceeded" when dragging. Do **not** re-add the Slider until antd is patched/upgraded.
