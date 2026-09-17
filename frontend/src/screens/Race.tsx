import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'

import type { Squad, SquadRider } from '../api'
import { Bar, Button, Card, PageBody, PageHeading, StatTile } from '../components/primitives'
import { raceStatusLabel } from '../raceStatus'
import { barColor, color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useSquad } from '../useSquad'

const SQUAD_SIZE = 4

const ATTRS: { key: keyof SquadRider & string; label: string }[] = [
  { key: 'climb', label: 'Climb' },
  { key: 'sprint', label: 'Sprint' },
  { key: 'flat', label: 'Flat' },
  { key: 'resistance', label: 'Resistance' },
  { key: 'positioning', label: 'Positioning' },
]

export function Race() {
  const { raceId } = useParams<{ raceId: string }>()
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

  const { squad, loading, error, save, saving, saveError } = useSquad(Number(raceId))

  if (authLoading || loading) return null

  if (!hasTeam) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            You do not manage a team, so there is no squad for you to pick here.
          </div>
        </Card>
      </PageBody>
    )
  }

  if (error || !squad) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load this race.</div>
        </Card>
      </PageBody>
    )
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow={raceStatusLabel(squad.race_status).toUpperCase()}
        title={squad.race_name}
        titleSize={29}
        subtitle={metaLine(squad)}
      />

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <StatTile label="DISTANCE" value={`${squad.distance_km.toFixed(1)} km`} minWidth={104} />
        <StatTile
          label="DATE"
          value={squad.starts_at ? new Date(squad.starts_at).toLocaleDateString() : '—'}
          minWidth={104}
        />
        <StatTile label="STATUS" value={raceStatusLabel(squad.race_status)} minWidth={104} />
      </div>

      <SquadPanel squad={squad} onSave={save} saving={saving} saveError={saveError} />
    </PageBody>
  )
}

function metaLine(squad: Squad): string {
  const date = squad.starts_at ? new Date(squad.starts_at).toLocaleDateString() : 'unscheduled'
  return `${date} · ${squad.distance_km.toFixed(1)} km · ${squad.team_name}`
}

function SquadPanel({
  squad,
  onSave,
  saving,
  saveError,
}: {
  squad: Squad
  onSave: (riderIds: number[], leaderId: number) => Promise<void>
  saving: boolean
  saveError: string | null
}) {
  const [selected, setSelected] = useState<number[]>(
    () => squad.candidates.filter((c) => c.selected).map((c) => c.id),
  )
  const [leaderId, setLeaderId] = useState<number | null>(
    () => squad.candidates.find((c) => c.is_leader)?.id ?? null,
  )

  const isValid = selected.length === SQUAD_SIZE && leaderId !== null && selected.includes(leaderId)

  const toggle = (riderId: number) => {
    if (!squad.editable) return
    setSelected((current) => {
      if (current.includes(riderId)) {
        const next = current.filter((id) => id !== riderId)
        if (leaderId === riderId) {
          setLeaderId(next[0] ?? null)
        }
        return next
      }
      if (current.length >= SQUAD_SIZE) return current
      return [...current, riderId]
    })
  }

  const makeLeader = (riderId: number) => {
    if (!squad.editable || !selected.includes(riderId)) return
    setLeaderId(riderId)
  }

  const leaderName = useMemo(
    () => squad.candidates.find((c) => c.id === leaderId)?.name ?? 'None picked',
    [squad.candidates, leaderId],
  )

  return (
    <Card style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.2px' }}>
          {squad.editable ? 'Select squad' : 'Squad'}
        </div>
        {squad.editable ? (
          <div style={{ fontSize: 11.5, fontWeight: 600, color: color.mutedStrong, fontFamily: font.mono }}>
            {selected.length}/{SQUAD_SIZE} selected
          </div>
        ) : null}
      </div>

      {squad.editable ? (
        <div style={{ background: color.canvas, borderRadius: 10, padding: '10px 12px' }}>
          <div style={{ fontSize: 10, letterSpacing: '0.9px', color: color.mutedStrong, fontFamily: font.mono }}>
            LEADER
          </div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{leaderName}</div>
        </div>
      ) : null}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {squad.candidates.map((rider) => (
          <RiderRow
            key={rider.id}
            rider={rider}
            isSelected={selected.includes(rider.id)}
            isLeader={leaderId === rider.id}
            editable={squad.editable}
            onToggle={() => toggle(rider.id)}
            onMakeLeader={() => makeLeader(rider.id)}
          />
        ))}
      </div>

      {squad.editable ? (
        <>
          <Button
            variant="primary"
            onClick={() => leaderId !== null && onSave(selected, leaderId)}
            style={{
              width: '100%',
              opacity: isValid && !saving ? 1 : 0.5,
              cursor: isValid && !saving ? 'pointer' : 'not-allowed',
            }}
          >
            {saving
              ? 'Saving…'
              : isValid
                ? 'Confirm squad'
                : `Select ${Math.max(0, SQUAD_SIZE - selected.length)} more`}
          </Button>
          {saveError ? (
            <div style={{ fontSize: 12.5, color: color.negative }}>{saveError}</div>
          ) : null}
        </>
      ) : null}
    </Card>
  )
}

