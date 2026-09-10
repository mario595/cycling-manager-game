/**
 * Wind display helpers (race_player/WIND_VISUALIZATION_PLAN.md). Pure
 * functions only — components stay dumb and just call these.
 */

const CALM_COLOR = '#94a3b8' // slate
const LIGHT_COLOR = '#38bdf8' // sky blue
const MODERATE_COLOR = '#f59e0b' // amber
const STRONG_COLOR = '#ef4444' // red

const MIN_ARROW_LENGTH = 10
const MAX_ARROW_LENGTH = 34
// Speeds at/above this are treated as "as strong as the arrow gets" — chosen
// to sit inside the `strong` band's mean range (24-38 km/h) rather than at
// its outer edge, so a merely-strong day doesn't max out the arrow.
const ARROW_MAX_SPEED = 30

/**
 * Colour ramp derived from the live speed (not the band), so the arrow's
 * colour breathes continuously as wind drifts rather than jumping only when
 * the band changes. Thresholds mirror the band's own mean ranges.
 */
export function windColor(speed: number): string {
  if (speed < 6) return CALM_COLOR
  if (speed < 14) return LIGHT_COLOR
  if (speed < 24) return MODERATE_COLOR
  return STRONG_COLOR
}

/**
 * Arrow length in px from live speed, clamped so a calm day still shows a
 * short, thin arrow and nothing runs past the compass's own bounds.
 */
export function arrowLength(speed: number): number {
  const t = Math.max(0, Math.min(1, speed / ARROW_MAX_SPEED))
  return MIN_ARROW_LENGTH + t * (MAX_ARROW_LENGTH - MIN_ARROW_LENGTH)
}

/**
 * Rider-relative wind label, bucketed from the angle convention (0=head,
 * 90=from the right, 180=tail, 270=from the left). Used for the compass
 * readout, the tooltip, and accessibility text.
 */
export function windLabel(angle: number): string {
  const a = ((angle % 360) + 360) % 360
  if (a < 22.5 || a >= 337.5) return 'Headwind'
  if (a < 67.5) return 'Headwind (R)'
  if (a < 112.5) return 'Crosswind (R)'
  if (a < 157.5) return 'Tailwind (R)'
  if (a < 202.5) return 'Tailwind'
  if (a < 247.5) return 'Tailwind (L)'
  if (a < 292.5) return 'Crosswind (L)'
  return 'Headwind (L)'
}

/**
 * Shortest-arc-unwrapped angle: returns the value closest to `prev` that is
 * congruent to `next` mod 360, so a CSS rotation transition (or any
 * continuously-tracked rotation) takes the short way around a 359->1 wrap
 * instead of spinning the long way through 180.
 */
export function unwrapAngle(prev: number, next: number): number {
  const delta = ((next - prev + 180) % 360 + 360) % 360 - 180
  return prev + delta
}
