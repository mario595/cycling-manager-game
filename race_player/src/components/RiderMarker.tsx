import { memo } from 'react'
import type { Rider } from '../types/race'

interface RiderMarkerProps {
  rider: Rider
  x: number
  y: number
  active?: boolean
  onClick?: () => void
  onHover?: (rider: Rider | null) => void
}

function RiderMarker({ rider, x, y, active, onClick, onHover }: RiderMarkerProps) {
  const color = '#ef4444'

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
      <circle r={active ? 7 : 5} fill={color} stroke="white" strokeWidth={1.5} />
      {active && (
        <circle r={11} fill="none" stroke={color} strokeWidth={1} opacity={0.5} />
      )}
      {rider.drafting && !active && (
        <circle r={9} fill="none" stroke={color} strokeWidth={0.75} opacity={0.4} />
      )}
    </g>
  )
}

export default memo(RiderMarker)
