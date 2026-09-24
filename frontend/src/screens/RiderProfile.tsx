import { Link, useParams } from 'react-router-dom'

import type { RiderRace } from '../api'
import { AttributeHistoryChart } from '../components/AttributeHistoryChart'
import { AttributeRadar } from '../components/AttributeRadar'
import { Card, CardHeader, PageBody, PageHeading, StatTile } from '../components/primitives'
import { formatMoney } from '../format'
import { formatGap, formatRaceTime } from '../raceTime'
import { color, font } from '../theme'
import { useRiderProfile } from '../useRiderProfile'

export function RiderProfile() {
  const { riderId } = useParams<{ riderId: string }>()
  const id = Number(riderId)

  const { profile, loading, notFound, error } = useRiderProfile(id)

  if (loading) return null

  if (notFound) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            This rider is no longer part of the game.
          </div>
        </Card>
      </PageBody>
    )
  }

  if (error || !profile) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load this rider.</div>
        </Card>
      </PageBody>
    )
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow={profile.speciality.toUpperCase()}
        title={profile.name}
        titleSize={29}
        subtitle={`${profile.team?.name ?? 'Free agent'} · ${profile.age} yrs · ${profile.nationality}`}
      />

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <StatTile label="HEIGHT" value={`${profile.height_cm} cm`} minWidth={104} />
        <StatTile label="WEIGHT" value={`${profile.weight_kg} kg`} minWidth={104} />
        <StatTile label="WEEKLY SALARY" value={formatMoney(profile.weekly_salary)} suffix="/wk" minWidth={130} />
        <StatTile label="MARKET VALUE" value={formatMoney(profile.market_value)} minWidth={130} />
        <StatTile label="FRESHNESS" value={`${profile.freshness} / 10`} minWidth={104} />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
          gap: 18,
        }}
      >
        <Card style={{ padding: '16px 18px' }}>
          <CardHeader title="Attributes" />
          <div style={{ padding: '16px 4px 4px' }}>
            <AttributeRadar rider={profile} />
          </div>
        </Card>
        <Card style={{ padding: '16px 18px' }}>
          <CardHeader title="Attribute history" />
          <div style={{ padding: '16px 4px 4px' }}>
            <AttributeHistoryChart
              history={profile.attribute_history}
              current={profile}
              currentWeek={profile.current_week}
            />
          </div>
        </Card>
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <StatTile label="RACES" value={String(profile.career.starts)} minWidth={100} />
        <StatTile label="WINS" value={String(profile.career.wins)} minWidth={100} />
        <StatTile label="PODIUMS" value={String(profile.career.podiums)} minWidth={100} />
        <StatTile label="TOP 10" value={String(profile.career.top_tens)} minWidth={100} />
        <StatTile label="DNF" value={String(profile.career.dnfs)} minWidth={100} />
      </div>

      <RaceHistory races={profile.races} />
    </PageBody>
  )
}

function timeCell(row: RiderRace): string {
  if (!row.finished || row.finish_time === null) return 'DNF'
  if (row.winner_time === null || row.finish_time === row.winner_time) {
    return formatRaceTime(row.finish_time)
  }
  return formatGap(row.finish_time - row.winner_time)
}

function RaceHistory({ races }: { races: RiderRace[] }) {
  return (
    <Card>
      <CardHeader title="Race history" />
      {races.length === 0 ? (
        <div style={{ padding: '18px 20px', fontSize: 13.5, color: color.muted }}>No races yet.</div>
      ) : (
        <div>
          {races.map((row) => (
            <div
              key={row.race.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '12px 20px',
                borderBottom: `1px solid ${color.divider}`,
              }}
            >
              <div style={{ width: 96, fontSize: 12.5, color: color.muted }}>
                {row.race.starts_at ? new Date(row.race.starts_at).toLocaleDateString() : '—'}
              </div>
              <div style={{ flex: 1, fontSize: 14, minWidth: 0 }}>
                <Link to={`/race/${row.race.id}`} style={{ color: color.ink, textDecoration: 'none' }}>
                  {row.race.name}
                </Link>
                {row.team ? (
                  <span style={{ marginLeft: 8, fontFamily: font.mono, fontSize: 11.5, color: color.muted }}>
                    {row.team.code}
                  </span>
                ) : null}
              </div>
              <div style={{ width: 32, fontFamily: font.mono, fontSize: 13, color: color.mutedStrong }}>
                {row.finished ? row.position : '—'}
              </div>
              <div style={{ fontFamily: font.mono, fontSize: 14, fontWeight: 600 }}>{timeCell(row)}</div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
