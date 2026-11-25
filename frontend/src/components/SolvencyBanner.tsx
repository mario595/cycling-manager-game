import { Card } from './primitives'
import { formatDate, formatMoney } from '../format'
import { color } from '../theme'
import { useSolvency } from '../useSolvency'

const LEVERS =
  'You can sell riders on the Roster, fire your trainer, close your development squad, or sign a sponsor.'

/**
 * The insolvency warning (#27). Renders nothing for a solvent team or while
 * the standing is loading. Three states, told apart by the live shortfall:
 * still owing (with a deadline, or a payday count when the weeks it falls in
 * are not declared yet), and recovering (the weekly gap is closed but the
 * embargo stays until the balance is back to zero).
 */
export function SolvencyBanner() {
  const { solvency } = useSolvency()
  if (!solvency || !solvency.insolvent) return null

  const owing = solvency.shortfall > 0
  const when = solvency.deadline
    ? `by ${formatDate(solvency.deadline)}`
    : `within ${solvency.paydays_left} ${solvency.paydays_left === 1 ? 'payday' : 'paydays'}`

  return (
    <Card style={{ padding: '14px 18px', borderColor: color.negative }}>
      <div role="alert" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {owing ? (
          <>
            <div style={{ fontSize: 14, fontWeight: 600, color: color.negative }}>
              Your team is insolvent. Cut {formatMoney(solvency.shortfall)} of weekly spending {when} or
              you will lose the team.
            </div>
            <div style={{ fontSize: 13, color: color.muted }}>
              Cut so far {formatMoney(solvency.cut_so_far)} of {formatMoney(solvency.target)}.{' '}
              {LEVERS}
            </div>
          </>
        ) : (
          <div style={{ fontSize: 14, fontWeight: 600, color: color.negative }}>
            Your team is insolvent but recovering. Spending is blocked until your balance is back to
            zero or above.
          </div>
        )}
      </div>
    </Card>
  )
}
