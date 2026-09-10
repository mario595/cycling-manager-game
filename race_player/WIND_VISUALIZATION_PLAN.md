# Wind Visualization — Race Player Implementation Plan

**Audience:** an implementing agent who has not read the wind brainstorm. This
document is self-contained: it states what to build and why, and it makes the
design decisions so you do not have to re-litigate them.

**Status:** proposed, not implemented. Awaiting approval.

---

## Context you need

The race engine writes a `.jsonl` log — one JSON object per tick (1 tick = 1
second) — which this React app plays back as an elevation profile with pack
markers plus a pack-grouped leaderboard.

A parallel piece of work ("Wind Tier A", specified in
`race_engine/WIND_PLAN.md`) adds wind to the simulation. Wind is modelled
**relative to the riders** — there is no compass bearing, no course heading.
Each tick carries one wind angle meaning "where the wind blows from, as seen by
a rider facing forward".

**That engine work may still be in progress while you implement this.** Build
against the data contract below, not against whatever the engine currently
writes.

---

## Goal

One question, answered at a glance, at any moment of playback:

> **Which way is the wind hitting the riders, and how hard?**

The agreed visual is a **wind compass**: a bike seen in perspective from
behind/above, sitting on a compass rose, with an arrow showing where the wind
blows *from*. Wind speed in km/h sits below the graphic.

The bike is the anchor of the whole design. Because the engine models wind
relative to the riders, **the bike never rotates** — it always points "forward,
away from the viewer". The *arrow* rotates around it. That is a direct visual
translation of the engine's model, and it is why this design is right rather
than merely pretty: a viewer reads "the wind is coming over my right shoulder"
without any mental transformation.

---

## Data contract

Each tick object gains one optional top-level key:

```json
{
  "time": 42,
  "course_length": 38000.0,
  "wind": {"speed": 17.3, "angle": 214.6, "band": "moderate"},
  "segments": [...],
  "riders": [...]
}
```

| Field | Meaning |
|---|---|
| `speed` | wind speed in **km/h** (already converted — do not convert again) |
| `angle` | degrees in `[0, 360)`, where the wind blows **FROM**, relative to the rider |
| `band`  | `"calm"` \| `"light"` \| `"moderate"` \| `"strong"` — constant for the race |

### The angle convention — read this twice

```
    0°  = HEADWIND      (blowing into the rider's face)
   90°  = CROSSWIND     from the rider's RIGHT
  180°  = TAILWIND      (blowing from behind, pushing)
  270°  = CROSSWIND     from the rider's LEFT
```

The arrow must point **from** the wind's origin **toward** the bike. At
`angle = 0` (headwind) the arrow sits ahead of the bike pointing back at the
viewer. At `angle = 180` (tailwind) it sits behind the bike pointing away.

Getting this backwards is the single most likely bug in this work item, and it
will look plausible. **Write the four cardinal cases as a test or a dev-only
sanity row before styling anything.**

### `wind` must be treated as OPTIONAL

The key is **absent entirely** on logs predating this feature and on races run
with wind disabled. Every `.jsonl` currently in `public/` is such a log.

- Type it as `wind?: Wind` and handle `undefined` everywhere.
- When absent, **render nothing** — no compass, no placeholder, no "no wind
  data" box. The layout must look exactly as it does today.

Mirror the precedent set by `team`/`role` in `utils/teamColors.ts`: optional
engine fields get a defaulting helper, not scattered `?.` checks.

### The `.jsonl` files in `public/` are almost certainly stale

They will not have `wind` until races are re-run against the new engine.
Regenerate with `python -m race_engine <config.json> --seed N`. Do not
"fix" the player to make old files show wind — absent means absent.

---

## Design decisions (settled — implement these, do not substitute)

### 1. The bike is fixed; the arrow rotates.

Per the Goal above. Do not rotate the bike, and do not rotate the compass rose
either — the rose's labels are rider-relative, not geographic.

**Label the rose in rider terms, not compass terms.** It reads `HEAD` at the
top, `TAIL` at the bottom, `L` and `R` at the sides. Writing N/S/E/W would be
actively wrong: there is no north in this model. This is the second-most-likely
mistake after the arrow direction.

### 2. Intensity is carried by colour AND arrow size — never by colour alone.

Map the band to a visual weight:

| Band | Colour | Arrow |
|---|---|---|
| `calm` | slate / muted | short, thin |
| `light` | sky blue | |
| `moderate` | amber | |
| `strong` | red | long, thick |

Derive the visual weight from the **live `speed`**, not the band, so the arrow
breathes as the wind drifts; use the **band** only for the label text. Two
redundant channels (colour + size) keep it readable for colour-blind viewers
and at a glance.

### 3. The compass is small and lives next to the playback controls.

Target ~96–120 px square. It is a persistent instrument, not a feature panel.
Place it in the `PlaybackControls` row (`RaceViz.tsx` line ~95), right-aligned
alongside the existing elapsed/tick readout — the natural home for
"current state of the race right now" readouts.

**It must not compete with the elevation profile for attention.** The profile
is the main event.

### 4. Smooth the rotation, but do not lie about it.

The engine already guarantees smooth drift (max ~0.15 km/h and a fraction of a
degree per tick), so at x1 playback no smoothing is needed. But at **x50** the
arrow will jump in ~10° steps.

