import type { ParsedRace, RaceSnapshot } from '../types/race'
import { computeProfile } from './profile'

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
