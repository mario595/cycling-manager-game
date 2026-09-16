import { useEffect, useMemo, useState } from 'react'

import { getRaceResults, type CalendarRace, type RaceResults } from '../api'
import { Card, CardHeader, PageBody, PageHeading } from '../components/primitives'
import { color, font } from '../theme'
import { useCalendar } from '../useCalendar'

function latestFinishedRace(races: CalendarRace[]): CalendarRace | null {
  const finished = races.filter((r) => r.status === 'finished')
  if (finished.length === 0) return null
  return finished.reduce((latest, race) =>
    (race.starts_at ?? '') > (latest.starts_at ?? '') ? race : latest,
  )
}

export function Results() {
  const { calendar, loading: calendarLoading, error: calendarError } = useCalendar()
  const [results, setResults] = useState<RaceResults | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const latestRace = useMemo(() => {
    if (!calendar || calendar.state !== 'in_season') return null
    return latestFinishedRace(calendar.weeks.flatMap((w) => w.races))
  }, [calendar])

  useEffect(() => {
    if (!latestRace) return
    let cancelled = false
    setLoading(true)
    getRaceResults(latestRace.id)
      .then((data) => {
        if (cancelled) return
        setResults(data)
        setError(false)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setError(true)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [latestRace])

  if (calendarLoading) return null

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="RACING"
        title="Results"
        titleSize={29}
        subtitle="The most recently finished race this season."
      />

      {calendarError || error ? (
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load the results.</div>
        </Card>
      ) : !latestRace ? (
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>No race has finished yet this season.</div>
        </Card>
      ) : loading || !results ? null : (
        <ResultsTable results={results} />
      )}
    </PageBody>
  )
}

function ResultsTable({ results }: { results: RaceResults }) {
  // Points belong to a team's best-placed finisher only (see
  // specs/race-points-and-standings.md) — key by the exact scoring
  // position, not just the team, so a second rider from the same team
  // doesn't also appear to have earned points.
  const pointsByPosition = new Map(results.points.map((p) => [p.position, p.points]))

  return (
    <Card>
      <CardHeader title={results.race.name} />
      <div>
        {results.results.map((entry) => (
          <div
            key={entry.rider.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '12px 20px',
              borderBottom: `1px solid ${color.divider}`,
            }}
          >
            <div style={{ width: 32, fontFamily: font.mono, fontSize: 13, color: color.mutedStrong }}>
              {entry.finished ? entry.position : '—'}
            </div>
            <div style={{ flex: 1, fontSize: 14 }}>
              {entry.rider.name}
              {entry.team ? (
                <span style={{ marginLeft: 8, fontFamily: font.mono, fontSize: 11.5, color: color.muted }}>
                  {entry.team.code}
                </span>
              ) : null}
            </div>
            <div style={{ fontFamily: font.mono, fontSize: 14, fontWeight: 600 }}>
              {pointsByPosition.has(entry.position) ? `+${pointsByPosition.get(entry.position)}` : ''}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