function RiderRow({
  rider,
  isSelected,
  isLeader,
  editable,
  onToggle,
  onMakeLeader,
}: {
  rider: SquadRider
  isSelected: boolean
  isLeader: boolean
  editable: boolean
  onToggle: () => void
  onMakeLeader: () => void
}) {
  return (
    <div
      onClick={editable ? onToggle : undefined}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 11,
        padding: '11px 14px',
        borderRadius: 11,
        cursor: editable ? 'pointer' : 'default',
        background: isSelected ? color.accentWash : color.surface,
        border: `1px solid ${isLeader ? color.accent : isSelected ? '#F4E2D3' : color.border}`,
      }}
    >
      {editable ? (
        <div
          style={{
            width: 20,
            height: 20,
            flex: '0 0 20px',
            borderRadius: 6,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 11,
            fontWeight: 700,
            color: color.ink,
            background: isSelected ? color.accent : color.canvas,
            border: `1px solid ${isSelected ? color.accent : color.borderButton}`,
          }}
        >
          {isSelected ? '✓' : ''}
        </div>
      ) : null}

      <div style={{ flex: '0 0 130px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
        <div style={{ fontSize: 13.5, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {rider.name}
        </div>
        <div style={{ fontSize: 10.5, color: color.mutedStrong, fontFamily: font.mono }}>
          {rider.speciality.toUpperCase()}
        </div>
      </div>

      <div style={{ flex: 1, minWidth: 0, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {ATTRS.map(({ key, label }) => {
          // rider[key] is the 0-10 display scale (see riders/display.py);
          // Bar/barColor expect 0-100, so scale up for the bar only — the
          // printed number stays 0-10.
          const value = rider[key] as number
          return (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 90 }}>
              <span style={{ fontSize: 9.5, color: color.muted, fontFamily: font.mono, width: 18 }}>
                {label.slice(0, 3).toUpperCase()}
              </span>
              <Bar value={value * 10} fill={barColor(value * 10)} />
            </div>
          )
        })}

        {/* freshness: the same 0-10 display scale as the attributes, but a
            status marker rather than an engine attribute — clipped apart so
            it reads as a separate meter. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 90, marginLeft: 4, paddingLeft: 9, borderLeft: `1px solid ${color.border}` }}>
          <span style={{ fontSize: 9.5, color: color.mutedStrong, fontFamily: font.mono, width: 18 }}>
            FIT
          </span>
          <Bar value={rider.freshness * 10} fill={barColor(rider.freshness * 10)} />
        </div>
      </div>

      {editable && isSelected ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onMakeLeader()
          }}
          style={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            fontSize: 13,
            padding: '2px 4px',
            color: isLeader ? color.accent : '#C9CDD4',
          }}
        >
          ★
        </button>
      ) : isLeader ? (
        <span
          style={{
            fontSize: 9.5,
            letterSpacing: '1px',
            fontWeight: 700,
            padding: '3px 6px',
            borderRadius: 5,
            fontFamily: font.mono,
            background: color.ink,
            color: '#FFFFFF',
          }}
        >
          LEADER
        </span>
      ) : null}
    </div>
  )
}
