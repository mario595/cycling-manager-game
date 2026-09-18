import { type LedgerEntry } from '../api'
import { Card, CardHeader, PageBody, PageHeading, StatTile } from '../components/primitives'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useFinances } from '../useFinances'

/** Abstract whole-number "credits" — see specs/team-finances-ledger.md.
 * Thousands-separated, never decimals, no currency symbol. */
function formatCredits(amount: number): string {
  return amount.toLocaleString('en-US')
}

/** `balance_after` is a whole number too — same formatting as amounts. */
function formatDate(occurredAt: string | null): string {
  return occurredAt ? new Date(occurredAt).toLocaleDateString() : '—'
}

const KIND_LABELS: Record<LedgerEntry['kind'], string> = {
  starting_balance: 'Starting balance',
  wages: 'Weekly wages',
  takeover: 'Team takeover',
}

export function Finances() {
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

  const { finances, loading, error } = useFinances()

  if (authLoading || loading) return null

  if (!hasTeam) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            You do not manage a team, so there are no finances to show here.
          </div>
        </Card>
      </PageBody>
    )
  }

  if (error || !finances) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load finances.</div>
        </Card>
      </PageBody>
    )
  }

  const negative = finances.balance < 0

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="TEAM · FINANCES"
        title="Finances"
        titleSize={29}
        subtitle="Everything that has touched your team's account, newest first."
        aside={
          <StatTile
            label="BALANCE"
            value={formatCredits(finances.balance)}
            suffix=" credits"
            minWidth={160}
            dark={false}
          />
        }
      />

      {negative ? (
        <Card style={{ padding: '12px 16px', borderColor: color.negative }}>
          <div style={{ fontSize: 13, color: color.negative }}>
            Your balance is negative. Wages are still paid in full — nothing is blocked yet.
          </div>
        </Card>
      ) : null}

      <Card>
        <CardHeader title="History" />
        {finances.entries.length === 0 ? (
          <div style={{ padding: '18px 20px', fontSize: 13.5, color: color.muted }}>
            No transactions yet.
          </div>
        ) : (
          finances.entries.map((entry) => (
            <div
              key={`${entry.kind}-${entry.occurred_at}-${entry.amount}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '12px 20px',
                borderTop: `1px solid ${color.dividerStrong}`,
              }}
            >
              <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
                <div
                  style={{
                    fontSize: 14,
                    fontWeight: 600,
                    letterSpacing: '-0.2px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {entry.description || KIND_LABELS[entry.kind]}
                </div>
                <div style={{ fontSize: 11.5, color: color.mutedStrong, fontFamily: font.mono }}>
                  {KIND_LABELS[entry.kind].toUpperCase()} · {formatDate(entry.occurred_at)}
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
                <div
                  style={{
                    fontSize: 14,
                    fontWeight: 600,
                    fontFamily: font.mono,
                    color: entry.amount < 0 ? color.negative : color.positive,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {entry.amount < 0 ? '−' : '+'}
                  {formatCredits(Math.abs(entry.amount))}
                </div>
                <div style={{ fontSize: 11.5, color: color.mutedStrong, fontFamily: font.mono, whiteSpace: 'nowrap' }}>
                  after: {formatCredits(entry.balance_after)}
                </div>
              </div>
            </div>
          ))
        )}
      </Card>
    </PageBody>
  )
}