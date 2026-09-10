import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ParsedRace } from '../types/race'
import ElevationProfile from './ElevationProfile'
import PlaybackControls from './PlaybackControls'
import RiderList from './RiderList'
import { computePacks } from '../utils/computePacks'
import { computeRaceResults } from '../utils/raceResults'

interface RaceVizProps {
  raceData: ParsedRace
}

export default function RaceViz({ raceData }: RaceVizProps) {
  const { snapshots, profile, maxTicks } = raceData
  const [tick, setTick] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [selectedRider, setSelectedRider] = useState<string | null>(null)

  const tickRef = useRef(tick)
  tickRef.current = tick

  const snapshot = snapshots[tick]
  const riders = snapshot?.riders ?? []

  // Playback loop
  useEffect(() => {
    if (!playing) return
    const interval = setInterval(() => {
      setTick((t) => {
        if (t >= maxTicks) {
          setPlaying(false)
          return t
        }
        return t + 1
      })
    }, 1000 / speed)
    return () => clearInterval(interval)
  }, [playing, speed, maxTicks])

  const handleTogglePlay = useCallback(() => {
    if (tick >= maxTicks) setTick(0)
    setPlaying((p) => !p)
  }, [tick, maxTicks])

  const handleTickChange = useCallback((t: number) => {
    setTick(Math.max(0, Math.min(maxTicks, t)))
  }, [maxTicks])

  const handleStep = useCallback(
    (dir: -1 | 1) => {
      handleTickChange(tickRef.current + dir)
    },
    [handleTickChange],
  )

  const handleSelectRider = useCallback((id: string) => {
    setSelectedRider(id)
  }, [])

  // Stable refs so the key listener never needs re-subscribing.
  const stepRef = useRef(handleStep)
  stepRef.current = handleStep
  const togglePlayRef = useRef(handleTogglePlay)
  togglePlayRef.current = handleTogglePlay

  // Keyboard controls: ← / → step, Space toggles play/pause
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        stepRef.current(-1)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        stepRef.current(1)
      } else if (e.key === ' ') {
        e.preventDefault()
        togglePlayRef.current()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const activeRider = useMemo(
    () => riders.find((r) => r.id === selectedRider) ?? null,
    [riders, selectedRider],
  )

  const packs = useMemo(() => computePacks(riders, profile), [riders, profile])
  const results = useMemo(() => computeRaceResults(raceData), [raceData])

  return (
    <div className="flex flex-col gap-4 p-4 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold text-slate-800">Race Viewer</h1>

      <PlaybackControls
        playing={playing}
        onTogglePlay={handleTogglePlay}
        tick={tick}
        maxTicks={maxTicks}
        speed={speed}
        onSpeedChange={setSpeed}
        onStep={handleStep}
        onSeek={handleTickChange}
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
