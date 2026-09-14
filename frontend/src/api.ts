/**
 * The SPA's first fetch. Relative URLs throughout: `vite.config.ts` proxies
 * `/api` to Django on :8000 in dev, and in production Django serves both.
 */

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`))
  return match ? decodeURIComponent(match[2]) : null
}

/**
 * Django sets the `csrftoken` cookie on any response from a view touched by
 * CsrfViewMiddleware; GET /api/accounts/me/ is @ensure_csrf_cookie so one
 * call is enough to guarantee it exists before the SPA issues a write.
 * DRF's SessionAuthentication enforces CSRF only for authenticated
 * sessions, so this only matters once someone is logged in — but it must
 * hold from the first write onward, so every unsafe request goes through
 * `post`/`put` below rather than a bare `fetch`.
 */
async function ensureCsrfToken(): Promise<string> {
  let token = readCookie('csrftoken')
  if (token) return token
  await fetch('/api/accounts/me/')
  token = readCookie('csrftoken')
  if (!token) {
    throw new Error('no CSRF token available')
  }
  return token
}

/**
 * A DRF validation failure (register's weak-password or duplicate-email
 * case) comes back as {field: [messages]}, not {detail}. Prefer the first
 * field error when there is one; fall back to `detail` for everything else
 * (login's deliberately generic wrong-credentials message, D7).
 */
function errorMessageFrom(parsed: unknown, fallback: string): string {
  if (parsed && typeof parsed === 'object') {
    const body = parsed as Record<string, unknown>
    if (typeof body.detail === 'string') return body.detail
    for (const value of Object.values(body)) {
      if (Array.isArray(value) && typeof value[0] === 'string') return value[0]
    }
  }
  return fallback
}

async function writeJson<T>(url: string, method: 'POST' | 'PUT', body?: unknown): Promise<T> {
  const csrfToken = await ensureCsrfToken()
  const response = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const parsed = await response.json().catch(() => null)
    throw new Error(errorMessageFrom(parsed, `${method} ${url} failed: ${response.status}`))
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json()
}

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

export interface MeTeam {
  id: number
  name: string
  code: string
}

export interface Me {
  authenticated: boolean
  display_name: string | null
  team: MeTeam | null
}

export async function getMe(): Promise<Me> {
  const response = await fetch('/api/accounts/me/')
  if (!response.ok) {
    throw new Error(`me request failed: ${response.status}`)
  }
  return response.json()
}

/**
 * accounts/ cannot know about teams/ (see AGENTS.md's dependency direction,
 * and specs/player-accounts-plan.md D9), so register/login only confirm the
 * display name — not the full Me shape. Callers that need the team (or the
 * `authenticated` flag) follow up with getMe(), which is where that answer
 * actually lives.
 */
interface AuthConfirmation {
  display_name: string
}

export async function register(email: string, password: string, displayName: string): Promise<AuthConfirmation> {
  return writeJson('/api/accounts/register/', 'POST', {
    email,
    password,
    display_name: displayName,
  })
}

export async function login(email: string, password: string): Promise<AuthConfirmation> {
  return writeJson('/api/accounts/login/', 'POST', { email, password })
}

export async function logout(): Promise<void> {
  return writeJson('/api/accounts/logout/', 'POST')
}

export interface SquadRider {
  id: number
  name: string
  role: 'leader' | 'support'
  speciality: string
  age: number
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

export async function getSquad(raceId: number): Promise<Squad> {
  const response = await fetch(`/api/racing/races/${raceId}/squad/`)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `squad request failed: ${response.status}`)
  }
  return response.json()
}

export async function putSquad(raceId: number, riderIds: number[], leaderId: number): Promise<Squad> {
  return writeJson(`/api/racing/races/${raceId}/squad/`, 'PUT', {
    rider_ids: riderIds,
    leader_id: leaderId,
  })
}

/** Ratings are the 0-10 display scale — see riders/display.py. The five
 * hidden traits (potential, peak age, decline rate, injury proneness,
 * training affinity) never reach this client at all. */
export interface Rider {
  id: number
  name: string
  role: 'leader' | 'support'
  speciality: string
  nationality: string
  age: number
  height_cm: number
  weight_kg: number
  climb: number
  sprint: number
  flat: number
  resistance: number
  positioning: number
}

export async function getRiders(): Promise<Rider[]> {
  const response = await fetch('/api/riders/')
  if (!response.ok) {
    throw new Error(`riders request failed: ${response.status}`)
  }
  return response.json()
}
