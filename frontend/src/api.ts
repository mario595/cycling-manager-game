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

export interface LostTeam {
  spell: number
  name: string
  code: string
  reason: string
  ended_at: string
}

export interface Me {
  authenticated: boolean
  display_name: string | null
  team: MeTeam | null
  lost_team: LostTeam | null
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

export async function claimTeam(name: string, code: string): Promise<MeTeam> {
  return writeJson('/api/teams/claim/', 'POST', { name, code })
}

export async function acknowledgeSpell(spellId: number): Promise<void> {
  return writeJson(`/api/teams/spells/${spellId}/acknowledge/`, 'POST')
}

export interface SquadRider {
  id: number
  name: string
  speciality: string
  age: number
  climb: number
  sprint: number
  flat: number
  resistance: number
  positioning: number
  freshness: number
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
 * training affinity) never reach this client at all. `weekly_salary` and
 * `market_value` are both exact whole credits, never mapped onto the
 * display scale — the first is what the rider costs to keep, frozen for
 * the season; the second is what they're worth, recomputed on every read
 * (#31). `release_cost` is what releasing them to the free agent pool
 * charges right now: 0 while the claim cooldown shields them, full
 * severance after it expires, and null when the payload is not the
 * caller's own roster (a free agent, say). `final_season` is true while a
 * season runs and this is the rider's last; they retire when it closes
 * (#42). */
export interface Rider {
  id: number
  name: string
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
  freshness: number
  weekly_salary: number
  market_value: number
  release_cost: number | null
  final_season: boolean
}

/** One rider's wage movement at a season close, whole credits. The keys map
 * from the stored "from"/"to" via source= server-side — a SPA could never
 * read a key named `from` (it is a JavaScript keyword). */
export interface SalaryChange {
  rider_id: number
  rider_name: string
  from_value: number
  to_value: number
}

/** What a season close's re-pricing did to the wage bill: the running total
 * before and after, plus each rider whose wage moved by at least the report
 * threshold. `null` on the roster response until the first season has
 * closed. */
export interface SalaryReview {
  season_number: number
  payroll_before: number
  payroll_after: number
  changes: SalaryChange[]
}

/** The caller's own team's roster: every rider plus the squad's total
 * market value (#31) — a single response so the two can never disagree —
 * and the latest post-season salary review when one exists. */
export interface Roster {
  riders: Rider[]
  squad_value: number
  salary_review: SalaryReview | null
}

export async function getRiders(): Promise<Roster> {
  const response = await fetch('/api/riders/')
  if (!response.ok) {
    throw new Error(`riders request failed: ${response.status}`)
  }
  return response.json()
}

/** A free agent as the transfer market shows it — everything the roster
 * shows about a rider plus the one figure this screen adds: the `signing_fee`
 * the team must pay to bring them in. `release_cost` is always null here:
 * a free agent is on nobody's roster, so there is nothing to release. */
export interface FreeAgent extends Rider {
  signing_fee: number
}

/** The transfer market's whole state in one payload: every free agent plus
 * the caller's balance, so the SPA can disable a Sign it cannot afford —
 * the same both-keys shape Staff uses. */
export interface FreeAgentPool {
  riders: FreeAgent[]
  balance: number
}

export async function getFreeAgents(): Promise<FreeAgentPool> {
  const response = await fetch('/api/transfers/free-agents/')
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `free agents request failed: ${response.status}`)
  }
  return response.json()
}

export async function signFreeAgent(riderId: number): Promise<void> {
  return writeJson('/api/transfers/free-agents/sign/', 'POST', { rider_id: riderId })
}

export async function releaseRider(riderId: number): Promise<void> {
  return writeJson('/api/transfers/riders/release/', 'POST', { rider_id: riderId })
}

/** One bid in an auction's full history — bidding is not anonymous, so
 * every bid carries the team that placed it. */
export interface Bid {
  team_name: string
  amount: number
  placed_at: string
}

/** One live auction as the market screen shows it, including its full
 * bid history. `min_next_bid` is the lowest amount the next bid must
 * clear; `is_own_listing` is true for the caller's own listing, so the
 * SPA can hide the Bid action on it. */
export interface AuctionListing {
  id: number
  rider: Rider
  current_price: number
  min_next_bid: number
  deadline: string
  is_own_listing: boolean
  bids: Bid[]
}

/** The auction market's whole state in one payload: every open auction
 * plus the caller's balance — the same both-keys shape FreeAgentPool
 * uses. */
export interface AuctionMarket {
  auctions: AuctionListing[]
  balance: number
}

export async function getAuctions(): Promise<AuctionMarket> {
  const response = await fetch('/api/transfers/auctions/')
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `auctions request failed: ${response.status}`)
  }
  return response.json()
}

