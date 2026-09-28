# Watch a finished race — Implementation Plan

**Spec:** `specs/archive/watch-finished-race.md` · **Issue:** #94 · **Status:** implemented
**Apps touched:** `api/`, `race_player/`, `frontend/`, `.github/workflows/ci.yml`
(no model changes, no migrations)

## Context you need

**What exists.**

- **Race logs.** Every simulated race stores its log as a brotli-compressed
  `.jsonl.br` file.
  - The file goes through Django storage (`racing.models.RaceLog.file`,
    `upload_to="race_logs/"`, one `RaceLog` per race, `related_name="log"`).
  - The format is one header line, then sampled ticks. See `racing/README.md`,
    *Race logs*, and `race_player/README.md`, *Data Source & Format*.
  - A mountain stage is about 0.75 MB compressed.
  - **Nothing serves a log over HTTP today.**
- **`race_player/`** is a standalone Vite app (React 19, **Tailwind + antd**)
  that plays those logs.
  - `RaceViz.tsx` holds the playback loop and keyboard handling, and composes
    `PlaybackControls` (antd), `ElevationProfile` (plain SVG) and `RiderList`
    (Tailwind + antd icons).
  - The data layer is pure TypeScript: `parseRaceLog`, `computePacks`,
    `computeRaceResults` and `formatTime`.
- **`frontend/`** is the game's SPA. Its styles are **inline `style={{}}`
  from `src/theme.ts`**, with no CSS framework (`frontend/README.md`,
  *Conventions*).
  - It already imports race_player source directly:
    `components/CourseProfile.tsx` imports `CourseChart` and `computeProfile`
    from `../../../race_player/src/`.
  - `vite.config.ts` dedupes `react`/`react-dom`, so those files use the
    SPA's React.
  - CI runs `npm ci` in `race_player/` so `tsc` can resolve those imports.
    CI runs **frontend** tests only. **race_player's own vitest tests are not
    run in CI today.**
- **`/race/:raceId`** (`screens/Race.tsx`) shows a finished race's course
  profile and then three results cards straight away: `RiderResultsTable`,
  `TeamPointsTable` and `MarkerResultsCard`.
  - The results come from `useRaceResults(id, enabled)`, which fetches
    `GET /api/racing/races/<id>/results/`.
  - The race's own facts come from `useRaceDetail`
    (`GET /api/racing/races/<id>/`, `RaceDetailView` in `api/views.py`).

**Log facts this plan relies on (verified in `race_engine/race_logger.py`,
`racing/adapters.py`):**

- Header riders carry `team` as the **stringified team pk** (`"7"`), or
  `null`.
  - This is the team the rider **raced for** (from the squad).
  - The SPA knows its own team as the number `me.team.id` (`useAuth()`).
- Flag bit `8` means the rider was cut by the time limit (DNF). It is
  mutually exclusive with finished (`4`).
  - `parseRaceLog` currently ignores bit 8, so a cut rider freezes on the
    road.
  - Worse, `computePacks` still clusters them with any group riding past
    them.
