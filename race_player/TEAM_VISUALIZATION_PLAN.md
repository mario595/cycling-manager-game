# Team Visualization — Race Player Implementation Plan

**Audience:** an implementing agent who has not read the team-tactics
brainstorm. This document is self-contained: it states what to build and why,
and it makes the design decisions so you do not have to re-litigate them.

**Status:** approved, ready to implement.

---

## Context you need

The race engine simulates a bike race and writes a `.jsonl` log — one JSON
object per tick (1 tick = 1 second) — which this React app plays back as an
elevation profile with rider markers plus a pack-grouped leaderboard.

A parallel piece of work ("Tier A team tactics", specified in
`race_engine/TEAM_TACTICS_PLAN.md`) groups the previously unaffiliated riders
into **4 teams of 4 riders**. Each team has exactly one **leader**; the other
three are **support** riders who shelter the leader, do more than their share
of front work, and do not chase breaks containing their own leader.

**That engine work may still be in progress while you implement this.** Build
against the data contract below, not against whatever the engine source
currently looks like.

## Goal

Make two things readable at a glance, without hovering or clicking:

1. **Which team each rider rides for.**
2. **Which rider is their team's leader** (👑).

Everything else here serves those two. The main enemy is **crowding**: a
bunched field occupies a few dozen pixels of the elevation profile — 16
riders today, up to 48 if races reach the 12-team ceiling. Design decision 3
(pack blobs) is the structural answer to it; read that before W4/W5.

---

## Data contract

Each rider object in every `.jsonl` tick carries two fields beyond what the
player reads today:

```json
{
  "id": "gc1",
  "name": "GC Climber 1",
  "team": "t1",
  "role": "leader",
  "pos": 48213.4, "speed": 12.1, "energy": 88.0, "stamina": 71.2,
  "pulling": false, "surging": false, "finished": false, "finish_time": null
}
```

- `team` — string team id. The bundled configs use `t1`–`t4`.
- `role` — `"leader"` or `"support"`. Exactly one leader per team.

### Both fields must be treated as OPTIONAL in TypeScript

Older logs predate these fields. The player must still load and play them,
falling back to "no team, everyone a leader" — matching the engine's own
dataclass defaults. This matters because stale logs are exactly what gets
loaded when someone is bisecting an engine regression, which is when the
player most needs to work.

### The `.jsonl` files in `public/` are almost certainly stale

They are gitignored build output. Regenerate before implementing:

```bash
python -m race_engine race_engine/configs/sprinters_classic.json
```

Repeat per config as needed (`classics_hilly`, `lombardia`, `mountain_stage`,
`san_remo`, `summit_finish`). Output lands in `race_player/public/`.

**Failure mode to recognise:** if every rider renders slate-grey and every
rider looks like a leader, the logs are stale — the optional-field fallback is
silent by design. Regenerate before debugging the code.

---

## Design decisions (settled — implement these, do not substitute)

### 1. Team identity is carried by COLOUR

Colour goes on markers, list rows, and the tooltip.

**The palette must support up to 12 teams.** Races today use 4, but more are
expected. 12 is the agreed ceiling — beyond that, categorical colour stops
working as an identity channel no matter how the palette is chosen, and the
answer would be a different mechanism (numbers or glyphs), not more hues.

The palette below is validated, not eyeballed. Use it verbatim.

| # | Name | Hex | | # | Name | Hex |
|---|------|-----|---|---|------|-----|
| 1 | blue | `#1d56c9` | | 7 | cyan | `#1089c6` |
| 2 | orange | `#e26912` | | 8 | magenta | `#a630a6` |
| 3 | violet | `#9235d4` | | 9 | steel | `#3f6b8f` |
| 4 | teal | `#0e9daa` | | 10 | rust | `#bb431b` |
| 5 | pink | `#d0257a` | | 11 | periwinkle | `#7b69d3` |
| 6 | bronze | `#8a6a0a` | | 12 | moss | `#6b7f16` |

Riders with no `team` get a neutral slate (`#64748b`), which is not part of
the 12 and is never assigned to a real team.

#### Why these specific values — do not "tidy" them

