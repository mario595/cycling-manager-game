import { useState } from 'react'
import { Link } from 'react-router-dom'

import type { RaceDetail, RacePayoutEntry, RaceResultEntry, RaceResults } from '../api'
import { formatMoney } from '../format'
import { riderPath } from '../navigation'
import { formatGap, formatRaceTime } from '../raceTime'
import { color, font } from '../theme'
import { Button, Card, CardHeader } from './primitives'
import { useRaceResults } from '../useRaceResults'

/**
 * A finished race's tables, behind a reveal.
 *
 * A race screen is where a manager goes to read a result, so the results are
 * not fetched at all until asked for: the log replay (see `HiddenResults` in
 * `screens/Replay.tsx`) reaches for the same tables, and a second screen
 * asking on its behalf would double a request nobody has made.
 */
export function HiddenResults({ race }: { race: RaceDetail }) {
  const [revealed, setRevealed] = useState(false)
  const { results, error } = useRaceResults(race.id, revealed)

  return (
    <>
      <Card>
        <CardHeader
          title="Results"
          action={
            <Button variant="secondary" onClick={() => setRevealed((current) => !current)}>
              {revealed ? 'Hide results' : 'Show results'}
            </Button>
          }
        />
        {revealed && error ? (
          <div style={{ padding: '18px 20px', fontSize: 13.5, color: color.muted }}>
            Couldn't load this race's results.
          </div>
        ) : null}
      </Card>
      {/* While loading, nothing: the toggle above is the whole card, and the
          tables appear when the response lands. */}
      {revealed && !error && results ? (
        <>
          <RiderResultsTable results={results} payout={race.payout} />
          <TeamPointsTable results={results} />
          {results.markers.length > 0 ? <MarkerResultsCard results={results} /> : null}
        </>
      ) : null}
    </>
  )
}

export function RiderResultsTable({ results, payout }: { results: RaceResults; payout: RacePayoutEntry[] }) {
  const winner = results.results.find((r) => r.finished)
  const winnerTime = winner?.finish_time ?? null
  const prizeByPosition = new Map(payout.map((p) => [p.position, p.prize]))

  const timeCell = (entry: RaceResultEntry): string => {
    if (!entry.finished || entry.finish_time === null || winnerTime === null) return 'DNF'
    if (entry.position === winner?.position) return formatRaceTime(winnerTime)
    return formatGap(entry.finish_time - winnerTime)
  }

  const prizeFor = (entry: RaceResultEntry): number => {
    if (!entry.finished) return 0
    return prizeByPosition.get(entry.position) ?? 0
  }

  return (
    <Card>
      <CardHeader title="Rider results" />
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
              <Link to={riderPath(entry.rider.id)} style={{ color: color.ink, textDecoration: 'none' }}>
                {entry.rider.name}
              </Link>
              {entry.team ? (
                <span style={{ marginLeft: 8, fontFamily: font.mono, fontSize: 11.5, color: color.muted }}>
                  {entry.team.code}
                </span>
              ) : null}
            </div>
            <div style={{ width: 64, textAlign: 'right', fontFamily: font.mono, fontSize: 13.5, fontWeight: 600, whiteSpace: 'nowrap', color: color.positive }}>
              {prizeFor(entry) > 0 ? formatMoney(prizeFor(entry)) : ''}
            </div>
            <div style={{ fontFamily: font.mono, fontSize: 14, fontWeight: 600 }}>{timeCell(entry)}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}

export function TeamPointsTable({ results }: { results: RaceResults }) {
  return (
    <Card>
      <CardHeader title="Team points" />
      <div>
        {results.points.map((entry) => (
          <div
            key={entry.team.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '12px 20px',
              borderBottom: `1px solid ${color.divider}`,
            }}
          >
            <div style={{ flex: 1, fontSize: 14 }}>
              {entry.team.name}
              <span style={{ marginLeft: 8, fontFamily: font.mono, fontSize: 11.5, color: color.muted }}>
                {entry.team.code}
              </span>
            </div>
            <div style={{ fontFamily: font.mono, fontSize: 14, fontWeight: 600 }}>{entry.points}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}

export function MarkerResultsCard({ results }: { results: RaceResults }) {
  return (
    <Card>
      <CardHeader title="Sprints and summits" />
      <div>
        {results.markers.map((marker) => (
          <div
            key={marker.id}
            style={{
              padding: '14px 20px',
              borderBottom: `1px solid ${color.divider}`,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>
                {marker.kind === 'sprint' ? 'Sprint' : 'Mountain'} · {marker.name}
              </div>
              <div style={{ fontFamily: font.mono, fontSize: 11.5, color: color.mutedStrong, whiteSpace: 'nowrap' }}>
                km {(marker.distance / 1000).toFixed(1)}
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginTop: 10 }}>
              {marker.crossings.map((crossing) => (
                <div key={crossing.rider.id} style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 13.5 }}>
                  <span style={{ width: 24, fontFamily: font.mono, fontSize: 12.5, color: color.mutedStrong }}>
                    {crossing.position}
                  </span>
                  <Link to={riderPath(crossing.rider.id)} style={{ color: color.ink, textDecoration: 'none' }}>
                    {crossing.rider.name}
                  </Link>
                  {crossing.team ? (
                    <span style={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
                      {crossing.team.code}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