- Course markers (#70) are **not** in the log. `racing/README.md` D2 says so,
  and no change is needed here.

**Rules this work is bound by:**

- `race_engine/` is untouched.
- `api/` may import `racing.models`. It already does.
- Logs are authoritative records. Serve the stored bytes and never
  regenerate them.
- Dependency direction between packages stays **`frontend` → `race_player`,
  never the reverse**. race_player must not import `frontend/src/theme.ts`.

## Goal

1. `GET /api/racing/races/<id>/log/` serves a finished race's stored log to
   any logged-in user. It sends the brotli bytes with
   `Content-Encoding: br` when the client accepts it, and decompresses on
   the server otherwise.
2. The race detail payload carries `has_replay`. A finished race's screen
   shows a **Watch race** button, or a "no replay" note when there is no
   log.
3. On the race screen, all results (rider results, team points, sprints and
   summits) are **hidden until a Show results button is pressed**. The same
   control appears on the replay screen.
4. `/race/:raceId/replay` plays the race in the game's own visual style.
   - The player's team's riders are highlighted.
   - Time-cut riders are shown as out of the race.
   - A missing or unreadable log produces a clear message.

## Design decisions (settled — implement these, do not substitute)

**D1 — The SPA imports race_player's logic and SVG; the SPA owns the
chrome.**
- **Imported from race_player** (all framework-free):
  - `parseRaceLog`, `computePacks`, `computeRaceResults`, `formatTime`
  - `ElevationProfile`, `RiderMarker`, `PackMarker` (plain SVG)
  - `WindCompass`, after W3 converts it to inline styles
  - two new pure helpers and one new hook (below)
- **Built fresh in `frontend/` from `primitives.tsx` + `theme.ts`:**
  - the playback controls
  - the rider list
- *Not* an iframe: it would need a second build and a second auth path.
- *Not* importing `RaceViz`/`PlaybackControls`/`RiderList`: they are antd +
  Tailwind. Tailwind classes are no-ops in the SPA, so they would render
  unstyled, and antd would add a UI kit the game does not use. The spec
  requires the game's look (*Decisions taken*).
- *Not* restyling race_player's own components in place: race_player cannot
  import the game's theme (package direction), so it would need a copied set
  of tokens that would drift.
- The standalone viewer keeps its antd/Tailwind chrome as a developer tool.

**D2 — Everything that is behaviour, not presentation, is shared, so there
is exactly one copy.** These move into race_player and both hosts consume
them:
- `usePlayback` — tick state, the play timer, speed, seek, step and the
  keyboard.
- `packGaps` — the gap between adjacent packs, extracted from `RiderList`.
- `resultLabel` — the per-row Result text, extracted from `RiderList`'s
  `ResultCell`.

Do not copy these into `frontend/`. Two playback loops will disagree about
the end-of-race and keyboard edge cases within a month.

**D3 — Serve the log through a DRF view that streams from storage. No
redirect, no public media URL.**
- 0.75 MB through the app server is fine at this scale.
- `IsAuthenticated` (the project default) is enforced for free.
- The storage API stays the only way the file is touched.
- When logs move to R2 (`racing/README.md`), this view becomes a redirect to
  a signed URL. That is a later change to one view.
- *Do not* link `/media/race_logs/...`. It is only served under `DEBUG`, it
  bypasses auth, and it does not send `Content-Encoding`.

**D4 — `Content-Encoding: br` only when the request's `Accept-Encoding`
lists `br`. Otherwise decompress on the server with `brotli` (already in
`requirements.txt`).**
- Browsers only advertise `br` on secure contexts. Production is HTTPS, but
  a plain-HTTP deploy or an odd client must still get readable text.
- Always set `Vary: Accept-Encoding`.
- **Load-bearing:** pass `content_type="application/x-ndjson"` explicitly to
  `FileResponse`. Without it, Django guesses from the `.br` filename and
  labels the body `application/x-brotli`.

**D5 — `has_replay` in the race detail payload is "a `RaceLog` row with a
non-empty `file` exists".**
- It does **not** stat the file. On R2 that would be a network round trip
  per detail view.
- A row whose file has gone missing surfaces on the replay screen as "This
  race's replay couldn't be loaded". That is the same message as a log the
  parser rejects, which covers spec item 9's "unreadable".

**D6 — Results are fetched lazily, only on reveal.**
- A new `HiddenResults` component owns a `revealed` boolean and calls the
  existing `useRaceResults(race.id, revealed)`.
- The existing `enabled` gate means nothing is fetched until the player
  clicks, so the network tab does not spoil the result either.
- `revealed` is plain component state, so every mount starts hidden, as the
  spec requires ("per-visit"). Race screen and replay screen each own their
  own. Revealing on one does not carry to the other, which is
  deliberate and matches the spec.
- *Do not* persist it in `localStorage`. That is the spec's **Later** item.

**D7 — "Your team" is `String(me.team.id) === headerRider.team`.**
- This is the team the rider **raced for**, as the spec now states. It was
  corrected while planning.
- No roster fetch is needed.
- **Load-bearing:** the header id is a string and `me.team.id` is a number.
  Compare with `String(...)`, or nothing is ever highlighted and no type
  error warns you (`team: string | null` vs `number`).
- A player with no team, or whose team did not race, gets
  `highlightTeam = null`. There is no highlight and no error.

**D8 — A time-cut rider leaves the road.**
- `parseRaceLog` exposes `dnf: boolean` (bit 8).
- Every host splits a snapshot's riders into **racing** (`!dnf`) and
  **out** (`dnf`).
- **Only racing riders go into `computePacks`.** This fixes the frozen-rider
  and phantom-pack-member bug, and it also removes them from the profile.
- The game's rider list shows the out riders in an **"Out of the race"**
  block under the last pack: no rank, km frozen where they were cut, speed
  `—`, Result `DNF`, no stamina or energy bars.
- *Not* a hollow marker on the profile: under the broom wagon a large share
  of the field can be cut, and a trail of ghost markers would bury the live
  race.
- The standalone viewer gets the same filtering (they vanish from its list
  as well). That is acceptable for a dev tool.

**D9 — Own-team highlight rendering.**
- **In the list:** the row background is `color.accentWash`, the same "your
  team" tint `League.tsx` uses. The row also carries
  `data-own-team="true"` so tests can assert it.
- **On the profile:**
  - `RiderMarker` takes `highlighted?: boolean` and draws an extra ring of
    `highlightColor` (radius `+3.5`, stroke width 2) outside the white
    stroke.
  - `PackMarker` takes `highlightCount?: number`. When it is > 0 it draws
    the same outer ring, and the pack tooltip adds a line: `Your riders: N`.
- `ElevationProfile` takes `highlightTeam?: string | null` and
  `highlightColor?: string` (default `'#0f172a'`), and computes both marker
  props.
- The SPA passes `color.ink`. A dark ring is distinguishable from all twelve
  palette hues. The accent orange is not (palette #2 is orange).
- Team colours stay the race_player palette, per the spec's Out of scope.

**D10 — `usePlayback` keyboard handling ignores events aimed at interactive
elements.**
- If `event.target` is an `INPUT`, `TEXTAREA`, `SELECT` or `BUTTON`, or is
  `isContentEditable`, do nothing.
- Otherwise:
  - Space toggles play/pause, and `preventDefault` stops the page
    scrolling.
  - `←`/`→` step.
- Without the guard:
  - Space on a focused Play button toggles twice (the native click plus
    the handler), so nothing happens.
  - `→` on the focused seek slider steps twice.

  The standalone viewer has both bugs today. The SPA page is full of
  focusable controls, so they would be hit constantly.

**D11 — Default speed in the game is ×10; the standalone stays ×1.**
- A 5-hour stage at ×1 is 5 hours.
- `usePlayback(maxTicks, tickInterval, { initialSpeed })` takes the default
  from the host.
- The speed options are unchanged: ×1, ×2, ×5, ×10, ×25, ×50.

**D12 — The replay is its own route, `/race/:raceId/replay`, inside
`Layout`.**
- It keeps the sidebar and passes through the session guards like every
  other screen.
- It is registered as an explicit `<Route>` next to `/race/:raceId`, for
  the same reason (it is parameterised).
- `navigation.ts` gains `racePath(id)` and `replayPath(id)`. Nothing builds
  these strings by hand, following the `riderPath` rule.

## API

### `api/serializers.py`

`RaceDetailSerializer` gains `has_replay = serializers.BooleanField()`.

### `api/views.py`

- In `RaceDetailView.get`, add the following to the payload:
  `"has_replay": RaceLog.objects.filter(race=race).exclude(file="").exists()`.
- Import `RaceLog` alongside the existing `racing.models` import.

**New `RaceLogView(APIView)`**, `IsAuthenticated` by default:

```python
def get(self, request, race_id: int):
    race = get_object_or_404(Race, pk=race_id)
    if race.status != Race.Status.FINISHED:
        raise Http404("race has not finished")
    log = RaceLog.objects.filter(race=race).exclude(file="").first()
    if log is None:
        raise Http404("race has no log")
    try:
        fh = log.file.open("rb")
    except FileNotFoundError:
        raise Http404("log file missing")

    if _accepts_brotli(request.META.get("HTTP_ACCEPT_ENCODING", "")):
        # content_type explicit: FileResponse would otherwise call a .br
        # file application/x-brotli (D4).
        response = FileResponse(fh, content_type="application/x-ndjson")
        response["Content-Encoding"] = "br"
    else:
        with fh:
            body = brotli.decompress(fh.read())
        response = HttpResponse(body, content_type="application/x-ndjson")
    response["Vary"] = "Accept-Encoding"
    response["Cache-Control"] = "private, max-age=86400"
    return response
```

- `_accepts_brotli(header)` is a module-level helper:
  - split on `,`
  - take each token before `;` and strip it
  - return true if any token is `br` and does not carry `q=0`

  Plain string parsing is enough; no library is needed.
- The log is immutable once written, so `Cache-Control: private` with a day
  is safe. `private` stops shared caches holding an authenticated response.
- A DRF `APIView` may return a plain Django `HttpResponse`/`FileResponse`,
  since DRF passes `HttpResponseBase` through. The fetch's `Accept: */*`
  passes DRF content negotiation.

### `api/urls.py`

- Add
  `path("racing/races/<int:race_id>/log/", RaceLogView.as_view(), name="race-log")`
  **above** the `racing/races/<int:race_id>/` entry, grouped with
  `results/`.

## race_player

### `race_player/src/types/race.ts`

`Rider` gains `dnf: boolean`.

### `race_player/src/utils/parseRaceLog.ts`

- Add `FLAG_DNF = 8`.
- `decodeRider` sets `dnf: (flags & FLAG_DNF) !== 0`.

### `race_player/src/utils/packGaps.ts` (new)

```ts
export interface PackGap { seconds: number; meters: number }
/** Gap from each pack to the one ahead; null for the leading pack. */
export function packGaps(packs: Pack[]): (PackGap | null)[]
```

This is the body of the `useMemo` in `RiderList.tsx`, lines 130–145 today:
`gapM = max(0, prevBack - cur.frontPos)`, and
`gapT = cur.speed > 0 ? gapM / cur.speed : 0`. Formatting stays with the
caller.

### `race_player/src/utils/raceResults.ts`

Add:

```ts
/** The Result cell for one rider at the displayed tick: '—' while racing,
 * hh:mm:ss for the winner, '+0' / '+3m 14s' (formatGapTime) for the rest. */
export function resultLabel(rider: Rider, result: RiderResult | undefined): string
```

This is `ResultCell`'s logic returning a string. It keeps the gate on the
**live** `rider.finished` flag; see the comment in `RiderList.tsx` for why.

### `race_player/src/utils/usePlayback.ts` (new)

```ts
export interface Playback {
  tick: number
  playing: boolean
  speed: number
  setSpeed: (speed: number) => void
  togglePlay: () => void      // at maxTicks, rewinds to 0 then plays
  seek: (tick: number) => void // clamped to [0, maxTicks]
  step: (dir: -1 | 1) => void
}
export const PLAYBACK_SPEEDS = [1, 2, 5, 10, 25, 50] as const
export function usePlayback(
  maxTicks: number,
  tickInterval: number,
  options?: { initialSpeed?: number },
): Playback
```

- Lift the body from `RaceViz.tsx`, lines 15–83: the interval loop, the
  ref-stable key listener, and the handlers.
- Add D10's guard at the top of the key listener:

```ts
const t = e.target as HTMLElement | null
if (t && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(t.tagName))) return
```

### `race_player/src/components/RaceViz.tsx`

- Use `usePlayback(maxTicks, tickInterval)`.
- Pass `riders.filter(r => !r.dnf)` to `computePacks` (D8).
- The rendered output is otherwise unchanged.

### `race_player/src/components/PlaybackControls.tsx`

- Build the speed options from `PLAYBACK_SPEEDS`.
- Nothing else changes.

### `race_player/src/components/RiderList.tsx`

- Use `packGaps` (keep the `+${formatGapTime(s)} (${m}m)` text).
- Replace `ResultCell` with `resultLabel`.
- The look is unchanged.

### `race_player/src/components/WindCompass.tsx`

- Replace its three Tailwind `className`s with equivalent inline `style`s.
- The text colours stay as literals: `#334155` for the value and `#94a3b8`
  for the band label.
- It then renders identically in both hosts. It has no antd.

### `race_player/src/components/ElevationProfile.tsx`, `RiderMarker.tsx`, `PackMarker.tsx`

- Add D9's props.
- `PackTooltip` gets a `Your riders: N` line when N > 0.
- Everything is optional, so the standalone viewer, which passes nothing,
  is visually unchanged.

## frontend

### `frontend/src/api.ts`

- `RaceDetail` gains `has_replay: boolean`.
- Add:

```ts
export async function getRaceLog(raceId: number): Promise<string>
// fetch(`/api/racing/races/${raceId}/log/`); !ok -> throw; return response.text()
```

The browser decodes `br` transparently. Vite's dev proxy passes the header
through untouched.

### `frontend/src/useRaceLog.ts` (new)

```ts
export function useRaceLog(raceId: number, enabled: boolean):
  { race: ParsedRace | null; loading: boolean; error: boolean }
```

- It mirrors `useRaceResults`: gated, a cancel flag, and no polling.
- It calls `parseRaceLog(text)` inside the same `.then`. A thrown parse
  error (a bad header, an unsupported `v`) sets `error`, exactly like a 404.

### `frontend/src/navigation.ts`

- Add `racePath(id)` → `/race/${id}` and `replayPath(id)` →
  `/race/${id}/replay`.
- Switch the three existing hand-built race links to `racePath`:
  `Dashboard.tsx:94`, `Calendar.tsx:229` and `RiderProfile.tsx:140`.
  `Dashboard.test.tsx:156`'s `href` assertion stays valid.
- `titleForPath`:
  - `'/race/…/replay'` → `'Replay'`
  - other `'/race/…'` → `'Race'`

  Today both fall through to `'Dashboard'`.

### `frontend/src/components/RaceResults.tsx` (new)

- **Move**, unchanged, `RiderResultsTable`, `TeamPointsTable` and
  `MarkerResultsCard` out of `screens/Race.tsx`.
- Add:

```tsx
export function HiddenResults({ race }: { race: RaceDetail })
```

- It renders a `Card` with `CardHeader title="Results"` and an action
  `Button variant="secondary"` that reads "Show results" / "Hide results".
- When revealed it calls `useRaceResults(race.id, revealed)`. While loading
  it shows nothing. On error it shows the existing "Couldn't load this
  race's results." text. Once loaded it shows the three cards, with the
  markers card only when there are markers, as today.

### `frontend/src/screens/Race.tsx`

The finished branch becomes:

1. `CourseProfile`.
2. A `Card` holding either:
   - `Button` "Watch race", which does `navigate(replayPath(race.id))`,
     when `race.has_replay`; or
   - muted text "No replay is available for this race."
3. `<HiddenResults race={race} />`.

Other changes:
- The screen-level `useRaceResults` call goes away; `HiddenResults` owns it
  now.
- Other statuses are unchanged.

### `frontend/src/components/replay/ReplayControls.tsx` (new)

- It takes a `Playback` plus `tickInterval`, `maxTicks` and
  `wind?: Wind`.
- Layout: one `Card`, with a row holding:
  - step-back, Play/Pause and step-forward: `Button`s, with Play/Pause as
    `primary` and the steps as `secondary`, using text glyphs `◀◀ ▶/❚❚ ▶▶`
    and `aria-label`s `Step back`/`Play`/`Pause`/`Step forward`
  - a speed selector built from `Chip`s, one per `PLAYBACK_SPEEDS` value,
    labelled `×N`, active when equal
  - on the right: elapsed `formatDuration(tick*tickInterval) / total` in
    `font.mono`, then `<WindCompass wind={wind} />`
- Below the row: a native `<input type="range" aria-label="Seek">` with
  `accentColor: color.ink`.
- The debug `tick x / y` line is **dropped**, per the spec scoping.
- `formatDuration` is already exported from race_player's
  `PlaybackControls.tsx`. Importing it would pull antd in, so **move it to
  `race_player/src/utils/formatTime.ts`** and re-import it in
  `PlaybackControls.tsx`.

### `frontend/src/components/replay/ReplayRiderList.tsx` (new)

- Props:
  - `packs`
  - `out: Rider[]`
  - `teamCodes`
  - `teamNames`
  - `results: Map<string, RiderResult>`
  - `highlightTeam: string | null`
- One `Card`, rows built from flex `div`s the way `Race.tsx`'s tables are.
  No `<table>`, to match the game.
- Columns, in order:
  - rank (mono)
  - team code, in `teamColor()` with a `title` of the team name
  - rider name, followed by `★` in `color.accent` when leader, and small
    mono tags `PULL`/`ATK` when pulling/surging
  - km
  - speed (`✓` when finished)
  - `resultLabel`
  - stamina and energy as two `Bar`s from `primitives.tsx`, in the same
    colours `RiderList` uses: stamina changes colour at 60/30, energy is
    `color.negative`
- A 3px left border in `teamColor(rider.team)`.
- Between packs, a divider row that reads `+3m 14s · 123 m`, from
  `packGaps` + `formatGapTime`.
- After the last pack, if `out.length`, a `CardHeader`-style divider
  "Out of the race" followed by the out rows, per D8.
- Own-team rows follow D9.
- A footer legend with `★ leader · PULL on the front · ATK attacking`.
- **No emojis.** The game does not use them. `👑 ✅ 🥇` from the standalone
  are replaced as described above.
- No surge animation. That needs a keyframe in CSS, and the `ATK` tag
  already carries the signal.

### `frontend/src/screens/Replay.tsx` (new)

- It uses `useParams` → `id`.
- It calls:
  - `useRaceDetail(id)`
  - `useRaceLog(id, race?.status === 'finished' && race.has_replay === true)`
  - `useAuth()`
- The states, in order:

| State | Renders |
|---|---|
| detail loading | `null` |
| detail error | `MessageCard` "Couldn't load this race." |
| `status !== 'finished'` | "This race hasn't finished yet." |
| `!has_replay` | "No replay is available for this race." |
| log loading | "Loading replay…" |
| log error | "This race's replay couldn't be loaded." |
| loaded | the replay |

- Every non-loaded state carries a `Link` "← Back to race" to
  `racePath(id)`.
- The loaded replay is a `PageBody` containing:
  - a `PageHeading` with eyebrow `REPLAY`, the race name as title, and the
    back link as `aside`
  - `ReplayControls`
  - a `Card` holding `ElevationProfile`, with
    `highlightTeam={me?.team ? String(me.team.id) : null}` and
    `highlightColor={color.ink}`
  - `ReplayRiderList`
  - `<HiddenResults race={race} />`
- Derivation inside the loaded view is `useMemo`'d, as `RaceViz` does it:
  - `snapshot = parsed.snapshots[playback.tick]`
  - `racing`/`out` split
  - `packs = computePacks(racing, parsed.profile)`
  - `results = computeRaceResults(parsed)`, keyed on `parsed`
- The loaded view is its own inner component (`ReplayView({ parsed, … })`),
  so `usePlayback` is only called once `parsed` exists. **Hooks cannot be
  conditional, and `maxTicks` must not start at a placeholder 0.**
  `initialSpeed: 10`, per D11.

### `frontend/src/App.tsx`

- Add `<Route path="/race/:raceId/replay" element={<Replay />} />` next to
  `/race/:raceId`, with the same comment style.

### `.github/workflows/ci.yml`

- In the `fast` job, after race_player's `npm ci`, add
  `- run: npm run test` with `working-directory: race_player`.
- The shared logic this plan adds must be covered where it lives.

## Work items

Each item leaves `pytest`, `npm --prefix frontend test`, `npm --prefix
frontend run build` and `npm --prefix race_player test` green.

### W1 — `api/`: serve the log, expose `has_replay`

- Make the serializer, view, URL and `_accepts_brotli` changes above.
- Tests go in `api/tests.py`. Use pytest-django's `settings` fixture with
  `settings.MEDIA_ROOT = tmp_path`, and build a `RaceLog` with
  `ContentFile(brotli.compress(b'{"v":1}\n'), name="r.jsonl.br")` on a
  `FINISHED` race.
  - `test_race_log_served_brotli_when_accepted`:
    - `HTTP_ACCEPT_ENCODING="gzip, br"`
    - `Content-Encoding == "br"`
    - `b"".join(response.streaming_content)` equals the stored bytes
    - `Content-Type` starts with `application/x-ndjson`
    - `Vary` contains `Accept-Encoding`
  - `test_race_log_decompressed_when_br_not_accepted`: `gzip` only; no
    `Content-Encoding`; the body is the plain text.
  - `test_race_log_br_with_q_zero_is_not_accepted`.
  - `test_race_log_404_for_unfinished_race`, `…_404_without_log`,
    `…_404_when_file_missing` (delete the file from `tmp_path` after
    creating the row).
  - `test_race_log_requires_login` → 403, matching
    `test_race_detail_requires_login`.
  - `test_race_detail_has_replay_false_without_log` and `…_true_with_log`.
- **Load-bearing:** the explicit `content_type` (D4). The Content-Type
  assertion is what catches its absence.

### W2 — `race_player/`: DNF flag and the extracted helpers

- Add `dnf` in `types/race.ts` and `parseRaceLog.ts`.
- Add `packGaps.ts`, `resultLabel`, and move `formatDuration` into
  `formatTime.ts`.
- `RiderList`/`PlaybackControls` consume them, with no visual change.
- `RaceViz` filters DNF from `computePacks`.
- Tests (race_player vitest, node environment):
  - `parseRaceLog.test.ts` → `decodes the dnf flag (bit 8)`: flags `8` →
    `dnf: true, finished: false`; flags `4` → `dnf: false`
  - new `packGaps.test.ts` → a leading `null`, the metres/seconds maths,
    and zero speed → 0 s
  - new `raceResults.test.ts` → `resultLabel` for a still-racing rider
    (`—`), the winner (`hh:mm:ss`), a `+0` group finisher, a gapped rider,
    and a rider whose result exists but who is not yet `finished` at this
    tick (`—`)
- **Before starting,** run `npm --prefix race_player test` on master to
  confirm the existing race_player tests pass. CI has never run them.

### W3 — `race_player/`: `usePlayback`, WindCompass inline styles, highlight props

- Add `usePlayback.ts`; `RaceViz` uses it.
- Convert `WindCompass` to inline styles.
- Add D9's props on `ElevationProfile`/`RiderMarker`/`PackMarker`, plus the
  tooltip line.
- Tests live in **`frontend/src/usePlayback.test.ts`**, because race_player
  has no jsdom or testing-library. Import it from
  `../../race_player/src/utils/usePlayback`, the same way `CourseProfile`
  tests cross the boundary. Use `renderHook` + `vi.useFakeTimers()`:
  - `advances one tick per tickInterval/speed while playing`
  - `stops at maxTicks and toggling at the end restarts from 0`
  - `seek clamps to [0, maxTicks]`
  - `space on a focused button does not toggle`: dispatch a `keydown`
    with `target` a `<button>` appended to `document.body`
  - `arrow keys step when focus is on the page body`
- Also add `frontend/src/components/replay/Highlight.test.tsx`. Render
  `ElevationProfile` with two single riders, one on `highlightTeam`, and
  assert there is exactly one circle with `stroke` equal to the highlight
  colour.

### W4 — `.github/workflows/ci.yml`: run race_player's tests

- Add the one step above.
- This proves itself on the PR's own CI run.

### W5 — `frontend/`: `getRaceLog`, `useRaceLog`, navigation helpers

- Tests:
  - `useRaceLog.test.ts`, mocking `./api` as `useRaceResults.test.ts`
    does:
    - disabled → no fetch
    - resolves text → `race.maxTicks` matches the fixture
    - `getRaceLog` rejects → `error`
    - the text has an unsupported `v` → `error`, not a thrown render
  - `navigation.test.ts`: `racePath`, `replayPath`, and `titleForPath` for
    both new cases

### W6 — `frontend/`: hidden results and Watch race on the race screen

- Create `components/RaceResults.tsx` (a pure move plus `HiddenResults`).
- Make the `Race.tsx` finished-branch changes.
- `has_replay` goes into the test fixtures.
- Tests in `screens/Race.test.tsx`. Update the existing finished-race
  tests, which currently expect the tables on first render, so they click
  "Show results" first. Add:
  - `finished race hides results until Show results is clicked`: no
    "Winner Rider" text before the click; `useRaceResults` last called with
    `enabled=false`; present after the click
  - `Hide results hides them again`
  - `shows Watch race when a replay exists`
  - `shows the no-replay note when has_replay is false`

### W7 — `frontend/`: the replay screen

- Add `ReplayControls`, `ReplayRiderList` and `screens/Replay.tsx`, plus the
  route.
- Tests in `screens/Replay.test.tsx`. Mock `useRaceDetail`, `useRaceLog`,
  `useRaceResults` and `useAuth`. Build `ParsedRace` from a small JSONL
  fixture through the real `parseRaceLog`. Cover:
  - each of the six non-loaded states renders its message and the back
    link
  - `highlights riders who raced for the player's team`:
    - fixture header teams `"7"` and `"9"`, `me.team.id = 7`
    - rows for team 7 have `data-own-team="true"`, and team 9 rows do not
    - **this is the test that catches the string/number trap in D7**
  - `no highlight when the player has no team`
  - `a time-cut rider is listed under Out of the race with DNF`: a fixture
    sample with flags `8`
  - `results stay hidden until Show results`
  - `Play button toggles to Pause`: a click on the `Play` label
- `ReplayRiderList.test.tsx`:
  - the pack-gap divider text for a two-pack fixture
  - leader `★`
  - `PULL`/`ATK` tags

### W8 — Documentation

See below. It is its own commit so the docs describe what landed.

## Execution order

1. **W1.** The backend is independent and the easiest thing to prove.
   Commit. — **done**
2. **W2.** This is pure logic with no UI change in the game yet. It must
   land before anything consumes `dnf`/`packGaps`/`resultLabel`. Commit. —
   **done**
3. **W3.** The hook and the SVG props. Standalone behaviour stays
   observably the same. Commit. — **done**
4. **W4.** Now that race_player has tests worth running. Commit. — **done**
5. **W5.** The data path into the SPA. Commit. — **done**
6. **W6.** The race-screen change is shippable on its own: the Watch button
   leads to a route added in W7, so land W6 and W7 in the same PR, as
   planned. Commit. — **done**
7. **W7.** Commit. — **done**
8. **Verification** (below), then **W8**. Commit. — **done**

W6 comes before W7 so that `HiddenResults` exists and is tested before the
replay screen reuses it.

## Documentation update (required, not optional)

- **`api/README.md`:**
  - Add a `GET /api/racing/races/<race_id>/log/` entry with D3/D4:
    streamed from storage, `br` only when accepted, otherwise
    decompressed, `Vary`, `private` caching, 404 cases, `IsAuthenticated`.
  - Add `has_replay` to the race detail entry, with D5's definition.
- **`racing/README.md`:**
  - In *Where they live* / *Compression*, replace "A future HTTP endpoint
    must serve it with `Content-Encoding: br`" with a pointer to the
    endpoint.
  - In the R2 paragraph, note that moving to R2 turns that view into a
    signed-URL redirect.
- **`race_player/README.md`:**
  - Bit `8`: replace the "#94's to do" sentence with D8's behaviour.
  - *Integration Strategy*:
    - replace the undecided A/B/C list with what was built: direct source
      import of logic + SVG, host-owned chrome (D1)
    - list exactly which modules the SPA imports
    - state that race_player modules imported by the SPA must stay free of
      antd and Tailwind
  - Mention `usePlayback` (with the D10 keyboard guard), `packGaps` and
    `resultLabel` in the file structure and Core Features.
  - Note that `WindCompass` is inline-styled so both hosts can render it.
  - Note that CI now runs race_player's tests.
- **`frontend/README.md`:**
  - Route table: add `/race/:raceId/replay`, and update the `/race/:raceId`
    row (results hidden behind Show results, Watch race).
  - In *Relationship to `design/`*, replace the "Race playback … deliberately
    not folded in" sentence with a paragraph on the replay screen. It has no
    mockup and follows the Staff composition rule.
  - Add `racePath`/`replayPath` beside the `riderPath` rule.
- **`AGENTS.md`:** update the `frontend/` table row's screen count and name
  the replay screen. Update the `race_player/` row to say it is also the
  source of the SPA's replay logic.
- **Specs:** set `Status: implemented` in both files and move both to
  `specs/archive/`, per the closing-a-ticket rule.

## Verification

- **Automated tests:**

  ```bash
  /home/mario/dev/cycling-manager/.venv/bin/python -m pytest api
  npm --prefix race_player test
  npm --prefix frontend test && npm --prefix frontend run lint && npm --prefix frontend run build
  ```

- **End to end, on the worktree's own DB and port** (see AGENTS.md,
  *Seeding a world*). Seed a world and move the mock clock past the first
  race so at least one race is `finished` with a log. Then:
  1. **The likeliest failure is a replay that loads as garbage**, either
     `Content-Encoding` missing or the wrong `Content-Type`, which makes
     `parseRaceLog` throw on line 1.
     - Check with
       `curl -s -D - -o /dev/null -H 'Accept-Encoding: br' -b 'sessionid=…' http://127.0.0.1:<port>/api/racing/races/<id>/log/`.
     - The headers must show `Content-Encoding: br`,
       `Content-Type: application/x-ndjson`, and `Vary: Accept-Encoding`.
     - Repeat without the header and pipe the body to `head -c 200`: it
       must be readable JSON.
  2. In the browser (the built SPA served by Django, *and* `vite dev` on
     the worktree's port):
     - Open the finished race. There should be no results visible, a
       Watch race button, and no request to `/results/` in the network
       tab.
     - Click Show results: the tables appear. Click Hide results: they go
       away.
  3. Click Watch race.
     - The replay loads, paused at 0:00, and the network tab shows the
       log response with `content-encoding: br`.
     - Press Play: markers move at ×10.
     - Press Space with the Play button focused: it toggles exactly once.
     - Drag the seek bar to the end: the finish order appears in the
       Result column.
  4. **Own-team highlight.** Log in as `test@mail.com`, whose team is
     claimed by `seed_teams --claim-for`. Four rows should be tinted, and
     four markers ringed or a pack ring shown. Log in as a freshly
     registered user with no team and claim a *different* team: no rows
     should be tinted.
     - This is the real check on D7's string/number comparison.
  5. **DNF.** Find a race with a time-cut rider (`RaceResult` with
     `finish_time IS NULL`). Seek past the cut: the rider leaves the
     profile and appears under "Out of the race" as `DNF`.
  6. **No replay.** Delete one race's `RaceLog` row in the shell. Its race
     screen should show the no-replay note, and `/race/<id>/replay` should
     show the same note.
     - Then restore a row but delete its file: the replay screen should
       show "couldn't be loaded".
- **Evidence to post in the PR:** the curl header output, and a screenshot
  of the replay with own-team rows highlighted.

## Risks

| Risk | Mitigation |
|---|---|
| Comparing `me.team.id` (number) to a header `team` (string): nothing is highlighted, and nothing fails. | D7 spells it out. The W7 `data-own-team` test uses real string ids from `parseRaceLog`, and Verification step 4 checks it by hand. |
| `FileResponse` labels the body `application/x-brotli` or omits `Content-Encoding`, and the browser hands raw bytes to `JSON.parse`. | D4, an explicit `content_type`, the W1 header assertions, and the Verification step 1 curl. |
| A reader copies `RaceViz`/`RiderList` into `frontend/` instead of sharing the logic, giving two playback loops. | D1/D2 name what is shared. `usePlayback`, `packGaps` and `resultLabel` are the only sources, and the reviewer checks there is no `setInterval` in `frontend/src`. |
| A race_player module the SPA imports gains an antd or Tailwind dependency later. The build still passes (race_player's node_modules are installed in CI), but it renders unstyled or bundles antd. | The `race_player/README.md` rule (W8). Check that `npm --prefix frontend run build` output has no `antd` in its chunk names. |
| Parsing a long stage's log in the browser is heavy: about 10–15 MB of text becomes one object per rider per sample. | This is the standalone player's existing cost, not new. Accepted for the MVP. If it bites, the fix is lazy per-tick decoding in `parseRaceLog`, which would be its own ticket. |
| Existing `Race.test.tsx` finished-race tests start failing because results are now hidden. | W6 updates them explicitly to click Show results. That is expected, not a regression. |
| race_player's tests have never run in CI and may already be red. | W2 runs them first, on master. If any fail, fix or report them before building on top. |
| The keyboard listener on `window` fires on other screens after navigating away. | `usePlayback` removes its listener on unmount; that is lifted as-is from `RaceViz`. Covered implicitly: the listener is in an effect with cleanup. Check this in review. |

## Open questions

None. The one product ambiguity, which riders get the own-team highlight,
was settled while planning. It is recorded in the spec's *Rules* and
*Decisions taken*.
