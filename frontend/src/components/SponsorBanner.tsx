import { Link } from 'react-router-dom'

import { Card } from './primitives'
import { formatMoney } from '../format'
import { color } from '../theme'
import { useAuth } from '../useAuth'

/**
 * The "no sponsor this season" warning (#161). Renders nothing unless the
 * caller's team is missing a sponsor for a running season, which `me`
 * reports as `team.sponsor_missing`. It cannot be dismissed: it goes when the
 * team signs. A warning, not an alarm, so it wears the accent rather than the
 * insolvency banner's red.
 */
export function SponsorBanner() {
  const { me } = useAuth()
  const team = me?.team
  if (!team || !team.sponsor_missing) return null

  return (
    <Card style={{ padding: '14px 18px', borderColor: color.accent, background: color.accentWash }}>
      <div role="status" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: color.accentInk }}>
          No sponsor this season. You are earning nothing from sponsorship.
        </div>
        <div style={{ fontSize: 13, color: color.muted }}>
          {team.guaranteed_weekly
            ? `Signing can guarantee you ${formatMoney(team.guaranteed_weekly)} a week. `
            : null}
          <Link to="/sponsors" style={{ color: color.accentInk, fontWeight: 600 }}>
            Pick an offer
          </Link>
        </div>
      </div>
    </Card>
  )
}
