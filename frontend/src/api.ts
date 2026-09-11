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