- **The green band is deliberately avoided.** The elevation profile fills
  flat terrain with green; a green team marker disappears into the
  background. `moss` (#12) is the closest approach and is dark and desaturated
  enough to stay distinct.
- **Pure red is deliberately avoided.** It is already the energy-bar colour
  and reads as "cracked/danger" throughout the UI. `rust` and `pink` sit
  either side of it without being it.
- **Hues are spread and lightness alternates.** Neighbouring entries differ on
  two axes, not just hue, which is what keeps them apart when markers are
  5px wide and overlapping.
- **Verified separation:** minimum pairwise perceptual distance (CIE76 ΔE)
  across all 66 pairs is **17.7**. Below ~12 two colours read as the same;
  the closest pairs here are blue/periwinkle (17.7) and cyan/steel (19.2).
- **Verified contrast:** every colour is at least **3.27:1** against white,
  so markers hold their white stroke and list swatches stay visible.

Swapping in a "nicer" hue will silently break one of these properties. If the
palette genuinely must change, re-check both ΔE and contrast rather than
trusting the eye — several obvious-looking choices (violet vs purple, orange
vs rust, a mid olive) fail badly on one or the other.

#### First 4 teams

Entries 1–4 are the four currently in use (`t1`–`t4`). Ordering matters: the
first four are the most widely separated of the twelve, so the common case
stays maximally legible.

### 2. Leader identity is carried by SHAPE and a 👑 BADGE — never by colour

Colour is fully spent on team. The leader channel must be orthogonal.

Placement differs by view because the space budgets differ enormously:

- **Rider list and tooltip:** literal 👑 emoji. There is room; it is
  unmistakable; it matches the `✅` and medal emoji already used there.
- **Elevation profile markers:** **no emoji.** At a 5–7px marker radius a
  glyph renders as an illegible smudge and inflates SVG cost across 16
  markers on every tick. Use size + a white inner dot instead (spec below).

### 3. The profile renders PACKS, not individual riders, when riders are bunched

This is the primary answer to crowding, and it is a change to how the
elevation profile works — read this before implementing W4/W5.

**The problem.** A bunch of 40 riders inside 60m of road renders as ~40
overlapping circles at essentially one x-coordinate. No viewer can read an
individual position out of that pile. At 12 teams x 4 riders = 48 riders it is
hopeless, but it is already poor at 16.

**The insight.** Those individual markers are *lying*. Their apparent
precision is fake — the riders genuinely are all in the same place. A single
blob saying "these 40 are together, here" is a more truthful rendering of the
race state, not a lossy one.

**The rule — adaptive, by pack size:**

| Pack size | Rendering |
|-----------|-----------|
| 1–2 riders | individual markers, exactly as specified in W4 |
| 3+ riders | a single **pack blob** (spec in W5) |

Threshold as a named constant so it can be tuned without hunting.

**Why adaptive rather than always-blobs.** In the finale the race strings out
into ones and twos, and there individual markers are correct and blobs would
be strictly worse. The threshold means early bunches collapse into blobs while
the decisive finale stays granular — and the transition is itself informative:
watching a blob shatter into individual markers *is* the selection happening.

**This supersedes the vertical-jitter idea** previously held in reserve
(offsetting markers on the y-axis by team). Jitter invents y-positions that
mean nothing; blobs remove the false precision instead of decorating it.

### 4. Do not build these

- **No jersey/kit graphics.** Illegible at marker scale, expensive in SVG.
- **No team filter / "show only my team" toggle.** That is a game feature;
  there is no concept of "my team" yet.
- **No per-team pack composition stats as a separate readout.** The pack blob
  (decision 3) already carries composition visually; a numeric panel on top of
  it is redundant until someone asks for it.

---

## Work items

Current file layout for orientation (verify before editing — this tree may
have shifted):

```
src/
├── components/
│   ├── RaceViz.tsx          # container: playback loop, pack computation
│   ├── ElevationProfile.tsx # SVG area chart + marker rendering + tooltip
│   ├── RiderMarker.tsx      # memoized SVG circle marker
│   ├── RiderList.tsx        # pack-grouped table with gap dividers
│   ├── PlaybackControls.tsx
│   └── FileExplorer.tsx
├── types/race.ts            # Rider, Pack, ParsedRace, ...
└── utils/
    ├── gradientColors.ts    # gradient % -> colour (pattern to mirror)
    ├── computePacks.ts
    ├── interpolateRider.ts
    ├── parseRaceLog.ts
    └── useProfileScale.ts
```

### W1 — `src/types/race.ts`

Add to the `Rider` interface:

```ts
team?: string
role?: 'leader' | 'support'
```

Optional, per the data contract. No other type changes needed — the fields
flow through `parseRaceLog` and `computePacks` untouched.

### W2 — `src/utils/teamColors.ts` (new)

Mirror the existing `gradientColors.ts` module style.

- `TEAM_PALETTE: string[]` — the 12 hex values, in the documented order.
- `teamColor(team?: string): string` — neutral slate (`#64748b`) when `team`
  is undefined; otherwise a palette entry.

  **Lookup rule.** For an id matching `t<n>` where `1 <= n <= 12`, use
  `TEAM_PALETTE[n - 1]` directly, so `t1`..`t12` get exactly the documented
  colours. For any other id — or `n` outside that range — fall back to a
  deterministic **hash of the id into the palette**.

  Hash rather than first-seen order so a rider's colour is stable across
  files and across playback; order-based assignment would make colours shift
  as riders re-sort into packs each tick.

  With more than 12 teams the hash necessarily repeats a colour. That is the
  accepted degradation, not a bug to solve — see the 12-team ceiling above.
- `isLeader(rider: Rider): boolean` — returns `rider.role !== 'support'`.
  Centralise the absent-field default here; do not scatter `?? 'leader'`
  through the components.

### W3 — `src/components/RiderList.tsx` — do this FIRST

Highest value per line of code, and the easiest place to confirm the data is
actually flowing before touching SVG.

- **Team colour bar:** a 3px left border on each rider `<tr>`, in the team
  colour. Cheapest affiliation cue that survives rows re-sorting into packs
  every tick.
- **Crown:** 👑 before the rider name for leaders, alongside the existing
  `✅` finished prefix.
- **Legend:** the footer already legends `pulling` / `surging`. Add a swatch
  per team **present in the loaded race** (do not render all 12 when only 4
  are racing), plus 👑 = team leader. With 12 teams this row will need to
  wrap — let it, rather than truncating the list.

### W4 — `src/components/RiderMarker.tsx`

Individual markers still matter: under the adaptive rule (design decision 3)
they render every pack of 1–2 riders, which is most of the finale and every
breakaway — the parts of the race that decide it.

This component currently hardcodes a single red fill for every rider. Replace
with `teamColor(rider.team)`.

Leader treatment:
- Radius **7** for leaders, **5** for support. Active (hovered/selected):
  **9** and **7** respectively.
- Leaders additionally get a **small white inner dot** drawn on top of the
  fill. A filled-ring silhouette stays distinguishable when two markers
  overlap, where a size difference alone does not.
- Recolour the existing active outer ring to the team colour.

### W5 — `src/components/PackMarker.tsx` (new) — the pack blob

The centrepiece of the crowding fix (design decision 3). Renders one pack of
3+ riders as a single glyph carrying three pieces of information:

**a. Size.** Blob radius scales with rider count — sub-linearly (e.g. by
square root), so a 40-rider bunch does not dwarf a 4-rider break into
invisibility. Clamp to a sane min/max.

**b. Team composition — a segmented ring.** Draw the blob as a donut whose
arc segments are team colours, proportioned by how many of the pack's riders
belong to each team. This is not decoration: "the front group is half `t1`"
*is* the tactical picture in team racing, and it is the single most valuable
thing this view can show once teams exist.

- Sort segments by team id so composition stays visually stable tick to tick
  rather than churning as riders re-sort within the pack.
- Riders with no team contribute a neutral slate segment.

**c. Leaders present — pips.** Draw a small pip per team leader in the pack,
in that leader's team colour, around or on top of the ring. Leaders are the
riders that matter tactically; support riders are largely fungible to a
viewer. If a pack contains many leaders, cap the pips at a small number and
rely on the ring for the rest.

**Rider count** rendered as text in the donut hole when the blob is large
enough to fit it legibly; omit it below that size rather than shrinking the
text into illegibility.

**Interaction.** Hovering a blob shows a tooltip listing the pack: size, and
per-team counts with the leaders named. Clicking selects the pack — reuse the
existing selection path so the rider list can respond, rather than inventing a
parallel selection concept.

### W5b — `src/components/ElevationProfile.tsx`

Consume packs instead of a flat rider list.

- **Source the packs from `computePacks`, do not recompute.** `RaceViz`
  already calls it for the rider list, and it already returns
  `{ riders, frontPos, speed }` — exactly what is needed. Pass the existing
  result down; a second grouping implementation would be a bug waiting to
  drift from the first.
- **Position a blob at its pack's `frontPos`** (consistent with the rider
  list, which measures gaps front-to-back). Note this in the tooltip so the
  blob is not mistaken for a centroid.
