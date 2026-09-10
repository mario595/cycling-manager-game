export interface Segment {
  length: number
  gradient: number
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
