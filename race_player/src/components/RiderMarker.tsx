import { memo } from 'react'
import type { Rider } from '../types/race'
import { isLeader, teamColor } from '../utils/teamColors'

interface RiderMarkerProps {
  rider: Rider
  x: number
  y: number
  active?: boolean
  onClick?: () => void
  onHover?: (rider: Rider | null) => void
}

const RADIUS_LEADER = 7
const RADIUS_SUPPORT = 5
const RADIUS_LEADER_ACTIVE = 9
const RADIUS_SUPPORT_ACTIVE = 7

function RiderMarker({ rider, x, y, active, onClick, onHover }: RiderMarkerProps) {
  const color = teamColor(rider.team)
  const leader = isLeader(rider)
  const radius = active
    ? leader
      ? RADIUS_LEADER_ACTIVE
      : RADIUS_SUPPORT_ACTIVE
    : leader
      ? RADIUS_LEADER
      : RADIUS_SUPPORT

  return (
    <g
      transform={`translate(${x}, ${y})`}
      onClick={(e) => {
        e.stopPropagation()
        onClick?.()
      }}
      onMouseEnter={() => onHover?.(rider)}
      onMouseLeave={() => onHover?.(null)}
      style={{ cursor: 'pointer' }}
    >
      <circle r={radius} fill={color} stroke="white" strokeWidth={1.5} />
      {leader && <circle r={radius * 0.35} fill="white" />}
      {active && (
        <circle r={radius + 4} fill="none" stroke={color} strokeWidth={1} opacity={0.5} />
      )}
    </g>
  )
}

export default memo(RiderMarker)
