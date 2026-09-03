import type { ProfilePoint } from '../types/race'

export interface InterpolatedPoint {
  x: number
  y: number
}

/**
 * Given a rider's distance (pos) and the elevation profile, returns
 * the (x, y) screen coordinates on the profile line.
 *
 * x = distance (meters from start)
 * y = elevation (meters, derived from accumulated gradients)
 */
export function profilePointAtDistance(
  profile: ProfilePoint[],
  pos: number,
): InterpolatedPoint {
  if (pos <= 0) {
    return { x: profile[0].distance, y: profile[0].elevation }
  }

  const last = profile[profile.length - 1]
  if (pos >= last.distance) {
    return { x: last.distance, y: last.elevation }
  }

  // Binary search for the segment containing pos
  let lo = 0
  let hi = profile.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (profile[mid].distance <= pos) {
      lo = mid
    } else {
      hi = mid
    }
  }

  const p1 = profile[lo]
  const p2 = profile[hi]
  const t = p2.distance === p1.distance ? 0 : (pos - p1.distance) / (p2.distance - p1.distance)

  return {
    x: p1.distance + t * (p2.distance - p1.distance),
    y: p1.elevation + t * (p2.elevation - p1.elevation),
  }
}
