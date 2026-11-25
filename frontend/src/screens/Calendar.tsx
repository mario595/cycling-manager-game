import { Link } from 'react-router-dom'

import type { Calendar as CalendarData, CalendarRace, CalendarWeek } from '../api'
import { Card, PageBody, PageHeading, StatTile } from '../components/primitives'
import { racePath } from '../navigation'
import { raceStatusLabel, raceStatusTone } from '../raceStatus'
import { formatMonth, formatShortDate, formatWeekday } from '../format'
import { calendarAccent, color, font } from '../theme'
import { useCalendar } from '../useCalendar'

export function Calendar() {
  const { calendar, loading, error } = useCalendar()

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="RACING"
        title="Calendar"
        titleSize={29}
        subtitle={subtitle(calendar)}
        aside={calendar && calendar.state === 'in_season' ? <HeaderStats calendar={calendar} /> : undefined}
      />

      {loading ? null : error ? (
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load the calendar.</div>
        </Card>
      ) : calendar && calendar.state === 'in_season' ? (
        <SeasonCard calendar={calendar} />
      ) : (
        <EmptyState calendar={calendar} />
      )}
    </PageBody>
  )
}

function subtitle(calendar: CalendarData | null): string {
  if (!calendar || calendar.state !== 'in_season' || calendar.current_week === null) {
    return 'Every race the season has planned, from week one.'
  }
  return `Twelve race weeks per season. You are in week ${calendar.current_week}.`
}

function HeaderStats({ calendar }: { calendar: CalendarData }) {
  const races = calendar.weeks.flatMap((w) => w.races)
  const ridden = races.filter((r) => r.status === 'finished' || r.status === 'failed').length

  return (
    <>
      <StatTile label="SEASON WEEK" value={`${calendar.current_week}/${calendar.weeks.length}`} minWidth={104} />
      <StatTile label="RACES RIDDEN" value={`${ridden}/${races.length}`} minWidth={104} />
    </>
  )
}

function EmptyState({ calendar }: { calendar: CalendarData | null }) {
  const message =
    calendar?.state === 'off_season'
      ? `Season ${calendar.season} has finished. No races until the next season is declared.`
      : 'No season has been declared yet.'

  return (
    <Card
      style={{
        padding: '26px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        borderStyle: 'dashed',
        borderColor: '#D6DAE0',
        background: 'transparent',
      }}
    >
      <div style={{ fontSize: 13.5, color: color.muted }}>{message}</div>
    </Card>
  )
}

function SeasonCard({ calendar }: { calendar: CalendarData }) {
  return (
    <div
      style={{
        background: color.surface,
        borderRadius: 16,
        overflow: 'hidden',
        border: `1px solid ${calendarAccent.border}`,
        boxShadow: '0 1px 0 ' + calendarAccent.border + ', 0 10px 26px rgba(122,69,32,0.07)',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '15px 18px',
          borderBottom: `1px solid ${color.dividerStrong}`,
          background: calendarAccent.headerWash,
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 12 }}>
          <div style={{ fontSize: 19, fontWeight: 700, letterSpacing: '-0.5px' }}>
            SEASON {calendar.season}
          </div>
          <div style={{ fontSize: 10.5, letterSpacing: '1.3px', color: color.muted, fontFamily: font.mono }}>
            12 RACE WEEKS + 1 OFF
          </div>
          <span
            style={{
              fontSize: 9.5,
              letterSpacing: '1.3px',
              fontWeight: 700,
              padding: '3px 8px',
              borderRadius: 6,
              fontFamily: font.mono,
              background: calendarAccent.railWash,
              color: calendarAccent.ink,
            }}
          >
            IN PROGRESS
          </span>
        </div>
        <WeekTicks calendar={calendar} />
      </div>

      {calendar.weeks.map((week, i) => (
        <WeekRow key={week.number} week={week} isCurrent={week.number === calendar.current_week} isFirst={i === 0} />
      ))}

      <OffSeasonRow />
    </div>
  )
}

function WeekTicks({ calendar }: { calendar: CalendarData }) {
  return (
    <div style={{ display: 'flex', gap: 3, alignItems: 'flex-end' }}>
      {calendar.weeks.map((week) => {
        const isCur = week.number === calendar.current_week
        const isPast = calendar.current_week !== null && week.number < calendar.current_week
        return (
          <div
            key={week.number}
            title={`Week ${week.number}`}
            style={{
              width: 7,
              height: isCur ? 18 : 12,
              borderRadius: 2,
              background: isCur ? '#C97B2E' : isPast ? '#8E939B' : '#DCE0E5',
            }}
          />
        )
      })}
      <div
        title="Off-season week"
        style={{
          width: 7,
          height: 12,
          borderRadius: 2,
          background: 'repeating-linear-gradient(135deg,#D8C3AA 0 3px,#EFE4D6 3px 6px)',
        }}
      />
    </div>
  )
}

