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
  maxTicks: number
  teamCodes: Record<string, string>
  teamNames: Record<string, string>
}

export interface RaceFile {
  name: string
  mtime: string
}
