export type GradientColorResult = { from: string; to: string }

/**
 * Map a gradient percentage to a color pair for the profile area.
 * - descents (gradient < 0): blue tones
 * - flat (0): green
 * - climbs: green -> yellow -> red as gradient increases
 */
export function gradientColor(gradient: number): GradientColorResult {
  if (gradient < 0) {
    return { from: '#3b82f6', to: '#60a5fa' }
  }
  if (gradient <= 2) {
    return { from: '#22c55e', to: '#4ade80' }
  }
  if (gradient <= 6) {
    return { from: '#eab308', to: '#facc15' }
  }
  if (gradient <= 10) {
    return { from: '#f97316', to: '#fb923c' }
  }
  return { from: '#ef4444', to: '#f87171' }
}

export function gradientColorForPoint(gradient: number): string {
  return gradientColor(gradient).from
}