export async function listForAuction(riderId: number): Promise<void> {
  return writeJson('/api/transfers/auctions/list/', 'POST', { rider_id: riderId })
}

export async function placeBid(auctionId: number, amount: number): Promise<void> {
  return writeJson(`/api/transfers/auctions/${auctionId}/bid/`, 'POST', { amount })
}

/** One auction the caller's team has an active bid on — backs the outbid
 * notice. `is_high_bidder` goes false the moment someone else clears the
 * caller's last bid. */
export interface MyBidStatus {
  auction_id: number
  rider_name: string
  my_last_bid: number
  current_price: number
  is_high_bidder: boolean
  deadline: string
}

export async function getMyBids(): Promise<MyBidStatus[]> {
  const response = await fetch('/api/transfers/auctions/mine/')
  if (!response.ok) {
    throw new Error(`my bids request failed: ${response.status}`)
  }
  return response.json()
}

export interface RaceResultTeam {
  id: number
  name: string
  code: string
}

/** One point on the attribute-history chart — already the 0-10 display
 * scale, never re-mapped. `season`/`week` are both null for the baseline,
 * the snapshot taken at the rider's creation. */
export interface AttributeSnapshot {
  season: number | null
  week: number | null
  climb: number
  sprint: number
  flat: number
  resistance: number
  positioning: number
}

export interface CurrentWeek {
  season: number
  week: number
}

export interface RiderRetired {
  season: number | null
  week: number | null
}

/** One race-history row. `team` is the team the rider raced for, not their
 * current team — a released or re-signed rider's past rows never change.
 * No points field: race points are a team award, not an individual one. */
export interface RiderRace {
  race: { id: number; name: string; starts_at: string | null }
  team: RaceResultTeam | null
  position: number
  finish_time: number | null
  winner_time: number | null
  finished: boolean
}

/** Career totals derived from the same race list the page shows. No points
 * field, for the same reason RiderRace has none. */
export interface Career {
  starts: number
  wins: number
  podiums: number
  top_tens: number
  dnfs: number
}

/** One rider's full profile: everything Rider already carries, plus their
 * current team (null for a free agent), where the world is now, the
 * retirement details (null while active), the attribute-history chart's
 * points, the race history and the career totals. Identical for every
 * viewer — no field is redacted based on who is looking. */
export interface RiderProfile extends Rider {
  team: RaceResultTeam | null
  current_week: CurrentWeek | null
  retired: RiderRetired | null
  attribute_history: AttributeSnapshot[]
  races: RiderRace[]
  career: Career
}

/** Thrown by getRiderProfile on a 404 — the rider no longer exists because
 * they were deleted without ever racing. A retired rider still returns 200.
 * The hook exposes this as a separate `notFound` state, not folded into a
 * generic error, so the page can explain the absence rather than show a
 * broken-page state. */
export class RiderNotFound extends Error {}

export async function getRiderProfile(riderId: number): Promise<RiderProfile> {
  const response = await fetch(`/api/riders/${riderId}/`)
  if (response.status === 404) {
    throw new RiderNotFound()
  }
  if (!response.ok) {
    throw new Error(`rider profile request failed: ${response.status}`)
  }
  return response.json()
}

export interface RaceResultEntry {
  position: number
  rider: { id: number; name: string }
  team: RaceResultTeam | null
  finish_time: number | null
  finished: boolean
}

export interface RaceResultPointsEntry {
  team: RaceResultTeam
  position: number | null
  finish_points: number
  sprint_points: number
  points: number
  prize: number
}

export interface RaceMarker {
  id: number
  kind: 'sprint' | 'mountain'
  name: string
  distance: number
  /** Null for a mountain marker — #17 decides what one is worth. */
  weight: 'minor' | 'standard' | 'major' | null
  /** Points by crossing position (1st, 2nd, ...), or null for a mountain marker. */
  points: number[] | null
}

export interface RaceMarkerCrossing {
  position: number
  rider: { id: number; name: string }
  team: RaceResultTeam | null
  /** Null for a mountain crossing, or a sprint crossing whose teammate
   * already scored the team's one row at this marker. */
  points: number | null
}

