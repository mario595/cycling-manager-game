import type {
  ParsedRace,
  RaceHeader,
  RaceHeaderRider,
  RaceRiderSample,
  RaceSample,
  RaceSnapshot,
  Rider,
} from '../types/race'
import { computeProfile } from './profile'

const KNOWN_VERSION = 1

const FLAG_PULLING = 1
const FLAG_SURGING = 2
const FLAG_FINISHED = 4
const FLAG_DNF = 8

function decodeRider(headerRider: RaceHeaderRider, values: RaceRiderSample): Rider {
  const flags = values[4]
  return {
    id: headerRider.id,
    name: headerRider.name,
    team: headerRider.team,
    role: headerRider.role,
    pos: values[0],
    speed: values[1],
    energy: values[2],
    stamina: values[3],
    pulling: (flags & FLAG_PULLING) !== 0,
    surging: (flags & FLAG_SURGING) !== 0,
    finished: (flags & FLAG_FINISHED) !== 0,
    dnf: (flags & FLAG_DNF) !== 0,
    finish_time: values[5],
  }
}

function decodeSnapshot(header: RaceHeader, sample: RaceSample): RaceSnapshot {
  const [time, riderSamples, windSample] = sample
  if (riderSamples.length !== header.riders.length) {
    throw new Error(
      `sample has ${riderSamples.length} riders, expected ${header.riders.length}`,
    )
  }
  const snapshot: RaceSnapshot = {
    time,
    course_length: header.course_length,
    segments: header.segments,
    riders: header.riders.map((headerRider, index) =>
      decodeRider(headerRider, riderSamples[index]),
    ),
    teams: header.teams,
  }
  if (header.wind_band !== undefined && windSample !== undefined) {
    snapshot.wind = {
      speed: windSample[0],
      angle: windSample[1],
      band: header.wind_band,
    }
  }
  return snapshot
}

export function parseRaceLog(text: string): ParsedRace {
  const lines = text.split('\n').filter((line) => line.length > 0)
  if (lines.length === 0) throw new Error('race log is empty')

  const first = JSON.parse(lines[0]) as RaceHeader
  if (Array.isArray(first) || typeof first.v !== 'number') {
    throw new Error('race log has no header line')
  }
  if (first.v !== KNOWN_VERSION) {
    throw new Error(
      `race log format v${first.v} is not supported (expected v${KNOWN_VERSION})`,
    )
  }

  const snapshots = lines
    .slice(1)
    .map((line) => decodeSnapshot(first, JSON.parse(line) as RaceSample))
  const profile = computeProfile(first.segments)

  const teamCodes: Record<string, string> = {}
  const teamNames: Record<string, string> = {}
  for (const [teamId, team] of Object.entries(first.teams)) {
    teamCodes[teamId] = team.code
    if (team.name) teamNames[teamId] = team.name
  }

  return {
    snapshots,
    profile,
    courseLength: first.course_length,
    maxTicks: snapshots.length - 1,
    tickInterval: first.tick_interval,
    teamCodes,
    teamNames,
  }
}