- **Render pack-by-pack:** size 1–2 emits individual `RiderMarker`s, size 3+
  emits one `PackMarker`.
- **Z-order.** Draw larger packs first so smaller packs and individual riders
  paint on top of them — a lone attacker must never be hidden behind the
  bunch they just escaped. Within individual markers, leaders still draw last
  (per W4).
- **Tooltip:** keep the existing rider tooltip for individual markers, adding
  the team swatch, team name, and 👑 for leaders. Add the separate pack
  tooltip described in W5.
- **Tooltip box sizing:** the tooltip `<rect>` has fixed dimensions while its
  text already overflows it. Both tooltips now carry more content. Size the
  box to its actual content rather than adding to the existing overflow.

### W6 — team summary strip (`RaceViz.tsx`) — optional, do last

A compact row above the profile: one chip per team showing team colour, team
name, and that team's **leader's current race position**. Answers "how is my
team doing?" at a glance.

This is the only genuinely new UI surface in the plan; everything else
enhances an existing component. **Cut this first if scope bites.**

**Reassess whether this is still needed after W5 lands.** A segmented-ring
blob on the lead group already answers "which teams are represented at the
front" fairly well. If it does, this strip is redundant and should be dropped
rather than built for completeness.

---

## Execution order

1. Regenerate `.jsonl` files in `public/` (data contract section).
2. **W1** types + **W2** `teamColors.ts` — foundation, no visual change.
3. **W3** `RiderList` — confirms data flow with minimal risk.
4. **W4** `RiderMarker` — team colours and leader shape on individual
   markers.