export interface RaceMarkerResult extends RaceMarker {
  crossings: RaceMarkerCrossing[]
}

export interface RaceResults {
  race: { id: number; name: string; status: string }
  results: RaceResultEntry[]
  points: RaceResultPointsEntry[]
  markers: RaceMarkerResult[]
}

export async function getRaceResults(raceId: number): Promise<RaceResults> {
  const response = await fetch(`/api/racing/races/${raceId}/results/`)
  if (!response.ok) {
    throw new Error(`race results request failed: ${response.status}`)
  }
  return response.json()
}

export interface CourseSegment {
  length: number
  gradient: number
}

export interface RacePayoutEntry {
  position: number
  points: number
  prize: number
}

export interface RaceDetail {
  id: number
  name: string
  status: string
  starts_at: string | null
  distance_km: number
  course: CourseSegment[]
  payout: RacePayoutEntry[]
  markers: RaceMarker[]
  /** Whether the server holds a log worth replaying for this race. Always
   * false while the race is unfinished, and false for a finished race
   * recorded before replays existed. */
  has_replay: boolean
}

export async function getRaceDetail(raceId: number): Promise<RaceDetail> {
  const response = await fetch(`/api/racing/races/${raceId}/`)
  if (!response.ok) {
    throw new Error(`race detail request failed: ${response.status}`)
  }
  return response.json()
}

/** The race's recorded log, as text. The server hands back the brotli
 * compressed bytes verbatim or the decompressed body, depending on what the
 * browser sent; both are a race log, so there is nothing to negotiate here.
 * Replay is only for a finished race with a stored log, so a 404 is not
 * "no replay" — it is a failure worth showing (the file vanished), which the
 * caller does. */
export async function getRaceLog(raceId: number): Promise<string> {
  const response = await fetch(`/api/racing/races/${raceId}/log/`)
  if (!response.ok) {
    throw new Error(`race log request failed: ${response.status}`)
  }
  return response.text()
}

/** Same state vocabulary as Calendar/Position — see api/README.md. */
export interface Standings {
  state: 'in_season' | 'off_season' | 'no_season'
  season: number | null
  standings: Array<{
    rank: number
    team: RaceResultTeam
    points: number
  }>
}

export async function getStandings(): Promise<Standings> {
  const response = await fetch('/api/competitions/standings/')
  if (!response.ok) {
    throw new Error(`standings request failed: ${response.status}`)
  }
  return response.json()
}

/** Skills are the 0-10 display scale, same convention as Rider — see
 * riders/display.py. `speciality` is the skill this trainer is best at,
 * derived server-side, not a separate rating. `hire_fee` is the one-off
 * cost of hiring and `weekly_salary` what they cost every week, both
 * derived server-side from the speciality (staff/pricing.py). */
export interface Trainer {
  id: number
  name: string
  nationality: string
  speciality: string
  skills: {
    climb: number
    sprint: number
    flat: number
    resistance: number
    positioning: number
  }
  hire_fee: number
  weekly_salary: number
}

export interface Staff {
  trainer: Trainer | null
  pool: Trainer[]
  balance: number
}

export async function getStaff(): Promise<Staff> {
  const response = await fetch('/api/staff/')
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `staff request failed: ${response.status}`)
  }
  return response.json()
}

export async function hireTrainer(trainerId: number): Promise<void> {
  return writeJson('/api/staff/trainer/hire/', 'POST', { trainer_id: trainerId })
}

export async function fireTrainer(): Promise<void> {
  return writeJson('/api/staff/trainer/fire/', 'POST')
}

/** One rider's visible movement at a rollover — display scale only, matching
 * riders/display.py. Hidden traits (training affinity, etc.) never reach this
 * client at all. */
export interface TrainingChange {
  rider_id: number
  rider_name: string
  attribute: string
  from_value: number
  to_value: number
}

/** The Training screen's whole state in one payload. `last_week` is null
 * until the first rollover, then the focus that was applied plus its visible
 * changes. */
export interface TrainingState {
  has_trainer: boolean
  focus: string | null
  options: string[]
  last_week: {
    attribute: string
    changes: TrainingChange[]
  } | null
}

export async function getTraining(): Promise<TrainingState> {
  const response = await fetch('/api/staff/training/')
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `training request failed: ${response.status}`)
  }
  return response.json()
}

export async function setTrainingFocus(attribute: string): Promise<void> {
  return writeJson('/api/staff/training/', 'PUT', { attribute })
}

