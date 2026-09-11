/**
 * The SPA's first fetch. Relative URLs throughout: `vite.config.ts` proxies
 * `/api` to Django on :8000 in dev, and in production Django serves both.
 */

export interface Clock {
  current: string
  catch_up_hours: number
  last_tick: string | null
}

export async function getClock(): Promise<Clock> {
  const response = await fetch('/api/world/clock/')
  if (!response.ok) {
    throw new Error(`clock request failed: ${response.status}`)
  }
  return response.json()
}
