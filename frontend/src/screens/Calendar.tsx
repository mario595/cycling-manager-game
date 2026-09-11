import type { Calendar as CalendarData, CalendarRace, CalendarWeek } from '../api'
import { Card, CardHeader, PageBody, PageHeading } from '../components/primitives'
import { raceStatusLabel, raceStatusTone } from '../raceStatus'
import { color, font } from '../theme'
import { useCalendar } from '../useCalendar'

export function Calendar() {
  const { calendar, loading, error } = useCalendar()

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        title="Calendar"
        titleSize={29}
        subtitle="Every race the season has planned, from week one."
      />

      {loading ? null : error ? (
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load the calendar.</div>
        </Card>
      ) : calendar && calendar.state === 'in_season' ? (
        <WeekList weeks={calendar.weeks} currentWeek={calendar.current_week} />
      ) : (
        <EmptyState calendar={calendar} />
      )}
    </PageBody>
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

function WeekList({ weeks, currentWeek }: { weeks: CalendarWeek[]; currentWeek: number | null }) {
  return (
    <Card style={{ overflow: 'hidden' }}>
      <CardHeader title="Season calendar" />
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {weeks.map((week) => (
          <WeekRow key={week.number} week={week} isCurrent={week.number === currentWeek} />
        ))}
      </div>
    </Card>
  )
}

function WeekRow({ week, isCurrent }: { week: CalendarWeek; isCurrent: boolean }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 16,
        padding: '13px 20px',
        borderBottom: `1px solid ${color.divider}`,
        background: isCurrent ? color.accentWash : 'transparent',
      }}
    >
      <div
        style={{
          width: 60,
          flex: '0 0 60px',
          fontSize: 12,
          color: color.mutedStrong,
          fontFamily: font.mono,
          paddingTop: 2,
        }}
      >
        WEEK {week.number}
      </div>
      {week.races.length === 0 ? (
        <div style={{ fontSize: 13, color: color.muted, paddingTop: 2 }}>No racing</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1, minWidth: 0 }}>
          {week.races.map((race) => (
            <RaceRow key={race.id} race={race} />
          ))}
        </div>
      )}
    </div>
  )
}

function RaceRow({ race }: { race: CalendarRace }) {
  const day = race.starts_at
    ? new Date(race.starts_at).toLocaleDateString(undefined, {
        weekday: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
    : ''

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
      <div style={{ fontSize: 13.5, fontWeight: 500, letterSpacing: '-0.1px' }}>{race.name}</div>
      <div style={{ fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>{day}</div>
      <div style={{ fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>
        {race.distance_km.toFixed(1)} km
      </div>
      <div
        style={{
          fontSize: 10.5,
          letterSpacing: '0.8px',
          fontWeight: 700,
          padding: '3px 7px',
          borderRadius: 5,
          fontFamily: font.mono,
          color: raceStatusTone(race.status),
          background: color.canvas,
        }}
      >
        {raceStatusLabel(race.status).toUpperCase()}
      </div>
    </div>
  )
}
