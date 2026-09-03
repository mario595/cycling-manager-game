# Race Player / Visualizer

A standalone React-based web application for visualizing race simulations produced by `race_engine`.

## Project Goals

- **Primary:** Provide a sophisticated, interactive visualization of race logs (`race.jsonl`).
- **Design:** Mimic professional cycling visualizers like Strava or VeloViewer (elevation profile + rider markers).
- **Integration:** Must be modular and portable enough to integrate into the future Django-based game web app.

## Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| **Build Tool** | Vite | Fast HMR, excellent React support. |
| **UI Library** | React 18+ | Functional components and hooks. |
| **Language** | TypeScript | Strict typing for race data and props. |
| **Styling** | Tailwind CSS | Utility-first CSS for rapid UI development. |
| **Charts** | Recharts | For the elevation profile (Area/Line charts). |
| **UI Components** | Ant Design (antd) | Lightweight UI kit (Slider, Table, Tooltip). |

## Data Source & Format

### Input
- **File:** `race.jsonl` (produced by `race_engine`).
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
- **Type:** Area chart rendered via Recharts.
- **Coloring:** Gradient-colored area based on the slope (e.g., green for flat, red for steep climbs).
- **Rider Markers:** Custom SVG markers rendered on the profile line using Recharts' `customized` layer.
- **Interactivity:** Hovering over a rider marker shows detailed stats (speed, energy, etc.).

### 2. Playback Controls
- **Start/Pause:** Toggle button to start/stop the simulation.
- **Slider:** `<Slider>` component to scrub through the race timeline (0 to max ticks).
- **Speed Selector:** Options for `x1` (1 tick/sec), `x2`, `x5`, and `x10` playback speeds.
- **Logic:** Use `useEffect` with `setInterval` or `requestAnimationFrame` to advance ticks based on selected speed.

### 3. Rider Leaderboard
- **Sorted List:** A table below the profile showing riders sorted by distance (descending).
- **Columns:** Rank, Name, Meters, Speed, Energy/Stamina bars.
- **Leader Highlight:** Visual distinction for the current race leader (highest `pos`).

## Architecture

### File Structure
```
race-player/
├── public/
│   └── race.jsonl          # Static file for local development
├── src/
│   ├── components/
│   │   ├── RaceViz.tsx          # Main container
│   │   ├── ElevationProfile.tsx # Gradient area chart
│   │   ├── RiderMarker.tsx      # Custom SVG marker
│   │   ├── PlaybackControls.tsx # Slider, Play/Pause, Speed
│   │   └── RiderList.tsx        # Sorted table of riders
│   ├── types/
│   │   └── race.ts              # TypeScript interfaces
│   ├── utils/
│   │   ├── parseRaceLog.ts      # Parses JSONL + computes elevation
│   │   └── interpolateRider.ts  # Maps rider.pos to (x,y) on profile
│   ├── App.tsx
│   └── main.tsx
├── scripts/
│   └── serve_viewer.py          # CLI tool to serve the player + JSONL
├── package.json
├── vite.config.ts
└── tsconfig.json
```

### Component Hierarchy
```
App.tsx
└── RaceViz
    ├── PlaybackControls
    ├── ElevationProfile
    │   └── RiderMarker (Customized Recharts component)
    └── RiderList
```

## Integration Strategy

### Current (Standalone)
- Serve via `vite dev` or a custom Python script (`serve_viewer.py`).
- Fetch `race.jsonl` from the public folder or a local server.

### Future (Django Integration)
- **Method A (iframe):** Embed the built React app in a Django template.
- **Method B (NPM):** Extract the visualizer as an npm package and import it into the main Django+React frontend.
- **Method C (Web Component):** Build the React app as a Web Component for direct embedding.

The primary integration point will be the `RaceViz` component, which accepts a `raceData: RaceSnapshot[]` prop. Switching from local file to API data will only require modifying the data fetching logic in `App.tsx`.

## Development Guidelines

1. **Modularity:** Keep components decoupled. Data should flow down from `App.tsx`.
2. **Performance:** Use `React.memo` for expensive renders (like the profile chart) and virtualization for the rider list if the count is high.
3. **Type Safety:** Define all data structures in `types/race.ts` and use them throughout the app.
4. **Styling:** Use Tailwind for layout and custom styles. Use Ant Design components for complex UI elements (tables, sliders).
