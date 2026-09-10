import { useMemo, useRef, useState } from 'react'
import type { Pack, ProfilePoint, Rider } from '../types/race'
import { gradientColorForPoint } from '../utils/gradientColors'
import { profilePointAtDistance } from '../utils/interpolateRider'
import { useProfileScale } from '../utils/useProfileScale'
import { isLeader, teamColor } from '../utils/teamColors'
import RiderMarker from './RiderMarker'
import PackMarker from './PackMarker'

interface ElevationProfileProps {
  profile: ProfilePoint[]
  packs: Pack[]
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

// Adaptive pack-blob threshold (design decision 3, TEAM_VISUALIZATION_PLAN.md):
// packs of 1-2 render as individual markers, 3+ collapse into a single blob.
// Hysteresis (split at 3, re-merge at 2) damps flicker for packs hovering at
// the boundary — a pack must reach 3 to become a blob, and drop to 1 to
// split back to individuals.
const BLOB_SPLIT_SIZE = 3
const BLOB_MERGE_SIZE = 1

function useBlobHysteresis(packs: Pack[]): Map<string, boolean> {
  const stateRef = useRef<Map<string, boolean>>(new Map())

  return useMemo(() => {
    const prev = stateRef.current
    const next = new Map<string, boolean>()
    for (const pack of packs) {
      const key = pack.riders[0].id
      const wasBlob = prev.get(key) ?? false
      let isBlob: boolean
      if (pack.riders.length >= BLOB_SPLIT_SIZE) {
        isBlob = true
      } else if (pack.riders.length <= BLOB_MERGE_SIZE) {
        isBlob = false
      } else {
        isBlob = wasBlob
      }
      next.set(key, isBlob)
    }
    stateRef.current = next
    return next
  }, [packs])
}

export default function ElevationProfile({
  profile,
  packs,
  width = 900,
  height = 300,
  onSelectRider,
}: ElevationProfileProps) {
  const [hoveredRider, setHoveredRider] = useState<Rider | null>(null)
  const [hoveredPack, setHoveredPack] = useState<Pack | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const isBlobByKey = useBlobHysteresis(packs)

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

  // Renderable items: a pack becomes a single blob (3+ riders, sticky via
  // hysteresis) or emits one marker per rider (1-2 riders). Sorted largest
  // pack first so smaller packs / individuals paint on top (z-order rule,
  // W5b) — a lone attacker off the front must never be hidden behind the
  // bunch they escaped.
  const renderItems = useMemo(() => {
    const blobs: { kind: 'blob'; pack: Pack; x: number; y: number }[] = []
    const singles: { kind: 'single'; rider: Rider; x: number; y: number }[] = []

    for (const pack of packs) {
      const key = pack.riders[0].id
      if (isBlobByKey.get(key)) {
        const pt = profilePointAtDistance(profile, pack.frontPos)
        blobs.push({ kind: 'blob', pack, x: scale.x(pt.x), y: scale.y(pt.y) })
      } else {
        for (const rider of pack.riders) {
          const pt = profilePointAtDistance(profile, rider.pos)
          singles.push({ kind: 'single', rider, x: scale.x(pt.x), y: scale.y(pt.y) })
        }
      }
    }

    blobs.sort((a, b) => b.pack.riders.length - a.pack.riders.length)
    // Leaders draw last among individual markers (per W4).
    singles.sort((a, b) => Number(isLeader(a.rider)) - Number(isLeader(b.rider)))

    return [...blobs, ...singles]
  }, [packs, isBlobByKey, profile, scale])

  const activeId = hoveredRider?.id ?? selectedId

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

      {/* Pack blobs and rider markers, larger packs painted first */}
      <g>
        {renderItems.map((item) =>
          item.kind === 'blob' ? (
            <PackMarker
              key={`pack-${item.pack.riders[0].id}`}
              pack={item.pack}
              x={item.x}
              y={item.y}
              active={hoveredPack === item.pack}
              onClick={() => onSelectRider?.(item.pack.riders[0].id)}
              onHover={(p) => setHoveredPack(p)}
            />
          ) : (
            <RiderMarker
              key={item.rider.id}
              rider={item.rider}
              x={item.x}
              y={item.y}
              active={item.rider.id === activeId}
              onClick={() => {
                setSelectedId((cur) => (cur === item.rider.id ? null : item.rider.id))
                onSelectRider?.(item.rider.id)
              }}
              onHover={(r) => setHoveredRider(r)}
            />
          ),
        )}
      </g>

      {/* Rider tooltip */}
      {hoveredRider && (
        <RiderTooltip rider={hoveredRider} marginLeft={scale.margin.left} marginTop={scale.margin.top} />
      )}

      {/* Pack tooltip */}
      {hoveredPack && !hoveredRider && (
        <PackTooltip pack={hoveredPack} marginLeft={scale.margin.left} marginTop={scale.margin.top} />
      )}
    </svg>
  )
}

