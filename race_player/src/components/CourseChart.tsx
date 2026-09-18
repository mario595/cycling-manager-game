import { useId, useMemo } from 'react'
import type { ReactNode } from 'react'

import type { ProfilePoint } from '../types/race'
import { gradientColorForPoint } from '../utils/gradientColors'
import { profileScale, type ProfileScale } from '../utils/useProfileScale'

export interface CourseBounds {
  minElevation: number
  maxElevation: number
  maxDistance: number
}

export interface CourseSegmentDef {
  d: string
  color: string
  gradient: number
  midX: number
  midY: number
}

/** Bounds for profile scaling. maxElevation keeps 20 m of headroom so the
 * highest point is never flush against the chart top. */
export function courseBounds(profile: ProfilePoint[]): CourseBounds {
  let minElevation = Infinity
  let maxElevation = -Infinity
  for (const p of profile) {
    if (p.elevation < minElevation) minElevation = p.elevation
    if (p.elevation > maxElevation) maxElevation = p.elevation
  }
  return {
    minElevation,
    maxElevation: maxElevation + 20,
    maxDistance: profile[profile.length - 1].distance,
  }
}

/** One filled trapezoid per course segment, dropped to the chart baseline —
 * each segment's slope becomes an area in its own gradient colour. */
export function courseSegments(
  profile: ProfilePoint[],
  scale: ProfileScale,
  minElevation: number,
): CourseSegmentDef[] {
  const segs: CourseSegmentDef[] = []
  for (let i = 0; i < profile.length - 1; i++) {
    const p1 = profile[i]
    const p2 = profile[i + 1]
    const x1 = scale.x(p1.distance)
    const y1 = scale.y(p1.elevation)
    const x2 = scale.x(p2.distance)
    const y2 = scale.y(p2.elevation)
    const bottom = scale.y(minElevation)
    segs.push({
      d: `M ${x1} ${y1} L ${x2} ${y2} L ${x2} ${bottom} L ${x1} ${bottom} Z`,
      color: gradientColorForPoint(p2.gradient),
      gradient: p2.gradient,
      midX: (x1 + x2) / 2,
      midY: (y1 + y2) / 2,
    })
  }
  return segs
}

export interface CourseChartProps {
  profile: ProfilePoint[]
  width?: number
  height?: number
  /** Extra SVG content drawn on top of the chart with the same scale (for
   * example rider markers in the visualizer), so overlays stay aligned with
   * the drawn course. */
  overlay?: (scale: ProfileScale, bounds: CourseBounds) => ReactNode
}

/** The elevation chart: gradient-colored segments, % labels, km markers and
 * axes. Shared by the race_player visualizer and the frontend's race-detail
 * screen — the frontend imports this same component instead of keeping its
 * own course drawing. */
export default function CourseChart({
  profile,
  width = 900,
  height = 300,
  overlay,
}: CourseChartProps) {
  const bounds = courseBounds(profile)
  const scale = profileScale(
    width,
    height,
    bounds.maxDistance,
    bounds.minElevation,
    bounds.maxElevation,
  )
  const segments = useMemo(
    () => courseSegments(profile, scale, bounds.minElevation),
    [profile, scale, bounds.minElevation],
  )
  const clipId = useId()

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Elevation profile"
    >
      <defs>
        <clipPath id={clipId}>
          <rect x={0} y={0} width={width} height={height} />
        </clipPath>
      </defs>

      <rect x={0} y={0} width={width} height={height} fill="#f8fafc" rx={8} />

      <g clipPath={`url(#${clipId})`}>
        {segments.map((seg, i) => (
          <path key={i} d={seg.d} fill={seg.color} opacity={0.55} />
        ))}

        {segments.map((seg, i) => (
          <path
            key={`line-${i}`}
            d={seg.d.split(' L ').slice(0, 2).join(' L ')}
            fill="none"
            stroke={seg.color}
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}

        {profile.slice(0, -1).map((_, i) => {
          const x1 = scale.x(profile[i].distance)
          const x2 = scale.x(profile[i + 1].distance)
          if (x2 - x1 < 40) return null
          return (
            <text
              key={`grad-${i}`}
              x={(x1 + x2) / 2}
              y={scale.y(bounds.minElevation) + 14}
              textAnchor="middle"
              fontSize={10}
              fill="#64748b"
            >
              {`${Math.round(profile[i + 1].gradient)}%`}
            </text>
          )
        })}
      </g>

      {/* Axes */}
      <line
        x1={scale.margin.left}
        y1={scale.y(bounds.minElevation)}
        x2={width - scale.margin.right}
        y2={scale.y(bounds.minElevation)}
        stroke="#cbd5e1"
        strokeWidth={1}
      />
      <line
        x1={scale.margin.left}
        y1={scale.margin.top}
        x2={scale.margin.left}
        y2={scale.y(bounds.minElevation)}
        stroke="#cbd5e1"
        strokeWidth={1}
      />
      <text
        x={scale.margin.left - 10}
        y={scale.y(Math.max(0, bounds.minElevation))}
        textAnchor="end"
        fontSize={10}
        fill="#64748b"
      >
        elevation (m)
      </text>

      {/* Km markers every 5km */}
      {Array.from({ length: Math.floor(bounds.maxDistance / 5000) + 1 }, (_, i) => i * 5000).map(
        (km) => {
          const x = scale.x(km)
          const y = scale.y(bounds.minElevation)
          return (
            <g key={`km-${km}`}>
              <line x1={x} y1={y} x2={x} y2={y + 6} stroke="#94a3b8" strokeWidth={1} />
              <text
                x={x}
                y={y + 16}
                textAnchor="middle"
                fontSize={9}
                fill="#94a3b8"
              >
                {km === 0 ? '0' : `${km / 1000}`}
              </text>
            </g>
          )
        },
      )}

      <text
        x={width / 2}
        y={height - 10}
        textAnchor="middle"
        fontSize={11}
        fill="#64748b"
      >
        distance (km)
      </text>

      {/* Overlays (markers, tooltips) paint last, above axes and labels. */}
      {overlay?.(scale, bounds)}
    </svg>
  )
}