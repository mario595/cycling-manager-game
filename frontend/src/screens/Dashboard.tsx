import { Link } from 'react-router-dom'

import { Card, CardHeader, PageBody, PageHeading } from '../components/primitives'
import { nextRace } from '../nextRace'
import { seasonLabel } from '../seasonLabel'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useCalendar } from '../useCalendar'
import { useNextRaceSquad } from '../useNextRaceSquad'
import { useSeason } from '../useSeason'
import { useStandings } from '../useStandings'

export function Dashboard() {
  const { me } = useAuth()
  const { position } = useSeason()

  return (
    <PageBody>
      <PageHeading
        eyebrow={seasonLabel(position)}
        title={me ? `Good morning, ${me.display_name}.` : ''}
        subtitle={me?.team?.name ?? ''}
      />

      <StandingsSection />

      <NextRaceCard />
    </PageBody>
  )
}

function StandingsSection() {
  const { me } = useAuth()
  const { standings } = useStandings()

  const team = me?.team
  if (!standings || standings.state === 'no_season' || !team) return null

  const mine = standings.standings.find((entry) => entry.team.id === team.id)
  if (!mine) return null

  return (
    <Card>
      <CardHeader title="Standings" />
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 10,
          padding: '16px 20px',
        }}
      >
        <div style={{ fontSize: 20, fontWeight: 600, fontFamily: font.mono }}>
          #{mine.rank}
        </div>
        <div style={{ fontSize: 13, color: color.muted }}>
          {mine.points} pts
        </div>
      </div>
    </Card>
  )
}

function NextRaceCard() {
  const { calendar, loading } = useCalendar()
  const race = nextRace(calendar)
  const { saved } = useNextRaceSquad(race?.id ?? null)

  return (
    <Card>
      <CardHeader title="Next race" />
      {loading ? null : race === null ? (
        <div style={{ padding: '16px 20px', fontSize: 13, color: color.muted }}>
          The season has no races left.
        </div>
      ) : (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            padding: '16px 20px',
          }}
        >
          <Link
            to={`/race/${race.id}`}
            style={{ fontSize: 17, fontWeight: 600, color: color.ink, textDecoration: 'none' }}
          >
            {race.name}
          </Link>
          <div style={{ fontSize: 12.5, color: color.muted, fontFamily: font.mono }}>
            {race.starts_at
              ? new Date(race.starts_at).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                })
              : 'unscheduled'}
          </div>
          {saved === true ? (
            <div style={{ fontSize: 13, color: color.positive }}>Squad set</div>
          ) : saved === false ? (
            <div style={{ fontSize: 13, color: color.accentInk }}>
              No squad chosen — one will be picked for you
            </div>
          ) : null}
        </div>
      )}
    </Card>
  )
}