Apply a short CSS transition on the arrow's rotation (`transition: transform
120ms linear`). **Use the shortest-arc rotation** — a naive `rotate(angle)`
will spin the long way around when the angle wraps 359° → 1°. Track a
continuously-unwrapped rotation value in a ref rather than feeding the raw
angle to CSS.

### 5. Do not build these.

Explicitly out of scope. They were considered and rejected:

- **Animated particle streaks.** Expensive, and they compete with rider markers
  for attention on the one surface that matters most.
- **Per-segment wind overlay on the elevation profile.** Wind is not a property
  of course position in this model — it is a property of *time*. Painting it
  onto the distance axis would imply a spatial relationship the engine does not
  have, and would be a genuine lie about the model.
- **A wind timeline under the seek bar.** Reasonable idea, but it needs a
  whole-race scan and more layout budget. Revisit once the compass exists.

---

## Work items

Ordered. W1–W3 are the feature; W4 is polish.

### W1 — `src/types/race.ts`

```ts
export type WindBand = 'calm' | 'light' | 'moderate' | 'strong'

export interface Wind {
  speed: number   // km/h
  angle: number   // degrees [0,360), where the wind blows FROM, rider-relative
  band: WindBand
}
```

Add `wind?: Wind` to `RaceSnapshot`. **Optional** per the data contract.

Keep the angle-convention comment in the type — it is the one place every
future reader will look.

### W2 — `src/utils/wind.ts` (new)

Pure helpers, no React. This is where the conventions live so components stay
dumb:

- `windColor(speed: number): string` — the colour ramp from decision 2.
- `windLabel(angle: number): string` — `"Headwind"`, `"Crosswind (R)"`,
  `"Tailwind"`, etc., bucketed from the angle. Used for the tooltip and for
  accessibility.
- `arrowLength(speed: number): number` — maps km/h to arrow length, clamped.
- `unwrapAngle(prev: number, next: number): number` — shortest-arc unwrapping
  per decision 4. **Unit-test this one**; it is pure math with an off-by-360
  failure mode.

### W3 — `src/components/WindCompass.tsx` (new)

Props: `{ wind: Wind | undefined }`. Returns `null` when `wind` is undefined.

Structure (inline SVG, ~110px square, matching the app's existing
custom-SVG-over-charting-library approach):

1. **Compass rose** — a circle with tick marks, labelled `HEAD` / `TAIL` /
   `L` / `R` per decision 1. Muted; it is a backdrop.
2. **Bike in perspective** — viewed from behind and slightly above: two wheel
   ellipses (rear larger/nearer), frame triangle, handlebar line. It needs to
   read as "a bike going away from you" at 110px, so favour a bold, simple
   silhouette over detail. A single dark fill, no gradients.
3. **Wind arrow** — rotates around the bike's centre per the angle convention,
   coloured and sized per decision 2. Give it a visible arrowhead; a bare line
   is directionally ambiguous at this size.
4. **Readout below** — `17.3 km/h` in tabular-nums, with the band name or
   `windLabel()` beneath it in smaller muted text.

Add a `<title>` element for accessibility, e.g.
`"Moderate crosswind from the right, 17.3 km/h"`.

Memoise with `React.memo` — it re-renders every tick, matching the
`RiderMarker` precedent in the Development Guidelines.

### W4 — `src/components/RaceViz.tsx` — mount it

Pass `snapshot.wind` down. Place per decision 3. Verify the layout does not
shift when wind is absent (old file) versus present (new file) — the
`return null` must collapse cleanly, not leave a gap.

---

## Execution order

1. W1 (types) — unblocks everything.
2. W2 (utils) + its unit test for `unwrapAngle`.
3. **Re-run one race with wind enabled** so you have a real file to build
   against. Building the compass against a file with no `wind` key means
   testing nothing.
4. W3 (component), verifying the four cardinal angles first, styling second.
5. W4 (mount).

---

## Documentation update (required, not optional)

`race_player/README.md` must be updated in the same commit:

- **Key Data Fields** — add the `wind` object, marked optional, with the angle
  convention spelled out.
- **Core Features** — a new subsection for the wind compass, describing the
  fixed-bike/rotating-arrow decision and why it follows from the engine's
  rider-relative model.
- **File Structure** — add `WindCompass.tsx` and `utils/wind.ts`.
- **Component Hierarchy** — add `WindCompass` under `RaceViz`.

---

## Verification

1. **The four cardinal angles.** Temporarily force `angle` to 0 / 90 / 180 /
   270 and confirm: arrow ahead pointing back / from the right / behind pointing
   away / from the left. Do this **before** any styling work.
2. **Wrap-around.** Force a run through 350° → 10° and confirm the arrow takes
   the short way (10° of travel, not 340°).
3. **Absent wind.** Load one of the current stale `public/*.jsonl` files;
   confirm no compass renders and the layout is byte-identical to today's.
4. **Playback at x50.** The arrow should drift smoothly, not stutter or spin.
5. **A calm race and a strong race** side by side — the difference must be
   obvious without reading the number.

---

## Risks

| Risk | Mitigation |
|---|---|
| **Arrow points the wrong way** and looks plausible | Verify the four cardinals before styling (W3/Verification 1). Highest-likelihood bug in this plan. |
| Compass rose labelled N/S/E/W, implying a geography the model does not have | Decision 1: rider-relative labels only. |
| Long-way-round spin at the 360°→0° wrap | `unwrapAngle` in W2, unit-tested. |
| Built against a stale log with no `wind` key, so nothing is actually tested | Execution order step 3: regenerate a race first. |
| Compass steals attention from the elevation profile | Decision 3: small, instrument-sized, beside the controls. |
