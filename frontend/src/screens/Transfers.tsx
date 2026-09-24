import { useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { signFreeAgent, type FreeAgent } from '../api'
import { Button, Card, Chip, ChipLabel, LabelBar, PageBody, PageHeading, StatTile } from '../components/primitives'
import { formatMoney } from '../format'
import { riderPath } from '../navigation'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useFreeAgents } from '../useFreeAgents'

type AttrKey = 'climb' | 'sprint' | 'flat' | 'resistance' | 'positioning'

const ATTR_KEYS: { key: AttrKey; label: string }[] = [
  { key: 'climb', label: 'CLM' },
  { key: 'sprint', label: 'SPR' },
  { key: 'flat', label: 'FLT' },
  { key: 'resistance', label: 'RES' },
  { key: 'positioning', label: 'POS' },
]

type SortKey =
  | 'name'
  | 'age'
  | 'signing_fee'
  | 'weekly_salary'
  | 'market_value'
  | AttrKey

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: 'signing_fee', label: 'Signing fee' },
  { key: 'weekly_salary', label: 'Salary' },
  { key: 'market_value', label: 'Value' },
  { key: 'name', label: 'Name' },
  { key: 'age', label: 'Age' },
  { key: 'climb', label: 'Climbing' },
  { key: 'sprint', label: 'Sprinting' },
  { key: 'flat', label: 'Flat' },
  { key: 'resistance', label: 'Resistance' },
  { key: 'positioning', label: 'Positioning' },
]

export function Transfers() {
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

  const { pool, loading, error, refresh } = useFreeAgents()
  const [actionError, setActionError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [filter, setFilter] = useState<'All' | string>('All')
  const [sort, setSort] = useState<SortKey>('signing_fee')

  const specialities = useMemo(() => {
    if (!pool) return []
    return Array.from(new Set(pool.riders.map((r) => r.speciality))).sort()
  }, [pool])

  const visible = useMemo(() => {
    if (!pool) return []
    const list = pool.riders.filter((r) => filter === 'All' || r.speciality === filter)
    return [...list].sort((a, b) => {
      if (sort === 'name') return a.name.localeCompare(b.name)
      if (sort === 'age') return a.age - b.age
      if (sort === 'signing_fee') return a.signing_fee - b.signing_fee
      if (sort === 'weekly_salary') return a.weekly_salary - b.weekly_salary
      if (sort === 'market_value') return a.market_value - b.market_value
      return b[sort] - a[sort]
    })
  }, [pool, filter, sort])

  if (authLoading || loading) return null

  if (!hasTeam) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            You do not manage a team, so the transfer market is closed to you.
          </div>
        </Card>
      </PageBody>
    )
  }

  if (error || !pool) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load the transfer market.</div>
        </Card>
      </PageBody>
    )
  }

  const handleSign = async (agent: FreeAgent) => {
    setPending(true)
    setActionError(null)
    try {
      await signFreeAgent(agent.id)
      refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not sign that rider.')
    } finally {
      setPending(false)
    }
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="MARKET · TRANSFERS"
        title="Transfers"
        titleSize={29}
        subtitle="Free agents sign with a one-off fee. Riders released by claims and teams land here."
        aside={
          <>
            <StatTile label="BALANCE" value={formatMoney(pool.balance)} minWidth={160} />
            <StatTile label="FREE AGENTS" value={String(pool.riders.length)} minWidth={104} />
          </>
        }
      />

      {actionError ? (
        <Card style={{ padding: '12px 16px', borderColor: '#D9534F' }}>
          <div style={{ fontSize: 13, color: '#D9534F' }}>{actionError}</div>
        </Card>
      ) : null}

      <Card style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '14px 16px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <ChipLabel>SPECIALITY</ChipLabel>
          {['All', ...specialities].map((f) => (
            <Chip key={f} active={filter === f} onClick={() => setFilter(f)}>
              {f}
            </Chip>
          ))}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <ChipLabel>SORT</ChipLabel>
          {SORT_OPTIONS.map((o) => (
            <Chip key={o.key} active={sort === o.key} onClick={() => setSort(o.key)}>
              {o.label}
            </Chip>
          ))}
          <span
            style={{
              marginLeft: 'auto',
              fontSize: 12,
              color: color.muted,
              fontFamily: font.mono,
            }}
          >
            {visible.length} of {pool.riders.length} free agents
          </span>
        </div>
      </Card>

      {pool.riders.length === 0 ? (
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            No free agents right now — riders released by claims and teams land here.
          </div>
        </Card>
      ) : null}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(288px, 1fr))',
          gap: 12,
        }}
      >
        {visible.map((agent) => {
          const affordable = agent.signing_fee <= pool.balance
          return (
            <FreeAgentCard
              key={agent.id}
              agent={agent}
              note={affordable ? undefined : "You cannot afford this rider's signing fee."}
              action={
                <Button
                  onClick={() => handleSign(agent)}
                  disabled={!affordable || pending}
                  style={{ opacity: pending || !affordable ? 0.6 : 1 }}
                >
                  Sign
                </Button>
              }
            />
          )
        })}
      </div>
    </PageBody>
  )
}

function FreeAgentCard({
  agent,
  action,
  note,
}: {
  agent: FreeAgent
  action: ReactNode
  note?: string
}) {
  return (
    <Card style={{ padding: '15px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 11,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 14,
            fontWeight: 700,
            fontFamily: font.mono,
            background: color.canvas,
            color: color.ink,
            flex: '0 0 40px',
          }}
        >
          {agent.speciality.slice(0, 2).toUpperCase()}
        </div>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
          <Link
            to={riderPath(agent.id)}
            style={{
              display: 'block',
              fontSize: 14.5,
              fontWeight: 600,
              letterSpacing: '-0.2px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              color: color.ink,
              textDecoration: 'none',
            }}
          >
            {agent.name}
          </Link>
          <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
            {agent.speciality.toUpperCase()} · {agent.age} yrs
          </div>
        </div>
        {action}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {ATTR_KEYS.map(({ key, label }) => (
          <LabelBar key={key} label={label} value={agent[key]} />
        ))}
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
          borderTop: `1px solid ${color.dividerStrong}`,
          paddingTop: 10,
        }}
      >
        <span style={{ fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>
          Fee {formatMoney(agent.signing_fee)}
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
          <span style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
            {formatMoney(agent.weekly_salary)}/wk
          </span>
          <span style={{ fontSize: 10.5, color: color.muted, fontFamily: font.mono }}>
            <span style={{ letterSpacing: '0.4px' }}>VALUE </span>
            {formatMoney(agent.market_value)}
          </span>
        </span>
      </div>

      {note ? (
        <div style={{ fontSize: 12, color: color.negative }}>{note}</div>
      ) : null}
    </Card>
  )
}