import { memo } from 'react'
import type { Pack, Rider } from '../types/race'
import { isLeader, teamColor } from '../utils/teamColors'

interface PackMarkerProps {
  pack: Pack
  x: number
  y: number
  active?: boolean
  onClick?: () => void
  onHover?: (pack: Pack | null) => void
}

const MIN_RADIUS = 12
const MAX_RADIUS = 34
const RADIUS_PER_SQRT_RIDER = 4.5

const RING_THICKNESS_RATIO = 0.35
const MIN_RADIUS_FOR_COUNT_TEXT = 18
const MAX_PIPS = 5
const PIP_RADIUS = 2.5

interface TeamSegment {
  team: string | undefined
  count: number
  color: string
}

function groupByTeam(riders: Rider[]): TeamSegment[] {
  const counts = new Map<string | undefined, number>()
  for (const rider of riders) {
    const key = rider.team
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  const segments = [...counts.entries()].map(([team, count]) => ({
    team,
    count,
    color: teamColor(team),
  }))
  segments.sort((a, b) => {
    if (a.team === undefined) return 1
    if (b.team === undefined) return -1
    return a.team.localeCompare(b.team)
  })
  return segments
}

function describeArc(radius: number, startAngle: number, endAngle: number): string {
  const start = {
    x: radius * Math.cos(startAngle),
    y: radius * Math.sin(startAngle),
  }
  const end = {
    x: radius * Math.cos(endAngle),
    y: radius * Math.sin(endAngle),
  }
  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArc} 1 ${end.x} ${end.y}`
}

function PackMarker({ pack, x, y, active, onClick, onHover }: PackMarkerProps) {
  const riderCount = pack.riders.length
  const radius = Math.min(
    MAX_RADIUS,
    Math.max(MIN_RADIUS, RADIUS_PER_SQRT_RIDER * Math.sqrt(riderCount)),
  )
  const thickness = radius * RING_THICKNESS_RATIO
  const ringRadius = radius - thickness / 2

  const segments = groupByTeam(pack.riders)
  const leaders = pack.riders.filter(isLeader).slice(0, MAX_PIPS)

  let angle = -Math.PI / 2
  const TAU = Math.PI * 2
  const arcs = segments.map((seg) => {
    const sweep = (seg.count / riderCount) * TAU
    const startAngle = angle
    const endAngle = riderCount === seg.count ? angle + sweep - 0.001 : angle + sweep
    angle = endAngle
    return { ...seg, startAngle, endAngle }
  })

  return (
    <g
      transform={`translate(${x}, ${y})`}
      onClick={(e) => {
        e.stopPropagation()
        onClick?.()
      }}
      onMouseEnter={() => onHover?.(pack)}
      onMouseLeave={() => onHover?.(null)}
      style={{ cursor: 'pointer' }}
    >
      {arcs.map((arc, i) => (
        <path
          key={i}
          d={describeArc(ringRadius, arc.startAngle, arc.endAngle)}
          fill="none"
          stroke={arc.color}
          strokeWidth={thickness}
        />
      ))}

      {radius >= MIN_RADIUS_FOR_COUNT_TEXT && (
        <text
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={Math.min(12, radius * 0.55)}
          fontWeight={600}
          fill="#0f172a"
        >
          {riderCount}
        </text>
      )}

      {leaders.map((leader, i) => {
        const pipAngle = -Math.PI / 2 + (i / Math.max(1, leaders.length)) * TAU
        const pipR = radius + thickness / 2 + PIP_RADIUS + 1
        return (
          <circle
            key={leader.id}
            cx={pipR * Math.cos(pipAngle)}
            cy={pipR * Math.sin(pipAngle)}
            r={PIP_RADIUS}
            fill={teamColor(leader.team)}
            stroke="white"
            strokeWidth={1}
          />
        )
      })}

      {active && (
        <circle r={radius + thickness / 2 + 6} fill="none" stroke="#0f172a" strokeWidth={1} opacity={0.4} />
      )}
    </g>
  )
}

export default memo(PackMarker)
