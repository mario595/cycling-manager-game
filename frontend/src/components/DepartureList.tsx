import { Link } from 'react-router-dom'

import type { Departure } from '../api'
import { departureText } from '../departures'
import { riderPath } from '../navigation'
import { color, font } from '../theme'

/**
 * One row per departure (#158, #162): the rider's name, linked to their
 * profile while they still exist, with speciality and age beside it because
 * names repeat in this world, then what happened and when. Shared by the
 * dashboard, the roster and the development squad screen so a departure
 * reads the same wherever it appears.
 */
export function DepartureList({ departures }: { departures: Departure[] }) {
  return (
    <div>
      {departures.map((departure) => (
        <div
          key={departure.id}
          style={{
            display: 'flex',
            alignItems: 'baseline',
            flexWrap: 'wrap',
            gap: 6,
            padding: '11px 20px',
            borderTop: `1px solid ${color.dividerStrong}`,
            fontSize: 13.5,
          }}
        >
          {departure.rider.id !== null ? (
            <Link
              to={riderPath(departure.rider.id)}
              style={{ fontWeight: 600, color: color.ink, textDecoration: 'none' }}
            >
              {departure.rider.name}
            </Link>
          ) : (
            <span style={{ fontWeight: 600 }}>{departure.rider.name}</span>
          )}
          <span style={{ fontSize: 11, fontFamily: font.mono, color: color.mutedStrong }}>
            {departure.rider.speciality.toUpperCase()} · {departure.rider.age} yrs
          </span>
          <span style={{ color: color.muted }}>{departureText(departure)}</span>
        </div>
      ))}
    </div>
  )
}
