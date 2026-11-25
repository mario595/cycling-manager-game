import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import type { CalendarRace, RaceDetail, RaceDetailStageRace, RacePayoutEntry, Squad, SquadRider } from '../api'
import { CourseProfile } from '../components/CourseProfile'
import { HiddenResults } from '../components/RaceResults'
import { Button, Card, CardHeader, LabelBar, PageBody, PageHeading, StatTile } from '../components/primitives'
import { racePath, replayPath } from '../navigation'
import { raceStatusLabel, raceStatusTone } from '../raceStatus'
import { color, font } from '../theme'
import { useRaceDetail } from '../useRaceDetail'
import { useSquad } from '../useSquad'
import { formatDate, formatMoney } from '../format'

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
  const id = Number(raceId)

  const navigate = useNavigate()
  const { race, loading, error } = useRaceDetail(id)
  const { squad, save, saving, saveError } = useSquad(id)

  if (loading) return null

  if (error || !race) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load this race.</div>
        </Card>
      </PageBody>
    )
  }

  const body = raceBody(race, {
    onWatch: () => navigate(replayPath(id)),
    squad,
    save,
    saving,
    saveError,
  })

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow={raceStatusLabel(race.status as CalendarRace['status']).toUpperCase()}
        title={race.name}
        titleSize={29}
        subtitle={metaLine(race)}
      />

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <StatTile label="DISTANCE" value={`${race.distance_km.toFixed(1)} km`} minWidth={104} />
        <StatTile
          label="DATE"
          value={race.starts_at ? formatDate(race.starts_at) : '—'}
          minWidth={104}
        />
        <StatTile label="STATUS" value={raceStatusLabel(race.status as CalendarRace['status'])} minWidth={104} />
      </div>

      {race.stage_race ? <StageStrip stageRace={race.stage_race} currentRaceId={race.id} /> : null}

      {body}
    </PageBody>
  )
}

function StageStrip({ stageRace, currentRaceId }: { stageRace: RaceDetailStageRace; currentRaceId: number }) {
  return (
    <Card style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 12.5, fontWeight: 600, color: color.mutedStrong }}>
        Stage {stageRace.stage_number} of {stageRace.stage_count} — {stageRace.name}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {stageRace.stages.map((stage) => {
          const isCurrent = stage.id === currentRaceId
          return (
            <Link
              key={stage.id}
              to={racePath(stage.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 10px',
                borderRadius: 8,
                fontSize: 12,
                fontFamily: font.mono,
                textDecoration: 'none',
                color: isCurrent ? '#FFFFFF' : color.ink,
                background: isCurrent ? color.ink : color.canvas,
                border: `1px solid ${isCurrent ? color.ink : color.border}`,
              }}
            >
              <span>Stage {stage.stage_number}</span>
              <span style={{ opacity: 0.7, color: isCurrent ? '#FFFFFF' : raceStatusTone(stage.status as CalendarRace['status']) }}>
                {raceStatusLabel(stage.status as CalendarRace['status'])}
              </span>
            </Link>
          )
        })}
      </div>
    </Card>
  )
}

function metaLine(race: RaceDetail): string {
  const date = race.starts_at ? formatDate(race.starts_at) : 'unscheduled'
  return `${date} · ${race.distance_km.toFixed(1)} km`
}

function raceBody(
  race: RaceDetail,
  state: {
    onWatch: () => void
    squad: Squad | null
    save: (riderIds: number[], leaderId: number) => Promise<void>
    saving: boolean
    saveError: string | null
  },
) {
  if (race.status === 'finished') {
    return (
      <>
        <CourseProfile course={race.course} markers={race.markers} />
        <Card style={{ padding: '16px 18px', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {race.has_replay ? (
            <>
              <Button variant="primary" onClick={state.onWatch}>
                Watch race
              </Button>
              <span style={{ fontSize: 12.5, color: color.muted }}>
                See how it unfolded, tick by tick.
              </span>
            </>
          ) : (
            <span style={{ fontSize: 13.5, color: color.muted }}>No replay is available for this race.</span>
          )}
        </Card>
        <HiddenResults race={race} />
      </>
    )
  }
  if (race.status === 'failed') {
    return <MessageCard text="This race did not run." />
  }
  if (race.status === 'running') {
    return <MessageCard text="This race is being simulated." />
  }
  return (
    <>
      <CourseProfile course={race.course} markers={race.markers} />
      <PayoutTable title={race.stage_race ? 'Stage prize list' : 'Prize list'} payout={race.payout} />
      {race.stage_race ? <PayoutTable title="General classification" payout={race.gc_payout} /> : null}
      {state.squad ? (
        <SquadPanel
          squad={state.squad}
          onSave={state.save}
          saving={state.saving}
          saveError={state.saveError}
        />
      ) : null}
    </>
  )
}

function MessageCard({ text }: { text: string }) {
  return (
    <Card style={{ padding: '18px 20px' }}>
      <div style={{ fontSize: 13.5, color: color.muted }}>{text}</div>
    </Card>
  )
}

function PayoutTable({ title, payout }: { title: string; payout: RacePayoutEntry[] }) {
  return (
    <Card>
      <CardHeader title={title} />
      <div>
        {payout.map((entry) => (
          <div
            key={entry.position}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '12px 20px',
              borderBottom: `1px solid ${color.divider}`,
            }}
          >
            <div style={{ width: 32, fontFamily: font.mono, fontSize: 13, color: color.mutedStrong }}>
              {entry.position}
            </div>
            <div style={{ flex: 1, fontSize: 13.5, color: color.muted }}>{entry.points} points</div>
            <div style={{ fontFamily: font.mono, fontSize: 14, fontWeight: 600, whiteSpace: 'nowrap' }}>
              {formatMoney(entry.prize)}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
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

      {squad.stage_race ? <SquadStageRaceNote stageRace={squad.stage_race} /> : null}

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

function SquadStageRaceNote({ stageRace }: { stageRace: NonNullable<Squad['stage_race']> }) {
  const text =
    stageRace.stage_number === 1
      ? `This squad and leader ride every stage of ${stageRace.name}.`
      : "Chosen at stage 1 — riders who didn't finish an earlier stage are out."
  return (
    <div style={{ fontSize: 12, color: color.mutedStrong, background: color.canvas, borderRadius: 8, padding: '8px 10px' }}>
      {text}
    </div>
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
        {ATTRS.map(({ key, label }) => (
          // rider[key] and rider.freshness are the 0-10 display scale (see
          // riders/display.py); LabelBar prints that value and scales it to
          // 0-100 inside the bar.
          <LabelBar key={key} label={label.slice(0, 3).toUpperCase()} value={rider[key] as number} />
        ))}

        {/* freshness: a status marker rather than an engine attribute —
            clipped apart so it reads as a separate meter. */}
        <div
          style={{
            marginLeft: 4,
            paddingLeft: 9,
            borderLeft: `1px solid ${color.border}`,
          }}
        >
          <LabelBar label="FIT" value={rider.freshness} />
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