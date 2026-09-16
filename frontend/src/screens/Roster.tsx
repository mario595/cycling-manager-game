import { useMemo, useState } from 'react'

import type { Rider } from '../api'
import { Bar, Card, PageBody, PageHeading, StatTile } from '../components/primitives'
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

type SortKey = 'name' | 'age' | 'climb' | 'sprint' | 'flat' | 'resistance' | 'positioning'

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: 'name', label: 'Name' },
  { key: 'age', label: 'Age' },
  { key: 'climb', label: 'Climbing' },
  { key: 'sprint', label: 'Sprinting' },
  { key: 'flat', label: 'Flat' },
  { key: 'resistance', label: 'Resistance' },
  { key: 'positioning', label: 'Positioning' },
]

export function Roster() {
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

  const { riders, loading, error } = useRoster()
  const [filter, setFilter] = useState<'All' | string>('All')
  const [sort, setSort] = useState<SortKey>('name')
  const [picked, setPicked] = useState<number | null>(null)

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

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="TEAM · ROSTER"
        title="Squad"
        titleSize={29}
        subtitle="Tap a rider for the full profile. Attributes are the five the race engine reads."
        aside={<StatTile label="SQUAD SIZE" value={String(riders.length)} minWidth={104} />}
      />

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
            {rider.speciality.toUpperCase()} · {rider.age} yrs · {rider.role}
          </div>
        </div>
      </div>

      {/* rider[key] is the 0-10 display scale (riders/display.py); Bar/
          barColor expect 0-100, so scale for the bar only — see
          specs/rider-attributes-plan.md, Design decisions, item 12. */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0,1fr))', gap: 7 }}>
        {ATTR_KEYS.map(({ key, label }) => {
          const value = rider[key]
          return (
            <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
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
                  {label}
                </span>
                <span style={{ fontSize: 11, fontWeight: 600, fontFamily: font.mono }}>{value}</span>
              </div>
              <Bar value={value * 10} fill={barColor(value * 10)} />
            </div>
          )
        })}
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
        <span style={{ fontSize: 11, color: color.muted, fontFamily: font.mono }}>
          {rider.height_cm} cm · {rider.weight_kg} kg
        </span>
      </div>
    </button>
  )
}

function RiderPanel({ rider, onClose }: { rider: Rider; onClose: () => void }) {
  const facts: Array<[string, string]> = [
    ['Age', `${rider.age} yrs`],
    ['Height', `${rider.height_cm} cm`],
    ['Weight', `${rider.weight_kg} kg`],
    ['Speciality', rider.speciality],
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
            {rider.speciality} · {rider.age} yrs · {rider.role}
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
    </div>
  )
}