5. **W5** `PackMarker` + **W5b** `ElevationProfile` — the pack blob and
   adaptive rendering. Largest item; do it as its own reviewable step.
6. **W6** summary strip (optional, and reassess per W6).
7. Update `race_player/DOMAIN.md` — see below.

## Documentation update (required, not optional)

`race_player/DOMAIN.md` is the authoritative spec for this app. Update:

- **Key Data Fields** — add `team` and `role`, noting both are optional.
- **Core Features** — team colouring and the leader crown, including the
  decision that the profile markers use shape rather than an emoji.
- **File structure tree** — add `utils/teamColors.ts` and
  `components/PackMarker.tsx`.
- **Core Features → Elevation Profile** — the profile no longer renders one
  marker per rider. Document the adaptive pack-blob rule, the size threshold,
  and that blobs sit at the pack's `frontPos`.

---

## Verification

The failure mode for this work is **"looks fine strung out, unreadable in a
bunch"**. Verify at a bunch moment specifically:

1. Load **`sprinters_classic`** (flattest course, so the largest and most
   compressed bunch). Scrub to mid-race with the field together. The bunch
   must render as **one blob** whose ring shows team composition — not a pile
   of overlapping circles.
2. Load **`mountain_stage`** (most selective) and scrub to the finale to
   confirm the strung-out case falls back to **individual markers** with team
   colours and identifiable leaders.
3. **Watch the transition.** Play through a selection (a bunch breaking up)
   and confirm blobs split into smaller blobs and then into individuals
   without flicker or jumping. Rapid oscillation at the size threshold is the
   most likely defect in this work.
4. Load an **old log lacking `team`/`role`** and confirm it still loads and
   plays with the neutral fallback rather than crashing — blobs render as
   all-slate rings.
5. **Many-teams check.** The bundled configs use 4 teams, so the upper end is
   untested by default. Hand-edit a config (or a generated log) to carry 10–12
   teams and confirm the palette still reads in a bunch and the list legend
   wraps sensibly. This is the case the palette was designed for and the one
   most likely to be shipped unverified.
6. Confirm both tooltip boxes visually contain all of their text.

**A screenshot of the compressed-bunch case is the deliverable that proves
this works. A strung-out screenshot proves nothing.**

## Risks

- **Threshold oscillation is the likeliest defect.** A pack hovering at the
  size boundary can flip between blob and individual markers every tick,
  producing visible flicker. If it appears, damp it (hysteresis: split at 3,
  re-merge at 2) rather than raising the threshold.
- **The blob must not hide a decisive move.** A lone attacker just off the
  front is the most important thing on screen. The z-order rule in W5b
  (larger packs painted first) is what protects this; verify it specifically
  at the moment of an attack, not just on a static frame.
- **Composition is only readable above a certain blob size.** A 3-rider pack
  with 3 teams gives three thin arcs. Accept coarse rendering at small sizes —
  small packs are also the case where hovering for the tooltip is easy.
- **More than 12 teams degrades to repeated colours.** The hash fallback
  keeps the app working and stable, but two teams will share a hue. If races
  routinely exceed 12 teams, colour is the wrong channel and the fix is a
  different identity mechanism — raise it rather than extending the palette.
- **Emoji rendering varies by platform.** 👑 is widely supported and is used
  only where a fallback box would be merely ugly, never where it would break
  layout.
- **Stale logs fail silently** (all-slate, all-leader) rather than erroring.
  See the data contract section.
