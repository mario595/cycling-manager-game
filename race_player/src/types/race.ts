export interface Segment {
  length: number
  gradient: number
}

export type WindBand = 'calm' | 'light' | 'moderate' | 'strong'

/**
 * Wind is modelled relative to the riders, not as a compass bearing.
 * `angle` is where the wind blows FROM, as seen by a rider facing forward:
 * 0 = headwind, 90 = crosswind from the right, 180 = tailwind,
 * 270 = crosswind from the left. There is no north in this model.
 */
export interface Wind {
  speed: number // km/h
  angle: number // degrees [0, 360)
  band: WindBand
}

export interface Rider {
  id: string
  name: string
  team?: string
  role?: 'leader' | 'support'
  pos: number
  speed: number
  energy: number
  stamina: number
  pulling: boolean
  surging: boolean
  finished: boolean
  finish_time: number | null
}

export interface RaceSnapshot {
  time: number
  course_length: number
  segments: Segment[]
  riders: Rider[]
  teams?: Record<string, { code: string; name: string }>
  wind?: Wind
}

export interface RaceHeaderRider {
  id: string
  name: string
  team: string
  role: 'leader' | 'support'
}

/**
 * Line 1 of a race log: everything constant for the race. `riders` is the
 * identity list the positional samples index into — rider *i* in a sample is
 * `header.riders[i]`.
 */
export interface RaceHeader {
  v: number
  tick_interval: number
  course_length: number
  segments: Segment[]
  teams: Record<string, { code: string; name: string }>
  riders: RaceHeaderRider[]
  wind_band?: WindBand
}

/** One rider's per-sample values, positional. `flags` is a bitmask. */
export type RaceRiderSample = [
  pos: number,
  speed: number,
  energy: number,
  stamina: number,
  flags: number,
  finish_time: number | null,
]

/** Every line after the header: `[time, riders, wind?]` (`time` is race seconds). */
export type RaceSample = [
  time: number,
  riders: RaceRiderSample[],
  wind?: [speed: number, angle: number],
]

export interface ProfilePoint {
  distance: number
  elevation: number
  gradient: number
}

export interface Pack {
  riders: Rider[]
  frontPos: number
  speed: number
}

export interface ParsedRace {
  snapshots: RaceSnapshot[]
  profile: ProfilePoint[]
  courseLength: number
  /** Number of sample steps minus the first — actual seconds are `maxTicks * tickInterval`. */
  maxTicks: number
  /** Race seconds between samples; the header states it, the player never assumes it. */
  tickInterval: number
  teamCodes: Record<string, string>
  teamNames: Record<string, string>
}

export interface RaceFile {
  name: string
  mtime: string
}
