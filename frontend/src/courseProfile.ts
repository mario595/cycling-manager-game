import { COURSE_LENGTH_M, COURSE_SEGMENTS } from './placeholderData'

/**
 * Turn the course's `[length, gradient]` segments into SVG point strings.
 *
 * Elevation is accumulated segment by segment, then normalised into the box so
 * the profile always fills the available height regardless of how much total
 * climbing there is. Returns both a polyline (the ridge) and a polygon (the
 * same ridge closed along the bottom edge, for the fill).
 */
export function buildProfile(width: number, height: number, pad: number) {
  let elevation = 0
  let distance = 0
  const points: Array<[number, number]> = [[0, 0]]
  let min = 0
  let max = 0

  for (const [length, gradient] of COURSE_SEGMENTS) {
    distance += length
    elevation += (length * gradient) / 100
    if (elevation < min) min = elevation
    if (elevation > max) max = elevation
    points.push([distance, elevation])
  }

  const span = Math.max(1, max - min)
  const scaled = points.map(([d, e]): [number, number] => [
    (d / COURSE_LENGTH_M) * width,
    height - pad - ((e - min) / span) * (height - pad * 2),
  ])

  const line = scaled.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')

  return {
    line,
    polygon: `${line} ${width},${height} 0,${height}`,
  }
}
