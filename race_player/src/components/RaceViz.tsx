import { useCallback, useMemo, useState } from 'react'
import type { ParsedRace } from '../types/race'
import ElevationProfile from './ElevationProfile'
import PlaybackControls from './PlaybackControls'
import RiderList from './RiderList'
import { computePacks } from '../utils/computePacks'
import { computeRaceResults } from '../utils/raceResults'
import { usePlayback } from '../utils/usePlayback'

interface RaceVizProps {
  raceData: ParsedRace
}

export default function RaceViz({ raceData }: RaceVizProps) {
  const { snapshots, profile, maxTicks, tickInterval } = raceData
  const playback = usePlayback(maxTicks, tickInterval)
  const [selectedRider, setSelectedRider] = useState<string | null>(null)

  const snapshot = snapshots[playback.tick]
  const riders = snapshot?.riders ?? []

  const handleSelectRider = useCallback((id: string) => {
    setSelectedRider(id)
  }, [])

  const activeRider = useMemo(
    () => riders.find((r) => r.id === selectedRider) ?? null,
    [riders, selectedRider],
  )

  const packs = useMemo(
    // A time-cut rider is out of the race, not one that stopped making
    // progress: they leave the road and the packs, rather than freezing on
    // it and being clustered with whoever rides past them.
    () => computePacks(riders.filter((r) => !r.dnf), profile),
    [riders, profile],
  )
  const results = useMemo(() => computeRaceResults(raceData), [raceData])

  return (
    <div className="flex flex-col gap-4 p-4 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold text-slate-800">Race Viewer</h1>

      <PlaybackControls
        playing={playback.playing}
        onTogglePlay={playback.togglePlay}
        tick={playback.tick}
        maxTicks={maxTicks}
        tickInterval={tickInterval}
        speed={playback.speed}
        onSpeedChange={playback.setSpeed}
        onStep={playback.step}
        onSeek={playback.seek}
        wind={snapshot?.wind}
      />

      <div className="bg-white rounded-lg border border-slate-200 p-2">
        <ElevationProfile
          profile={profile}
          packs={packs}
          onSelectRider={handleSelectRider}
        />
      </div>

      <RiderList
        packs={packs}
        teamCodes={raceData.teamCodes}
        teamNames={raceData.teamNames}
        results={results}
        onSelectRider={handleSelectRider}
      />

      {activeRider && (
        <div className="text-xs text-slate-500">
          Selected: <span className="font-medium">{activeRider.name}</span>
        </div>
      )}
    </div>
  )
}