/** One ledger entry as the Finances screen needs it. `kind` is the machine
 * name (starting_balance/wages/takeover/prize_money/merchandise/
 * sponsorship/trainer_fee/trainer_salary/transfer_fee/development_squad/
 * development_squad_fee); the screen renders the label. `rider_count` is set
 * on wage entries only — null elsewhere. `balance_after` is computed
 * server-side: the running balance just after this entry. */
export interface LedgerEntry {
  id: number
  kind:
    | 'starting_balance'
    | 'wages'
    | 'takeover'
    | 'prize_money'
    | 'merchandise'
    | 'sponsorship'
    | 'trainer_fee'
    | 'trainer_salary'
    | 'transfer_fee'
    | 'development_squad'
    | 'development_squad_fee'
  description: string
  amount: number
  occurred_at: string | null
  rider_count: number | null
  balance_after: number
}

/** A team's whole financial state in one payload: the running balance and
 * its full history, newest first, plus the team's fanbase and how it moved
 * this week (`fanbase_change` is 0 before the first weekly row — the server
 * sends the change, not two raw numbers to diff), and `weekly_wage_bill` —
 * the roster's current payroll, not the ledger's last wages entry. */
export interface Finances {
  balance: number
  fanbase: number
  fanbase_change: number
  weekly_wage_bill: number
  entries: LedgerEntry[]
}

export async function getFinances(): Promise<Finances> {
  const response = await fetch('/api/economy/finances/')
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `finances request failed: ${response.status}`)
  }
  return response.json()
}

/** One unsigned sponsor offer, or (via SponsorContract) the signed one —
 * same money shape either way, matching economy/sponsors.py's terms. */
export interface SponsorOffer {
  id: number
  sponsor_name: string
  profile: string
  label: string
  blurb: string
  weekly_base: number
  floor_amount: number
  ceiling_amount: number
}

export interface SponsorContract {
  sponsor_name: string
  profile: string
  label: string
  blurb: string
  weekly_base: number
  floor_amount: number
  ceiling_amount: number
  signed_at: string
}

export interface Sponsors {
  contract: SponsorContract | null
  offers: SponsorOffer[]
}

export async function getSponsors(): Promise<Sponsors> {
  const response = await fetch('/api/economy/sponsors/')
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `sponsors request failed: ${response.status}`)
  }
  return response.json()
}

export async function signOffer(offerId: number): Promise<void> {
  return writeJson('/api/economy/sponsors/sign/', 'POST', { offer_id: offerId })
}

/** One development squad level, as the server prices and gates it.
 *
 * `fee` is what moving onto this level costs — the same figure the ledger is
 * debited, whether that move is the opening or an upgrade, and null-free so
 * the screen never has to invent a price for a move it cannot make.
 *
 * `action` is the ladder rule as the server states it, and the SPA renders it
 * rather than working it out: `open` on the entry level of a closed squad,
 * `upgrade` on the single rung above the one held, `current` on the one held,
 * `locked` on everything else. `requires` says what a locked level is waiting
 * for, and is null for every other action. The two kinds of lock are different
 * advice, which is why the note comes from the server too. */
export type DevelopmentSquadAction = 'open' | 'upgrade' | 'current' | 'locked'

export interface DevelopmentSquadLevel {
  level: number
  name: string
  weekly_cost: number
  season_cost: number
  fee: number
  action: DevelopmentSquadAction
  requires: string | null
}

/** The Development squad screen's whole state: `level` is null while the
 * squad is closed (not an error — a state the screen exists to show), and
 * `balance` is here so an action the team cannot afford can be disabled
 * without a second round trip. */
export interface DevelopmentSquad {
  level: number | null
  levels: DevelopmentSquadLevel[]
  balance: number
}

export async function getDevelopmentSquad(): Promise<DevelopmentSquad> {
  const response = await fetch('/api/development-squad/')
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `development squad request failed: ${response.status}`)
  }
  return response.json()
}

export async function openDevelopmentSquad(level: number): Promise<void> {
  return writeJson('/api/development-squad/open/', 'POST', { level })
}

export async function changeDevelopmentSquadLevel(level: number): Promise<void> {
  return writeJson('/api/development-squad/level/', 'POST', { level })
}

/** POST, not DELETE: closing deletes the squad row, but the opening fee
 * already paid stays in the ledger, so nothing here is destroyed. */
export async function closeDevelopmentSquad(): Promise<void> {
  return writeJson('/api/development-squad/close/', 'POST')
}
