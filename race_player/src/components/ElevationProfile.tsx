import { useMemo, useState } from 'react'
import type { ProfilePoint, Rider } from '../types/race'
import { gradientColorForPoint } from '../utils/gradientColors'
import { profilePointAtDistance } from '../utils/interpolateRider'
import { useProfileScale } from '../utils/useProfileScale'
import RiderMarker from './RiderMarker'

interface ElevationProfileProps {
  profile: ProfilePoint[]
  riders: Rider[]
  width?: number
  height?: number
  onSelectRider?: (id: string) => void
}

interface SegmentDef {
  d: string
  color: string
  gradient: number
  midX: number
  midY: number
}

interface RiderDef {
  rider: Rider
  x: number
  y: number
}

export default function ElevationProfile({
  profile,
  riders,
  width = 900,
  height = 300,
  onSelectRider,
}: ElevationProfileProps) {
  const [hovered, setHovered] = useState<Rider | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { minElevation, maxElevation, maxDistance } = useMemo(() => {
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
  }, [profile])

  const scale = useProfileScale(width, height, maxDistance, minElevation, maxElevation)

  const segments = useMemo<SegmentDef[]>(() => {
    const segs: SegmentDef[] = []
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
  }, [profile, scale, minElevation])

  const riderDefs = useMemo<RiderDef[]>(() => {
    return riders.map((rider) => {
      const pt = profilePointAtDistance(profile, rider.pos)
      return { rider, x: scale.x(pt.x), y: scale.y(pt.y) }
    })
  }, [riders, profile, scale])

  // The active rider (selected or hovered)
  const activeId = hovered?.id ?? selectedId

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      className="select-none"
      role="img"
      aria-label="Elevation profile"
    >
      <defs>
        <clipPath id="profile-clip">
          <rect x={0} y={0} width={width} height={height} />
        </clipPath>
      </defs>

      <rect
        x={0}
        y={0}
        width={width}
        height={height}
        fill="#f8fafc"
        rx={8}
      />

      <g clipPath="url(#profile-clip)">
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
              y={scale.y(minElevation) + 14}
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
        y1={scale.y(minElevation)}
        x2={width - scale.margin.right}
        y2={scale.y(minElevation)}
        stroke="#cbd5e1"
        strokeWidth={1}
      />
      <line
        x1={scale.margin.left}
        y1={scale.margin.top}
        x2={scale.margin.left}
        y2={scale.y(minElevation)}
        stroke="#cbd5e1"
        strokeWidth={1}
      />
      <text
        x={scale.margin.left - 10}
        y={scale.y(Math.max(0, minElevation))}
        textAnchor="end"
        fontSize={10}
        fill="#64748b"
      >
        elevation (m)
      </text>

      {/* Km markers every 5km */}
      {Array.from({ length: Math.floor(maxDistance / 5000) + 1 }, (_, i) => i * 5000).map((km) => {
        const x = scale.x(km)
        const y = scale.y(minElevation)
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
      })}

      <text
        x={width / 2}
        y={height - 10}
        textAnchor="middle"
        fontSize={11}
        fill="#64748b"
      >
        distance (km)
      </text>

      {/* Rider markers */}
      <g>
        {riderDefs.map(({ rider, x, y }) => (
          <RiderMarker
            key={rider.id}
            rider={rider}
            x={x}
            y={y}
            active={rider.id === activeId}
            onClick={() => {
              setSelectedId((cur) => (cur === rider.id ? null : rider.id))
              onSelectRider?.(rider.id)
            }}
            onHover={(r) => setHovered(r)}
          />
        ))}
      </g>

      {/* Tooltip */}
      {hovered && (
        <g transform={`translate(0,0)`}>
          <rect
            x={scale.margin.left + 10}
            y={scale.margin.top + 10}
            width={170}
            height={70}
            rx={6}
            fill="white"
            stroke="#e2e8f0"
            strokeWidth={1}
          />
          <text x={scale.margin.left + 18} y={scale.margin.top + 28} fontSize={12} fontWeight={600} fill="#0f172a">
            {hovered.name}
          </text>
          <text x={scale.margin.left + 18} y={scale.margin.top + 46} fontSize={11} fill="#334155">
            pos: {Math.round(hovered.pos)} m
          </text>
          <text x={scale.margin.left + 18} y={scale.margin.top + 62} fontSize={11} fill="#334155">
            speed: {(hovered.speed * 3.6).toFixed(1)} km/h
          </text>
          <text x={scale.margin.left + 18} y={scale.margin.top + 76} fontSize={11} fill="#334155">
            energy {hovered.energy.toFixed(0)}% · stamina {hovered.stamina.toFixed(0)}%
          </text>
        </g>
      )}
    </svg>
  )
}
