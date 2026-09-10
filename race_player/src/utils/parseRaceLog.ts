import type { ParsedRace, ProfilePoint, RaceSnapshot, Segment } from '../types/race'

function computeProfile(segments: Segment[]): ProfilePoint[] {
  const points: ProfilePoint[] = []
  let elevation = 0
  let distance = 0

  points.push({ distance: 0, elevation: 0, gradient: segments[0]?.gradient ?? 0 })

  for (const seg of segments) {
    const change = seg.length * (seg.gradient / 100)
    elevation += change
    distance += seg.length
    points.push({ distance, elevation, gradient: seg.gradient })
  }

  return points
}

export function parseRaceLog(text: string): ParsedRace {
  const snapshots: RaceSnapshot[] = text
    .trim()
    .split('\n')
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line) as RaceSnapshot)

  if (snapshots.length === 0) {
    throw new Error('race.jsonl is empty')
  }

  const profile = computeProfile(snapshots[0].segments)
  const maxTicks = snapshots.length - 1

  const teamCodes: Record<string, string> = {}
  const teamNames: Record<string, string> = {}
  for (const [teamId, team] of Object.entries(snapshots[0].teams ?? {})) {
    teamCodes[teamId] = team.code
    if (team.name) teamNames[teamId] = team.name
  }

  return {
    snapshots,
    profile,
    courseLength: snapshots[0].course_length,
    maxTicks,
    teamCodes,
    teamNames,
  }
}
