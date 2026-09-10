import { useMemo, useState } from 'react'

import { Bar, Card, PageBody, PageHeading, StatTile } from '../components/primitives'
import {
  ATTR_KEYS,
  ATTR_LABELS,
  SORT_OPTIONS,
  SPEC_FILTERS,
  SQUAD,
  WAGE_BILL,
  type Rider,
  type SortKey,
  type Speciality,
} from '../placeholderData'
import { barColor, color, font, formColor, riderStatus } from '../theme'

/** Wages read "€480k" / "€2.4M" — parse enough to sort by them. */
function wageValue(wage: string): number {
  const n = parseFloat(wage.replace(/[^\d.]/g, ''))
  return wage.includes('M') ? n * 1000 : n
}

export function Roster() {
  const [filter, setFilter] = useState<'All' | Speciality>('All')
  const [sort, setSort] = useState<SortKey>('ovr')
  const [picked, setPicked] = useState<string | null>(null)

  const riders = useMemo(() => {
    const list = SQUAD.filter((r) => filter === 'All' || r.spec === filter)
    return [...list].sort((a, b) => {
      switch (sort) {
        case 'name':
          return a.name.localeCompare(b.name)
        case 'age':
          return a.age - b.age
        case 'wage':
          return wageValue(b.wage) - wageValue(a.wage)
        default:
          return b[sort] - a[sort]
      }
    })
  }, [filter, sort])

  const selected = picked ? (SQUAD.find((r) => r.id === picked) ?? null) : null

  const avgOverall = Math.round(SQUAD.reduce((a, r) => a + r.ovr, 0) / SQUAD.length)
  const avgAge = (SQUAD.reduce((a, r) => a + r.age, 0) / SQUAD.length).toFixed(1)

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="TEAM · ROSTER"
        title="Squad"
        titleSize={29}
        subtitle="Tap a rider for the full profile. Attributes are the five the race engine reads."
        aside={
          <>
            <StatTile label="SQUAD SIZE" value={String(SQUAD.length)} minWidth={104} />
            <StatTile label="AVG OVERALL" value={String(avgOverall)} minWidth={104} />
            <StatTile label="AVG AGE" value={avgAge} minWidth={104} />
            <StatTile label="WAGE BILL" value={WAGE_BILL} minWidth={104} />
          </>
        }
      />

      <Card style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '14px 16px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <ChipLabel>ROLE</ChipLabel>
          {SPEC_FILTERS.map((f) => (
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
            {riders.length} of {SQUAD.length} riders
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
          {riders.map((rider) => (
            <RiderCard
              key={rider.id}
              rider={rider}
              selected={rider.id === picked}
              onPick={() => setPicked((current) => (current === rider.id ? null : rider.id))}
            />
          ))}
        </div>

        {selected ? <RiderPanel rider={selected} onClose={() => setPicked(null)} /> : null}
      </div>
    </PageBody>
  )
}

function ChipLabel({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontSize: 10.5,
        letterSpacing: '1.2px',
        color: color.mutedStrong,
        fontFamily: font.mono,
        marginRight: 2,
      }}
    >
      {children}
    </span>
  )
}

function Chip({
  children,
  active,
  onClick,
}: {
  children: React.ReactNode
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={{
        padding: '6px 12px',
        borderRadius: 8,
        fontSize: 12.5,
        cursor: 'pointer',
        border: `1px solid ${active ? color.ink : color.borderButton}`,
        background: active ? color.ink : color.surface,
        color: active ? '#FFFFFF' : '#565A61',
        fontWeight: active ? 600 : 400,
      }}
    >
      {children}
    </button>
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
  const status = riderStatus[rider.status]

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
            fontSize: 15,
            fontWeight: 700,
            fontFamily: font.mono,
            background: rider.ovr >= 80 ? color.accent : color.canvas,
            color: color.ink,
            flex: '0 0 40px',
          }}
        >
          {rider.ovr}
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
            {rider.spec.toUpperCase()} · {rider.age} yrs · {rider.role}
          </div>
        </div>
        <div
          style={{
            fontSize: 9.5,
            letterSpacing: '1px',
            fontWeight: 700,
            padding: '3px 6px',
            borderRadius: 5,
            fontFamily: font.mono,
            background: status.bg,
            color: status.fg,
            whiteSpace: 'nowrap',
          }}
        >
          {status.label}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0,1fr))', gap: 7 }}>
        {rider.attrs.map((value, i) => (
          <div key={ATTR_KEYS[i]} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                gap: 2,
              }}
            >
              <span
                style={{
                  fontSize: 9.5,
                  letterSpacing: '0.6px',
                  color: color.mutedStrong,
                  fontFamily: font.mono,
                }}
              >
                {ATTR_KEYS[i]}
              </span>
              <span style={{ fontSize: 11, fontWeight: 600, fontFamily: font.mono }}>{value}</span>
            </div>
            <Bar value={value} fill={barColor(value)} />
          </div>
        ))}
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          borderTop: `1px solid ${color.divider}`,
          paddingTop: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 0 }}>
          <MiniLabel>FRM</MiniLabel>
          <Bar value={rider.form} fill={formColor(rider.form)} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: 1, minWidth: 0 }}>
          <MiniLabel>CND</MiniLabel>
          <Bar value={rider.condition} fill={color.muted} />
        </div>
        <span
          style={{
            fontSize: 11,
            color: color.muted,
            fontFamily: font.mono,
            whiteSpace: 'nowrap',
          }}
        >
          {rider.years} {rider.years === 1 ? 'yr left' : 'yrs left'} · {rider.wage}
        </span>
      </div>
    </button>
  )
}

function MiniLabel({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontSize: 9.5,
        letterSpacing: '0.8px',
        color: color.mutedStrong,
        fontFamily: font.mono,
      }}
    >
      {children}
    </span>
  )
}

function RiderPanel({ rider, onClose }: { rider: Rider; onClose: () => void }) {
  const facts: Array<[string, string]> = [
    ['Contract', `${rider.years} ${rider.years === 1 ? 'yr' : 'yrs'}`],
    ['Wage', rider.wage],
    ['Market value', rider.value],
    ['Form', String(rider.form)],
    ['Condition', String(rider.condition)],
    ['Overall', String(rider.ovr)],
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
            {rider.spec} · {rider.age} yrs · {rider.role}
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
        {rider.attrs.map((value, i) => (
          <div key={ATTR_LABELS[i]} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ width: 88, flex: '0 0 88px', fontSize: 12.5, color: '#565A61' }}>
              {ATTR_LABELS[i]}
            </span>
            <Bar value={value} fill={barColor(value)} height={7} />
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
        ))}
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

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <button
          type="button"
          className="hover-dark"
          style={{
            background: color.ink,
            color: '#FFFFFF',
            border: 'none',
            borderRadius: 9,
            padding: '10px 14px',
            fontSize: 13,
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          Add to next lineup
        </button>
        <div style={{ display: 'flex', gap: 8 }}>
          {['Training', 'Transfer list'].map((label) => (
            <button
              key={label}
              type="button"
              className="hover-light"
              style={{
                flex: 1,
                background: color.canvas,
                color: color.ink,
                border: `1px solid ${color.borderButton}`,
                borderRadius: 9,
                padding: '9px 12px',
                fontSize: 12.5,
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
