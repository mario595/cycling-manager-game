import { useMemo, useRef, useState } from 'react'
import type { Pack, ProfilePoint, Rider } from '../types/race'
import { profilePointAtDistance } from '../utils/interpolateRider'
import { isLeader, teamColor } from '../utils/teamColors'
import CourseChart from './CourseChart'
import PackMarker from './PackMarker'
import RiderMarker from './RiderMarker'

interface ElevationProfileProps {
  profile: ProfilePoint[]
  packs: Pack[]
  width?: number
  height?: number
  onSelectRider?: (id: string) => void
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

  const activeId = hoveredRider?.id ?? selectedId

  return (
    <CourseChart
      profile={profile}
      width={width}
      height={height}
      overlay={(scale) => {
        // Renderable items: a pack becomes a single blob (3+ riders, sticky via
        // hysteresis) or emits one marker per rider (1-2 riders). Sorted largest
        // pack first so smaller packs / individuals paint on top (z-order rule,
        // TEAM_VISUALIZATION_PLAN.md W5b) — a lone attacker off the front must
        // never be hidden behind the bunch they escaped.
        const blobs: { kind: 'blob'; pack: Pack }[] = []
        const singles: { kind: 'single'; rider: Rider }[] = []

        for (const pack of packs) {
          const key = pack.riders[0].id
          if (isBlobByKey.get(key)) {
            blobs.push({ kind: 'blob', pack })
          } else {
            for (const rider of pack.riders) {
              singles.push({ kind: 'single', rider })
            }
          }
        }

        blobs.sort((a, b) => b.pack.riders.length - a.pack.riders.length)
        // Leaders draw last among individual markers (per W4).
        singles.sort((a, b) => Number(isLeader(a.rider)) - Number(isLeader(b.rider)))

        return (
          <>
            {/* Pack blobs and rider markers, larger packs painted first */}
            <g>
              {[...blobs, ...singles].map((item) => {
                if (item.kind === 'blob') {
                  const pt = profilePointAtDistance(profile, item.pack.frontPos)
                  return (
                    <PackMarker
                      key={`pack-${item.pack.riders[0].id}`}
                      pack={item.pack}
                      x={scale.x(pt.x)}
                      y={scale.y(pt.y)}
                      active={hoveredPack === item.pack}
                      onClick={() => onSelectRider?.(item.pack.riders[0].id)}
                      onHover={(p) => setHoveredPack(p)}
                    />
                  )
                }
                const pt = profilePointAtDistance(profile, item.rider.pos)
                return (
                  <RiderMarker
                    key={item.rider.id}
                    rider={item.rider}
                    x={scale.x(pt.x)}
                    y={scale.y(pt.y)}
                    active={item.rider.id === activeId}
                    onClick={() => {
                      setSelectedId((cur) => (cur === item.rider.id ? null : item.rider.id))
                      onSelectRider?.(item.rider.id)
                    }}
                    onHover={(r) => setHoveredRider(r)}
                  />
                )
              })}
            </g>

            {/* Rider tooltip */}
            {hoveredRider && (
              <RiderTooltip
                rider={hoveredRider}
                marginLeft={scale.margin.left}
                marginTop={scale.margin.top}
              />
            )}

            {/* Pack tooltip */}
            {hoveredPack && !hoveredRider && (
              <PackTooltip
                pack={hoveredPack}
                marginLeft={scale.margin.left}
                marginTop={scale.margin.top}
              />
            )}
          </>
        )
      }}
    />
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