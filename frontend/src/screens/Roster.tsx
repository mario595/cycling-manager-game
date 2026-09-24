import { useMemo, useState } from 'react'

import { listForAuction, releaseRider, type Rider, type SalaryReview } from '../api'
import { Bar, Button, Card, CardHeader, Chip, ChipLabel, LabelBar, PageBody, PageHeading, StatTile } from '../components/primitives'
import { formatMoney } from '../format'
import { barColor, color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useRoster } from '../useRoster'

type AttrKey = 'climb' | 'sprint' | 'flat' | 'resistance' | 'positioning'

const ATTR_KEYS: { key: AttrKey; label: string }[] = [
  { key: 'climb', label: 'CLM' },
  { key: 'sprint', label: 'SPR' },
  { key: 'flat', label: 'FLT' },
  { key: 'resistance', label: 'RES' },
  { key: 'positioning', label: 'POS' },
]

const ATTR_LABELS: { key: AttrKey; label: string }[] = [
  { key: 'climb', label: 'Climbing' },
  { key: 'sprint', label: 'Sprinting' },
  { key: 'flat', label: 'Flat' },
  { key: 'resistance', label: 'Resistance' },
  { key: 'positioning', label: 'Positioning' },
]

type SortKey =
  | 'name'
  | 'age'
  | 'climb'
  | 'sprint'
  | 'flat'
  | 'resistance'
  | 'positioning'
  | 'weekly_salary'
  | 'market_value'

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: 'name', label: 'Name' },
  { key: 'age', label: 'Age' },
  { key: 'climb', label: 'Climbing' },
  { key: 'sprint', label: 'Sprinting' },
  { key: 'flat', label: 'Flat' },
  { key: 'resistance', label: 'Resistance' },
  { key: 'positioning', label: 'Positioning' },
  { key: 'weekly_salary', label: 'Salary' },
  { key: 'market_value', label: 'Value' },
]

export function Roster() {
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

const { riders, squadValue, salaryReview, loading, error, refresh } = useRoster()
  const [filter, setFilter] = useState<'All' | string>('All')
  const [sort, setSort] = useState<SortKey>('name')
  const [picked, setPicked] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const specialities = useMemo(() => {
    if (!riders) return []
    return Array.from(new Set(riders.map((r) => r.speciality))).sort()
  }, [riders])

  const sorted = useMemo(() => {
    if (!riders) return []
    const list = riders.filter((r) => filter === 'All' || r.speciality === filter)
    return [...list].sort((a, b) => {
      if (sort === 'name') return a.name.localeCompare(b.name)
      if (sort === 'age') return a.age - b.age
      return b[sort] - a[sort]
    })
  }, [riders, filter, sort])

  if (authLoading || loading) return null

  if (!hasTeam) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            You do not manage a team, so there is no roster to show here.
          </div>
        </Card>
      </PageBody>
    )
  }

  if (error || !riders) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load the roster.</div>
        </Card>
      </PageBody>
    )
  }

  const selected = picked !== null ? (riders.find((r) => r.id === picked) ?? null) : null

  const handleRelease = async (rider: Rider) => {
    setPending(true)
    setActionError(null)
    try {
      await releaseRider(rider.id)
      setPicked(null)
      refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not release that rider.')
    } finally {
      setPending(false)
    }
  }

  const handleListForAuction = async (rider: Rider) => {
    setPending(true)
    setActionError(null)
    try {
      await listForAuction(rider.id)
      setPicked(null)
      refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not list that rider for auction.')
    } finally {
      setPending(false)
    }
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="TEAM · ROSTER"
        title="Squad"
        titleSize={29}
        subtitle="Tap a rider for the full profile. Attributes are the five the race engine reads."
        aside={
          <>
            <StatTile label="SQUAD SIZE" value={String(riders.length)} minWidth={104} />
            <StatTile label="SQUAD VALUE" value={formatMoney(squadValue ?? 0)} minWidth={140} />
          </>
        }
      />

{actionError ? (
        <Card style={{ padding: '12px 16px', borderColor: '#D9534F' }}>
          <div style={{ fontSize: 13, color: '#D9534F' }}>{actionError}</div>
        </Card>
      ) : null}

      {salaryReview && salaryReview.changes.length > 0 ? (
        <SalaryReviewCard review={salaryReview} />
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
            {sorted.length} of {riders.length} riders
          </span>
        </div>
      </Card>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <div
          style={{
            flex: 1,
            minWidth: 0,
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(288px, 1fr))',
            gap: 12,
          }}
        >
          {sorted.map((rider) => (
            <RiderCard
              key={rider.id}
              rider={rider}
              selected={rider.id === picked}
              onPick={() => setPicked((current) => (current === rider.id ? null : rider.id))}
            />
          ))}
        </div>

        {selected ? (
          <RiderPanel
            rider={selected}
            pending={pending}
            onClose={() => setPicked(null)}
            onRelease={() => handleRelease(selected)}
            onListForAuction={() => handleListForAuction(selected)}
          />
        ) : null}
      </div>
    </PageBody>
  )
}

