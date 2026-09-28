import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'

import { computePacks } from '../../../race_player/src/utils/computePacks'
import { computeRaceResults } from '../../../race_player/src/utils/raceResults'
import { usePlayback } from '../../../race_player/src/utils/usePlayback'
import ElevationProfile from '../../../race_player/src/components/ElevationProfile'
import type { ParsedRace } from '../../../race_player/src/types/race'

import type { RaceDetail } from '../api'
import { ReplayControls } from '../components/replay/ReplayControls'
import { ReplayRiderList } from '../components/replay/ReplayRiderList'
import { HiddenResults } from '../components/RaceResults'
import { Card, PageBody, PageHeading } from '../components/primitives'
import { color } from '../theme'
import { racePath } from '../navigation'
import { useAuth } from '../useAuth'
import { useRaceDetail } from '../useRaceDetail'
import { useRaceLog } from '../useRaceLog'

export function Replay() {
  const { raceId } = useParams<{ raceId: string }>()
  const id = Number(raceId)
  const { me } = useAuth()
  const { race, loading, error } = useRaceDetail(id)
  // Only a finished race with a stored log has a replay; asking otherwise
  // would be a request that 404s by design.
  const { race: parsed, loading: logLoading, error: logError } = useRaceLog(
    id,
    race?.status === 'finished' && race.has_replay === true,
  )

  if (loading) return null

  if (error || !race) return <Message text="Couldn't load this race." link={racePath(id)} />

  if (race.status !== 'finished') return <Message text="This race hasn't finished yet." link={racePath(id)} />
  if (!race.has_replay) return <Message text="No replay is available for this race." link={racePath(id)} />
  if (logLoading) return <Message text="Loading replay…" link={racePath(id)} />
  if (logError || !parsed) return <Message text="This race's replay couldn't be loaded." link={racePath(id)} />

  return (
    <ReplayView
      race={race}
      parsed={parsed}
      highlightTeam={me?.team ? String(me.team.id) : null}
    />
  )
}

function Message({ text, link }: { text: string; link?: string }) {
  return (
    <PageBody gap={14} paddingTop={26}>
      <Card style={{ padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ fontSize: 13.5, color: color.muted }}>{text}</div>
        {link ? (
          <Link to={link} style={{ fontSize: 13, color: color.accentInk, textDecoration: 'none' }}>
            ← Back to race
          </Link>
        ) : null}
      </Card>
    </PageBody>
  )
}

/**
 * Its own component, so `usePlayback` is only ever called with a real
 * `maxTicks` — a hook cannot be called conditionally, and a placeholder 0
 * would make the replay unplayable for the rest of its life.
 */
function ReplayView({
  race,
  parsed,
  highlightTeam,
}: {
  race: RaceDetail
  parsed: ParsedRace
  highlightTeam: string | null
}) {
  const playback = usePlayback(parsed.maxTicks, parsed.tickInterval, { initialSpeed: 10 })
  const snapshot = parsed.snapshots[playback.tick]

  // The finished order is a property of the whole race, not of a tick, so it
  // is computed once per loaded log — `computeRaceResults` walks every
  // sample × every rider, and re-deriving it per frame would make playing a
  // race cost the square of its length. Same reason as `RaceViz`.
  const results = useMemo(() => computeRaceResults(parsed), [parsed])

  // Only what this tick actually shows is per-tick.
  const { out, packs } = useMemo(() => {
    const riders = snapshot?.riders ?? []
    return {
      out: riders.filter((rider) => rider.dnf),
      packs: computePacks(
        riders.filter((rider) => !rider.dnf),
        parsed.profile,
      ),
    }
  }, [snapshot, parsed.profile])

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="REPLAY"
        title={race.name}
        titleSize={29}
        subtitle={`${race.distance_km.toFixed(1)} km · how it unfolded`}
        aside={
          <Link to={racePath(race.id)} style={{ fontSize: 13, color: color.accentInk, textDecoration: 'none' }}>
            ← Back to race
          </Link>
        }
      />

      <ReplayControls
        playback={playback}
        tickInterval={parsed.tickInterval}
        maxTicks={parsed.maxTicks}
        wind={snapshot?.wind}
      />

      <Card style={{ padding: 12 }}>
        <ElevationProfile
          profile={parsed.profile}
          packs={packs}
          highlightTeam={highlightTeam}
          highlightColor={color.ink}
        />
      </Card>

      <ReplayRiderList
        packs={packs}
        out={out}
        teamCodes={parsed.teamCodes}
        teamNames={parsed.teamNames}
        results={results}
        highlightTeam={highlightTeam}
      />

      <HiddenResults race={race} />
    </PageBody>
  )
}
