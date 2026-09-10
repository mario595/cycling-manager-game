import type { ParsedRace } from '../types/race'

// Same distance used by computePacks.ts to decide riders are in one pack —
// reused here so "finished in the same group" matches what the pack view
// already considers one group, rather than inventing a second threshold.
const PACK_COHESION_DISTANCE = 60.0

export interface RiderResult {
  finishTime: number | null
  gapSeconds: number | null
}

export function computeRaceResults(raceData: ParsedRace): Map<string, RiderResult> {
  const { snapshots } = raceData
  const results = new Map<string, RiderResult>()

  const finishTimeById = new Map<string, number>()
  const seen = new Set<string>()
  for (const snapshot of snapshots) {
    for (const rider of snapshot.riders) {
      if (rider.finished && !seen.has(rider.id)) {
        seen.add(rider.id)
        finishTimeById.set(rider.id, rider.finish_time ?? snapshot.time)
      }
    }
  }

  const snapshotByTick = new Map(snapshots.map((s) => [s.time, s]))

  const finishers = [...finishTimeById.entries()].sort(([, a], [, b]) => a - b)

  let winnerFinishTime: number | null = null
  let prevRiderId: string | null = null
  let prevFinishTime = 0
  let prevGapSeconds = 0

  for (const [riderId, finishTime] of finishers) {
    if (winnerFinishTime === null) {
      winnerFinishTime = finishTime
      results.set(riderId, { finishTime, gapSeconds: null })
      prevRiderId = riderId
      prevFinishTime = finishTime
      prevGapSeconds = 0
      continue
    }

    let gapSeconds = finishTime - winnerFinishTime

    if (prevRiderId !== null) {
      const snapshotAtPrevFinish = snapshotByTick.get(prevFinishTime)
      const riderAtPrevFinish = snapshotAtPrevFinish?.riders.find((r) => r.id === riderId)
      const prevRiderAtPrevFinish = snapshotAtPrevFinish?.riders.find((r) => r.id === prevRiderId)
      if (riderAtPrevFinish && prevRiderAtPrevFinish) {
        const distance = prevRiderAtPrevFinish.pos - riderAtPrevFinish.pos
        if (distance <= PACK_COHESION_DISTANCE) {
          gapSeconds = prevGapSeconds
        }
      }
    }

    results.set(riderId, { finishTime: null, gapSeconds })
    prevRiderId = riderId
    prevFinishTime = finishTime
    prevGapSeconds = gapSeconds
  }

  return results
}
