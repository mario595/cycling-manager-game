import type { ProfilePoint, Segment } from '../types/race'

/**
 * Derive the elevation profile from the course's raw segments. Absolute
 * altitude is not stored in engine logs, so it is built up from zero:
 * `elevation_change = length * (gradient / 100)` meters — a 4% gradient over
 * 40 km climbs 1600 m. The frontend's race-detail screen derives its course
 * profile with this same function so the calendar and the visualizer always
 * agree on how a course looks.
 */
export function computeProfile(segments: Segment[]): ProfilePoint[] {
  const points: ProfilePoint[] = []
  let elevation = 0
  let distance = 0

  points.push({ distance: 0, elevation: 0, gradient: segments[0]?.gradient ?? 0 })

  for (const seg of segments) {
    const change = seg.length * (seg.gradient / 100)
    elevation += change
    distance += seg.length
    points.push({ distance, elevation, gradient: seg.gradient })
  }

  return points
}