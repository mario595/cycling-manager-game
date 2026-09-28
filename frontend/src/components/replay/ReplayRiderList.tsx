import { formatGapTime } from '../../../../race_player/src/utils/formatTime'
import { packGaps } from '../../../../race_player/src/utils/packGaps'
import { resultLabel, type RiderResult } from '../../../../race_player/src/utils/raceResults'
import { isLeader, teamCode, teamColor, teamName } from '../../../../race_player/src/utils/teamColors'
import type { Pack, Rider } from '../../../../race_player/src/types/race'

import { color, font } from '../../theme'
import { Bar, Card } from '../primitives'

// Same thresholds race_player's RiderList reads its bars with: cruise pace
// degrades below 60, and below 30 a rider is genuinely cracked.
const STAMINA_YELLOW = 60
const STAMINA_RED = 30

function staminaColor(value: number): string {
  if (value >= STAMINA_YELLOW) return color.ink
  if (value >= STAMINA_RED) return color.accent
  return color.negative
}

function Tag({ children, tint }: { children: string; tint: string }) {
  return (
    <span
      style={{
        marginLeft: 7,
        padding: '2px 5px',
        borderRadius: 4,
        fontSize: 9.5,
        letterSpacing: '0.6px',
        fontWeight: 700,
        fontFamily: font.mono,
        color: tint,
        background: color.canvas,
      }}
    >
      {children}
    </span>
  )
}

function Meter({ label, value, fill }: { label: string; value: number; fill: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, width: 92 }}>
      <span style={{ fontSize: 9.5, color: color.muted, fontFamily: font.mono, width: 10 }}>{label}</span>
      <Bar value={value} fill={fill} />
      <span style={{ fontSize: 10.5, color: color.mutedStrong, fontFamily: font.mono, width: 20, textAlign: 'right' }}>
        {Math.round(value)}
      </span>
    </div>
  )
}

function Row({
  rider,
  rank,
  teamCodes,
  teamNames,
  result,
  isOwn,
}: {
  rider: Rider
  rank: number | null
  teamCodes: Record<string, string>
  teamNames: Record<string, string>
  result?: RiderResult
  isOwn: boolean
}) {
  return (
    <div
      // The test hook for the own-team highlight; the tint alone is a visual.
      data-own-team={isOwn ? 'true' : undefined}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '9px 18px',
        borderLeft: `3px solid ${teamColor(rider.team)}`,
        background: isOwn ? color.accentWash : 'transparent',
        borderBottom: `1px solid ${color.divider}`,
      }}
    >
      <div style={{ width: 26, fontFamily: font.mono, fontSize: 12.5, color: color.mutedStrong }}>
        {rank === null ? '—' : rank}
      </div>
      <div
        style={{ width: 34, fontFamily: font.mono, fontSize: 11.5, fontWeight: 600, color: teamColor(rider.team) }}
        title={teamName(teamNames, rider.team)}
      >
        {teamCode(teamCodes, rider.team)}
      </div>
      <div style={{ flex: 1, minWidth: 0, fontSize: 13.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {rider.name}
        {isLeader(rider) ? (
          <span title="Team leader" style={{ color: color.accent, marginLeft: 5 }}>★</span>
        ) : null}
        {rider.pulling ? <Tag tint={color.ink}>PULL</Tag> : null}
        {rider.surging ? <Tag tint={color.accentInk}>ATK</Tag> : null}
      </div>
      <div style={{ width: 62, textAlign: 'right', fontFamily: font.mono, fontSize: 12.5 }}>
        {(rider.pos / 1000).toFixed(2)} km
      </div>
      <div style={{ width: 58, textAlign: 'right', fontFamily: font.mono, fontSize: 12.5, color: color.mutedStrong }}>
        {rider.finished ? '✓' : rider.dnf ? '—' : `${(rider.speed * 3.6).toFixed(0)} km/h`}
      </div>
      <div style={{ width: 74, textAlign: 'right', fontFamily: font.mono, fontSize: 12.5 }}>
        {rider.dnf ? 'DNF' : resultLabel(rider, result)}
      </div>
      {rider.dnf ? null : (
        <div style={{ display: 'flex', gap: 10 }}>
          <Meter label="S" value={rider.stamina} fill={staminaColor(rider.stamina)} />
          <Meter label="E" value={rider.energy} fill={color.negative} />
        </div>
      )}
    </div>
  )
}

/**
 * The field as it stands at this tick: packs in order with the gap between
 * them, then whoever the time limit has already taken off the road.
 *
 * Built from divs rather than a table, like the rest of the game's rows, and
 * deliberately without race_player's emoji and icons — the game does not use
 * them, so a leader is a `★`, a rider on the front is `PULL` and a rider
 * attacking is `ATK`, and the legend says so.
 */
export function ReplayRiderList({
  packs,
  out,
  teamCodes,
  teamNames,
  results,
  highlightTeam,
}: {
  packs: Pack[]
  out: Rider[]
  teamCodes: Record<string, string>
  teamNames: Record<string, string>
  results: Map<string, RiderResult>
  highlightTeam: string | null
}) {
  const isOwn = (rider: Rider) => highlightTeam !== null && rider.team === highlightTeam
  const gaps = packGaps(packs)
  let rank = 0

  return (
    <Card>
      <div>
        {packs.map((pack, index) => (
          <div key={index}>
            {gaps[index] === null ? null : (
              <div
                style={{
                  padding: '6px 18px',
                  background: color.canvas,
                  borderBottom: `1px solid ${color.dividerStrong}`,
                  fontSize: 11,
                  fontWeight: 600,
                  fontFamily: font.mono,
                  color: color.mutedStrong,
                }}
              >
                +{formatGapTime(gaps[index]!.seconds)} · {gaps[index]!.meters.toFixed(0)} m
              </div>
            )}
            {pack.riders.map((rider) => {
              const thisRank = rank
              rank += 1
              return (
                <Row
                  key={rider.id}
                  rider={rider}
                  rank={thisRank + 1}
                  teamCodes={teamCodes}
                  teamNames={teamNames}
                  result={results.get(rider.id)}
                  isOwn={isOwn(rider)}
                />
              )
            })}
          </div>
        ))}

        {out.length > 0 ? (
          <>
            <div
              style={{
                padding: '9px 18px',
                background: color.canvas,
                borderBottom: `1px solid ${color.dividerStrong}`,
                borderTop: `1px solid ${color.dividerStrong}`,
                fontSize: 10.5,
                letterSpacing: '1px',
                fontWeight: 700,
                color: color.mutedStrong,
              }}
            >
              Out of the race
            </div>
            {out.map((rider) => (
              <Row
                key={rider.id}
                rider={rider}
                rank={null}
                teamCodes={teamCodes}
                teamNames={teamNames}
                result={results.get(rider.id)}
                isOwn={isOwn(rider)}
              />
            ))}
          </>
        ) : null}
      </div>

      <div
        style={{
          display: 'flex',
          gap: 16,
          padding: '9px 18px',
          borderTop: `1px solid ${color.dividerStrong}`,
          fontSize: 11,
          color: color.muted,
        }}
      >
        <span>
          <span style={{ color: color.accent }}>★</span> leader
        </span>
        <span>PULL on the front</span>
        <span>ATK attacking</span>
      </div>
    </Card>
  )
}