function WeekRow({ week, isCurrent, isFirst }: { week: CalendarWeek; isCurrent: boolean; isFirst: boolean }) {
  const dateLabel = week.races.length
    ? formatMonth(week.races[0].starts_at ?? week.starts_at).toUpperCase()
    : '—'

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '84px minmax(0,1fr)',
        alignItems: 'stretch',
        borderTop: isFirst ? 'none' : `1px solid ${color.divider}`,
        background: isCurrent ? calendarAccent.rowWash : color.surface,
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '12px 0',
          borderRight: `1px solid ${isCurrent ? calendarAccent.border : color.dividerStrong}`,
          background: isCurrent ? calendarAccent.railWash : color.surface,
          color: isCurrent ? calendarAccent.ink : color.mutedStrong,
        }}
      >
        <div style={{ fontSize: 9, letterSpacing: '1.4px', fontFamily: font.mono, opacity: 0.7 }}>WEEK</div>
        <div style={{ fontSize: 22, fontWeight: 700, fontFamily: font.mono, lineHeight: 1 }}>
          {String(week.number).padStart(2, '0')}
        </div>
        <div style={{ fontSize: 9.5, letterSpacing: '1px', fontFamily: font.mono, opacity: 0.55, marginTop: 3 }}>
          {dateLabel}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0, padding: '10px 16px 10px 0' }}>
        {isCurrent ? (
          <div style={{ fontSize: 9.5, letterSpacing: '1.5px', fontWeight: 700, color: calendarAccent.ink, fontFamily: font.mono }}>
            CURRENT WEEK
          </div>
        ) : null}

        {week.races.length === 0 ? (
          <div style={{ fontSize: 12.5, color: '#9DA1A8', fontStyle: 'italic', padding: '6px 2px' }}>
            Training week — no race held
          </div>
        ) : (
          groupStageRaces(week.races).map((entry) =>
            entry.type === 'stage_race' ? (
              <StageRaceGroup key={`stage-race-${entry.stageRace.id}`} races={entry.races} />
            ) : (
              <RaceRow key={entry.race.id} race={entry.race} />
            ),
          )
        )}
      </div>
    </div>
  )
}

type CalendarEntry =
  | { type: 'race'; race: CalendarRace }
  | { type: 'stage_race'; stageRace: NonNullable<CalendarRace['stage_race']>; races: CalendarRace[] }

/** Folds consecutive races sharing a stage_race.id into one group — the
 * calendar entry the spec asks for: a tour reads as one banner spanning
 * its days, not a run of otherwise-identical race rows. A one-day race
 * passes through untouched. */
function groupStageRaces(races: CalendarRace[]): CalendarEntry[] {
  const entries: CalendarEntry[] = []
  for (const race of races) {
    const last = entries[entries.length - 1]
    if (race.stage_race && last?.type === 'stage_race' && last.stageRace.id === race.stage_race.id) {
      last.races.push(race)
      continue
    }
    entries.push(
      race.stage_race
        ? { type: 'stage_race', stageRace: race.stage_race, races: [race] }
        : { type: 'race', race },
    )
  }
  return entries
}

function StageRaceGroup({ races }: { races: CalendarRace[] }) {
  const { name, stage_count } = races[0].stage_race!
  const dayRange =
    races[0].starts_at && races[races.length - 1].starts_at
      ? `${formatWeekday(races[0].starts_at)}–${formatWeekday(races[races.length - 1].starts_at!)}`
      : null

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        borderRadius: 12,
        border: `1px solid ${calendarAccent.border}`,
        background: calendarAccent.headerWash,
        padding: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '0 2px' }}>
        <span style={{ fontSize: 13.5, fontWeight: 700, letterSpacing: '-0.2px', color: calendarAccent.ink }}>
          {name}
        </span>
        <span style={{ fontSize: 10.5, fontFamily: font.mono, color: color.mutedStrong, letterSpacing: '0.5px' }}>
          {stage_count} stages{dayRange ? ` · ${dayRange}` : ''}
        </span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {races.map((race) => (
          <RaceRow key={race.id} race={race} stageLabel={`Stage ${race.stage_race!.stage_number}`} />
        ))}
      </div>
    </div>
  )
}

function RaceRow({ race, stageLabel }: { race: CalendarRace; stageLabel?: string }) {
  const date = race.starts_at
    ? formatShortDate(race.starts_at)
    : ''
  const hot = race.status === 'running'

  return (
    <Link
      to={racePath(race.id)}
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0,1fr) auto',
        gap: 12,
        alignItems: 'center',
        padding: '11px 14px',
        borderRadius: 10,
        border: `1px solid ${hot ? calendarAccent.border : '#E9ECEF'}`,
        background: race.status === 'running' ? '#F7F0E8' : color.surface,
        textDecoration: 'none',
        color: 'inherit',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 14, fontWeight: 600, letterSpacing: '-0.2px' }}>
            {stageLabel ? stageLabel : race.name}
          </span>
          <span
            style={{
              fontSize: 9.5,
              letterSpacing: '1px',
              fontWeight: 700,
              padding: '3px 7px',
              borderRadius: 5,
              whiteSpace: 'nowrap',
              fontFamily: font.mono,
              background: color.canvas,
              color: raceStatusTone(race.status),
            }}
          >
            {raceStatusLabel(race.status).toUpperCase()}
          </span>
        </div>
        <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
          {date} · {race.distance_km.toFixed(1)} km
        </div>
      </div>
    </Link>
  )
}

function OffSeasonRow() {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '84px minmax(0,1fr)',
        alignItems: 'center',
        background: 'repeating-linear-gradient(135deg,#F7F4F0 0 8px,#F2EEE9 8px 16px)',
        borderTop: `1px solid ${color.border}`,
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 2,
          padding: '12px 0',
          color: '#8A6642',
        }}
      >
        <div style={{ fontSize: 9, letterSpacing: '1.4px', fontFamily: font.mono, opacity: 0.7 }}>WEEK</div>
        <div style={{ fontSize: 22, fontWeight: 700, fontFamily: font.mono, lineHeight: 1 }}>13</div>
      </div>
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          padding: '12px 16px 12px 0',
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600, color: calendarAccent.ink, letterSpacing: '0.2px' }}>
          Off-season week · no racing
        </div>
      </div>
    </div>
  )
}