function RiderCard({
  rider,
  selected,
  onPick,
}: {
  rider: Rider
  selected: boolean
  onPick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      className={selected ? undefined : 'hover-card'}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        padding: '15px 16px',
        borderRadius: 14,
        cursor: 'pointer',
        background: color.surface,
        textAlign: 'left',
        border: `1px solid ${selected ? color.accent : color.border}`,
        boxShadow: selected ? '0 0 0 3px rgba(235,167,107,.22)' : 'none',
        transition: 'border-color .15s, box-shadow .15s',
      }}
    >
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
          {rider.speciality.slice(0, 2).toUpperCase()}
        </div>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
          <div
            style={{
              fontSize: 14.5,
              fontWeight: 600,
              letterSpacing: '-0.2px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {rider.name}
          </div>
          <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
            {rider.speciality.toUpperCase()} · {rider.age} yrs
          </div>
        </div>
      </div>

      {/* rider[key] and rider.freshness are the 0-10 display scale (see
          riders/display.py); LabelBar prints the value and scales it to
          0-100 for the bar. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {ATTR_KEYS.map(({ key, label }) => (
          <LabelBar key={key} label={label} value={rider[key]} />
        ))}
        <div style={{ marginTop: 3, paddingTop: 7, borderTop: `1px solid ${color.divider}` }}>
          <LabelBar label="FIT" value={rider.freshness} />
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
          borderTop: `1px solid ${color.divider}`,
          paddingTop: 10,
        }}
      >
        <span style={{ fontSize: 11, color: color.muted, fontFamily: font.mono }}>
          {rider.height_cm} cm · {rider.weight_kg} kg
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
          <span style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
            {formatMoney(rider.weekly_salary)}/wk
          </span>
          <span style={{ fontSize: 10.5, color: color.muted, fontFamily: font.mono }}>
            <span style={{ letterSpacing: '0.4px' }}>VALUE </span>
            {formatMoney(rider.market_value)}
          </span>
        </span>
      </div>
    </button>
  )
}

function RiderPanel({
  rider,
  pending,
  onClose,
  onRelease,
  onListForAuction,
}: {
  rider: Rider
  pending: boolean
  onClose: () => void
  onRelease: () => void
  onListForAuction: () => void
}) {
  const facts: Array<[string, string]> = [
    ['Age', `${rider.age} yrs`],
    ['Height', `${rider.height_cm} cm`],
    ['Weight', `${rider.weight_kg} kg`],
    ['Speciality', rider.speciality],
    ['Salary', `${formatMoney(rider.weekly_salary)}/wk`],
    ['Value', formatMoney(rider.market_value)],
  ]

  return (
    <div
      style={{
        position: 'sticky',
        top: 22,
        alignSelf: 'start',
        width: 286,
        flex: '0 0 286px',
        background: color.surface,
        border: `1px solid ${color.border}`,
        borderRadius: 14,
        padding: '18px 20px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 14 }}>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
          <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: '-0.4px' }}>{rider.name}</div>
          <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
            {rider.speciality} · {rider.age} yrs
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={`Close ${rider.name}`}
          className="hover-light"
          style={{
            background: color.canvas,
            border: `1px solid ${color.border}`,
            borderRadius: 8,
            width: 28,
            height: 28,
            cursor: 'pointer',
            color: color.mutedStrong,
            fontSize: 14,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 9, marginBottom: 16 }}>
        {ATTR_LABELS.map(({ key, label }) => {
          const value = rider[key]
          return (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ width: 88, flex: '0 0 88px', fontSize: 12.5, color: '#565A61' }}>
                {label}
              </span>
              <Bar value={value * 10} fill={barColor(value * 10)} height={7} />
              <span
                style={{
                  width: 26,
                  textAlign: 'right',
                  fontSize: 12,
                  fontWeight: 600,
                  fontFamily: font.mono,
                }}
              >
                {value}
              </span>
            </div>
          )
        })}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            marginTop: 1,
            paddingTop: 11,
            borderTop: `1px solid ${color.divider}`,
          }}
        >
          <span style={{ width: 88, flex: '0 0 88px', fontSize: 12.5, color: '#565A61' }}>
            Freshness
          </span>
          <Bar value={rider.freshness * 10} fill={barColor(rider.freshness * 10)} height={7} />
          <span
            style={{
              width: 26,
              textAlign: 'right',
              fontSize: 12,
              fontWeight: 600,
              fontFamily: font.mono,
            }}
          >
            {rider.freshness}
          </span>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, minmax(0,1fr))',
          gap: 9,
          marginBottom: 16,
        }}
      >
        {facts.map(([k, v]) => (
          <div
            key={k}
            style={{
              background: color.canvas,
              borderRadius: 9,
              padding: '9px 11px',
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
            }}
          >
            <span
              style={{
                fontSize: 10,
                letterSpacing: '0.8px',
                color: color.mutedStrong,
                fontFamily: font.mono,
              }}
            >
              {k}
            </span>
            <span style={{ fontSize: 14, fontWeight: 600, fontFamily: font.mono }}>{v}</span>
          </div>
        ))}
      </div>

      {/* Releasing sends the rider to the free agent pool. The cost is
          severance unless the claim cooldown still shields them — the
          server has the final say; this is the figure it will charge.
          Listing for auction keeps the rider on the roster — racing,
          training, earning their wage — until another manager wins it or
          the auction closes unsold. */}
      <div
        style={{
          borderTop: `1px solid ${color.divider}`,
          paddingTop: 14,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 10,
          }}
        >
          <span style={{ fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>
            Release {formatMoney(rider.release_cost ?? 0)}
          </span>
          <Button onClick={onRelease} disabled={pending} style={{ opacity: pending ? 0.6 : 1 }}>
            Release
          </Button>
        </div>
        {rider.release_cost === 0 ? (
          <div style={{ fontSize: 11.5, color: color.muted }}>
            Free while the claim cooldown shields them.
          </div>
        ) : null}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 10,
          }}
        >
          <span style={{ fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>
            Auction this rider
          </span>
          <Button onClick={onListForAuction} disabled={pending} style={{ opacity: pending ? 0.6 : 1 }}>
            List for auction
          </Button>
        </div>
      </div>
    </div>
  )
}

function signedMoney(amount: number): string {
  if (amount > 0) return `+${formatMoney(amount)}`
  return formatMoney(amount)
}

function SalaryReviewCard({ review }: { review: SalaryReview }) {
  const changes = [...review.changes].sort(
    (a, b) => Math.abs(b.to_value - b.from_value) - Math.abs(a.to_value - a.from_value),
  )
  const net = review.payroll_after - review.payroll_before

  return (
    <Card>
      <CardHeader
        title="Season-end salary review"
        action={
          <div style={{ fontSize: 11, letterSpacing: '0.8px', color: color.mutedStrong, fontFamily: font.mono }}>
            SEASON {review.season_number}
          </div>
        }
      />
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '13px 20px',
          borderTop: `1px solid ${color.dividerStrong}`,
        }}
      >
        <div style={{ flex: 1, minWidth: 0, fontSize: 13.5, fontWeight: 600 }}>Weekly wage bill</div>
        <div style={{ fontSize: 13, fontFamily: font.mono, whiteSpace: 'nowrap' }}>
          <span style={{ color: color.muted }}>{formatMoney(review.payroll_before)}</span>
          <span style={{ color: color.accentInk, padding: '0 5px' }}>→</span>
          <span style={{ fontWeight: 600 }}>{formatMoney(review.payroll_after)}</span>
          <span
            style={{
              color: net > 0 ? color.positive : net < 0 ? color.negative : color.muted,
              paddingLeft: 8,
            }}
          >
            {signedMoney(net)}
          </span>
        </div>
      </div>
      {changes.map((change) => {
        const delta = change.to_value - change.from_value
        return (
          <div
            key={change.rider_id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '11px 20px',
              borderTop: `1px solid ${color.dividerStrong}`,
            }}
          >
            <div
              style={{
                flex: 1,
                minWidth: 0,
                fontSize: 14,
                fontWeight: 600,
                letterSpacing: '-0.2px',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {change.rider_name}
            </div>
            <div style={{ fontSize: 13, fontFamily: font.mono, whiteSpace: 'nowrap' }}>
              <span style={{ color: color.muted }}>{formatMoney(change.from_value)}</span>
              <span style={{ color: color.accentInk, padding: '0 5px' }}>→</span>
              <span style={{ fontWeight: 600 }}>{formatMoney(change.to_value)}</span>
              <span
                style={{
                  color: delta > 0 ? color.positive : delta < 0 ? color.negative : color.muted,
                  paddingLeft: 8,
                }}
              >
                {signedMoney(delta)}
              </span>
            </div>
          </div>
        )
      })}
    </Card>
  )
}
