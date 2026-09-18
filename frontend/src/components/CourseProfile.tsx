import type { CourseSegment } from '../api'
import { color } from '../theme'

const VIEWBOX_WIDTH = 600
const VIEWBOX_HEIGHT = 160
const PAD = 10

/** Cumulative (distance, altitude) points — altitude runs up `length * gradient`.
 * A flat course stays flat: a zero range normalises to mid-height. */
function cumulativePoints(course: CourseSegment[]): Array<{ x: number; y: number }> {
  const points: Array<{ x: number; y: number }> = [{ x: 0, y: 0 }]
  let distance = 0
  let altitude = 0
  for (const segment of course) {
    distance += segment.length
    altitude += segment.length * segment.gradient
    points.push({ x: distance, y: altitude })
  }
  return points
}

/** The course as an elevation sparkline — a filled polygon under a stroked
 * polyline, both axes scaled into the viewBox. Flat stays flat; that is
 * information, not a bug to special-case. */
export function CourseProfile({ course }: { course: CourseSegment[] }) {
  const points = cumulativePoints(course)
  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const xRange = maxX - minX || 1
  const yRange = maxY - minY || 1
  const scaleX = VIEWBOX_WIDTH - 2 * PAD
  const scaleY = VIEWBOX_HEIGHT - 2 * PAD

  const toX = (x: number) => PAD + ((x - minX) / xRange) * scaleX
  const toY = (y: number) => VIEWBOX_HEIGHT - PAD - ((y - minY) / yRange) * scaleY

  const line = points.map((p) => `${toX(p.x)},${toY(p.y)}`).join(' ')
  const polygon = `${PAD},${VIEWBOX_HEIGHT - PAD} ${line} ${VIEWBOX_WIDTH - PAD},${VIEWBOX_HEIGHT - PAD}`

  return (
    <svg viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`} style={{ display: 'block', width: '100%' }}>
      <polygon points={polygon} fill={color.accent} fillOpacity={0.15} />
      <polyline
        points={line}
        fill="none"
        stroke={color.accent}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}