function TooltipBox({
  x,
  y,
  width,
  height,
  children,
}: {
  x: number
  y: number
  width: number
  height: number
  children: React.ReactNode
}) {
  return (
    <g transform={`translate(${x}, ${y})`}>
      <rect
        width={width}
        height={height}
        rx={6}
        fill="white"
        stroke="#e2e8f0"
        strokeWidth={1}
      />
      {children}
    </g>
  )
}

function RiderTooltip({
  rider,
  marginLeft,
  marginTop,
}: {
  rider: Rider
  marginLeft: number
  marginTop: number
}) {
  const lines = [
    `pos: ${Math.round(rider.pos)} m`,
    `speed: ${(rider.speed * 3.6).toFixed(1)} km/h`,
    `energy ${rider.energy.toFixed(0)}% · stamina ${rider.stamina.toFixed(0)}%`,
  ]
  const headerHeight = 28
  const lineHeight = 16
  const bottomPadding = 10

  const nameText = `${isLeader(rider) ? '\u{1F451} ' : ''}${rider.name}`
  const textWidth = Math.max(nameText.length * 7, ...lines.map((l) => l.length * 6)) + 40
  const width = Math.max(170, textWidth)

  let cursorY = headerHeight
  const teamRowY = rider.team ? (cursorY += lineHeight) : null
  const lineYs = lines.map(() => (cursorY += lineHeight))
  const height = cursorY + bottomPadding

  return (
    <TooltipBox x={marginLeft + 10} y={marginTop + 10} width={width} height={height}>
      <text x={18} y={20} fontSize={12} fontWeight={600} fill="#0f172a">
        {nameText}
      </text>
      {rider.team && teamRowY && (
        <g transform={`translate(18, ${teamRowY - 9})`}>
          <rect width={10} height={10} rx={2} fill={teamColor(rider.team)} />
          <text x={16} y={9} fontSize={11} fill="#334155">
            {rider.team}
          </text>
        </g>
      )}
      {lines.map((line, i) => (
        <text key={i} x={18} y={lineYs[i]} fontSize={11} fill="#334155">
          {line}
        </text>
      ))}
    </TooltipBox>
  )
}

function PackTooltip({
  pack,
  marginLeft,
  marginTop,
}: {
  pack: Pack
  marginLeft: number
  marginTop: number
}) {
  const counts = new Map<string | undefined, number>()
  for (const rider of pack.riders) {
    counts.set(rider.team, (counts.get(rider.team) ?? 0) + 1)
  }
  const teamRows = [...counts.entries()].sort(([a], [b]) => {
    if (a === undefined) return 1
    if (b === undefined) return -1
    return a.localeCompare(b)
  })

  const leaders = pack.riders.filter(isLeader)
  const leaderLine =
    leaders.length > 0 ? `\u{1F451} ${leaders.map((l) => l.name).join(', ')}` : null

  const headerHeight = 28
  const lineHeight = 16

  let cursorY = headerHeight
  const subtitleY = (cursorY += lineHeight)
  const teamRowYs = teamRows.map(() => (cursorY += lineHeight))
  const leaderLineY = leaderLine ? (cursorY += lineHeight) : null
  const height = cursorY + 10

  const allLines = [
    `${pack.riders.length} riders · measured at front position`,
    ...teamRows.map(([team, count]) => `${team ?? 'no team'}: ${count}`),
    ...(leaderLine ? [leaderLine] : []),
  ]
  const textWidth = Math.max(140, ...allLines.map((l) => l.length * 6)) + 40
  const width = Math.max(180, textWidth)

  return (
    <TooltipBox x={marginLeft + 10} y={marginTop + 10} width={width} height={height}>
      <text x={18} y={20} fontSize={12} fontWeight={600} fill="#0f172a">
        Pack ({pack.riders.length} riders)
      </text>
      <text x={18} y={subtitleY} fontSize={10} fill="#94a3b8">
        position measured at pack front
      </text>
      {teamRows.map(([team, count], i) => (
        <g key={i} transform={`translate(18, ${teamRowYs[i] - 9})`}>
          <rect width={10} height={10} rx={2} fill={teamColor(team)} />
          <text x={16} y={9} fontSize={11} fill="#334155">
            {team ?? 'no team'}: {count}
          </text>
        </g>
      ))}
      {leaderLine && leaderLineY && (
        <text x={18} y={leaderLineY} fontSize={11} fill="#334155">
          {leaderLine}
        </text>
      )}
    </TooltipBox>
  )
}
