/**
 * The SPA's first fetch. Relative URLs throughout: `vite.config.ts` proxies
 * `/api` to Django on :8000 in dev, and in production Django serves both.
 */

export interface Clock {
  current: string
}

export async function getClock(): Promise<Clock> {
  const response = await fetch('/api/world/clock/')
  if (!response.ok) {
    throw new Error(`clock request failed: ${response.status}`)
  }
  return response.json()
}

export interface Position {
  state: 'in_season' | 'off_season' | 'no_season'
  season: number | null
  week: number | null
  week_ends_at: string | null
}

export async function getPosition(): Promise<Position> {
  const response = await fetch('/api/schedule/position/')
  if (!response.ok) {
    throw new Error(`position request failed: ${response.status}`)
  }
  return response.json()
}

export interface CalendarRace {
  id: number
  name: string
  starts_at: string | null
  status: 'scheduled' | 'running' | 'finished' | 'failed'
  distance_km: number
}

export interface CalendarWeek {
  number: number
  starts_at: string
  races: CalendarRace[]
}

export interface Calendar {
  state: 'in_season' | 'off_season' | 'no_season'
  season: number | null
  current_week: number | null
  weeks: CalendarWeek[]
}

export async function getCalendar(): Promise<Calendar> {
  const response = await fetch('/api/schedule/calendar/')
  if (!response.ok) {
    throw new Error(`calendar request failed: ${response.status}`)
  }
  return response.json()
}

export interface SquadRider {
  id: number
  name: string
  role: 'leader' | 'support'
  climb: number
  sprint: number
  flat: number
  resistance: number
  positioning: number
  selected: boolean
  is_leader: boolean
}

export interface Squad {
  race: number
  race_name: string
  race_status: 'scheduled' | 'running' | 'finished' | 'failed'
  starts_at: string | null
  distance_km: number
  team: number
  team_name: string
  editable: boolean
  saved: boolean
  squad_size: number
  candidates: SquadRider[]
}

async function squadResponseOrThrow(response: Response): Promise<Squad> {
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `squad request failed: ${response.status}`)
  }
  return response.json()
}

export async function getSquad(raceId: number, teamId: number): Promise<Squad> {
  const response = await fetch(`/api/racing/races/${raceId}/squads/${teamId}/`)
  return squadResponseOrThrow(response)
}

export async function putSquad(
  raceId: number,
  teamId: number,
  riderIds: number[],
  leaderId: number,
): Promise<Squad> {
  const response = await fetch(`/api/racing/races/${raceId}/squads/${teamId}/`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rider_ids: riderIds, leader_id: leaderId }),
  })
  return squadResponseOrThrow(response)
}
