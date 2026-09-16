import type { Standings } from '../api'
import { Card, CardHeader, PageBody, PageHeading } from '../components/primitives'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useStandings } from '../useStandings'

export function League() {
  const { me, loading: authLoading } = useAuth()
  const { standings, loading, error } = useStandings()

  if (authLoading || loading) return null

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="COMPETITION"
        title="League table"
        titleSize={29}
        subtitle={subtitle(standings)}
      />

      {error ? (
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load the standings.</div>
        </Card>
      ) : standings && standings.standings.length > 0 ? (
        <StandingsTable standings={standings} ownTeamId={me?.team?.id ?? null} />
      ) : (
        <EmptyState standings={standings} />
      )}
    </PageBody>
  )
}

function subtitle(standings: Standings | null): string {
  if (!standings || standings.state === 'no_season') {
    return 'No season has been declared yet.'
  }
  if (standings.state === 'off_season') {
    return `Final standings for season ${standings.season}.`
  }
  return `Points from every race so far this season.`
}

function StandingsTable({ standings, ownTeamId }: { standings: Standings; ownTeamId: number | null }) {
  return (
    <Card>
      <CardHeader title={`Season ${standings.season}`} />
      <div>
        {standings.standings.map((entry) => {
          const isOwnTeam = entry.team.id === ownTeamId
          return (
            <div
              key={entry.team.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '12px 20px',
                borderBottom: `1px solid ${color.divider}`,
                background: isOwnTeam ? color.accentWash : 'transparent',
              }}
            >
              <div style={{ width: 28, fontFamily: font.mono, fontSize: 13, color: color.mutedStrong }}>
                {entry.rank}
              </div>
              <div style={{ flex: 1, fontSize: 14, fontWeight: isOwnTeam ? 600 : 400 }}>
                {entry.team.name}
                <span style={{ marginLeft: 8, fontFamily: font.mono, fontSize: 11.5, color: color.muted }}>
                  {entry.team.code}
                </span>
              </div>
              <div style={{ fontFamily: font.mono, fontSize: 14, fontWeight: 600 }}>{entry.points}</div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function EmptyState({ standings }: { standings: Standings | null }) {
  const message =
    standings?.state === 'in_season'
      ? 'No points have been scored yet this season.'
      : 'There is no standings table to show right now.'

  return (
    <Card style={{ padding: '18px 20px' }}>
      <div style={{ fontSize: 13.5, color: color.muted }}>{message}</div>
    </Card>
  )
}
