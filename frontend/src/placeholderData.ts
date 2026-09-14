/**
 * Hard-coded fixtures, copied from the design mockup.
 *
 * NOTHING here is real. There is no API yet; this module exists so that every
 * invented value in the UI sits in one file rather than being scattered
 * through the components. When the endpoints land, the screens keep their
 * shapes and this file is replaced by fetches — that is the whole point of
 * keeping it separate.
 */

import type { InboxTag } from './theme'

// --- Team identity --------------------------------------------------------

export const TEAM = {
  name: 'Vallée Cycling',
  code: 'VC',
  tier: 'CONTINENTAL · DIV 2',
  budget: '€1.84M',
  manager: 'manager_rob',
  // Now only a fallback for the Sidebar footer, shown while the real game
  // clock (GET /api/world/clock/, see useClock.ts) is loading or unreachable.
  season: 'SEASON 3 · WK 14',
} as const

// --- Dashboard ------------------------------------------------------------

export const DASHBOARD = {
  greeting: 'Good morning, Rob.',
  subtitle:
    'Two races resolved overnight. Your lineup for Tour de Sancerre is still open.',
  deadline: '5h 42m',
} as const

export interface HeadlineStat {
  key: string
  value: string
  /** Smaller trailing text, e.g. the "/16" after a rank. */
  suffix?: string
}

export const HEADLINE_STATS: HeadlineStat[] = [
  { key: 'BUDGET', value: '€1.84M' },
  { key: 'DIV 2 RANK', value: '4', suffix: '/16' },
]

export interface ResultRow {
  pos: string
  rider: string
  role: string
  race: string
  pts: string
}

export const RESULTS: ResultRow[] = [
  { pos: '1st', rider: 'M. Kestrel', role: 'GC CLIMBER', race: 'GP de Verrières', pts: '+60' },
  { pos: '7th', rider: 'A. Bergström', role: 'ROULEUR', race: 'GP de Verrières', pts: '+14' },
  { pos: '3rd', rider: 'T. Okafor', role: 'SPRINTER', race: "Circuit d'Aubain", pts: '+32' },
  { pos: '12th', rider: 'R. Vance', role: 'DOMESTIQUE', race: "Circuit d'Aubain", pts: '+4' },
]

export interface TableRow {
  rank: number
  team: string
  pts: string
  /** True for the player's own team, which gets a tinted row. */
  me?: boolean
}

export const LEAGUE_TABLE: TableRow[] = [
  { rank: 1, team: 'Nordkap Pro', pts: '418' },
  { rank: 2, team: 'Auroch Racing', pts: '390' },
  { rank: 3, team: 'Kessel Sport', pts: '361' },
  { rank: 4, team: 'Vallée Cycling', pts: '344', me: true },
  { rank: 5, team: 'Marchal Équipe', pts: '330' },
  { rank: 6, team: 'Bergline', pts: '302' },
]

export interface FormRow {
  name: string
  role: string
  value: number
  delta: string
}

export const FORM_WATCH: FormRow[] = [
  { name: 'M. Kestrel', role: 'GC CLIMBER', value: 92, delta: '+6' },
  { name: 'A. Bergström', role: 'ROULEUR', value: 78, delta: '+2' },
  { name: 'T. Okafor', role: 'SPRINTER', value: 54, delta: '−9' },
  { name: 'R. Vance', role: 'DOMESTIQUE', value: 66, delta: '−1' },
]

export interface InboxRow {
  tag: InboxTag
  title: string
  body: string
  time: string
}

export const INBOX: InboxRow[] = [
  {
    tag: 'TRANSFER',
    title: 'Bid received for T. Okafor',
    body: 'Kessel Sport offer €340k. Expires in 22h.',
    time: '07:04',
  },
  {
    tag: 'MEDICAL',
    title: 'R. Vance — minor knee strain',
    body: 'Out for 6 days. Training load reduced automatically.',
    time: '06:40',
  },
  {
    tag: 'SPONSOR',
    title: 'Objective met: top 5 at a classic',
    body: '€120k bonus paid into your budget.',
    time: '07:00',
  },
]

export const NEXT_RACE = {
  name: 'Tour de Sancerre',
  detail: 'STAGE 1 · 128.4 KM · HILLY',
  countdown: 'IN 5H 42M',
  /** Filled slots first, then the empty ones. */
  lineup: ['Kestrel', 'Bergström', 'Okafor', 'Vance', 'Hoffmann', 'Duarte'],
  lineupSize: 8,
} as const

// --- Course profile -------------------------------------------------------

/** `[length in metres, gradient %]` pairs describing the next race's course. */
export const COURSE_SEGMENTS: ReadonlyArray<readonly [number, number]> = [
  [22000, 0],
  [9000, 2.5],
  [6000, -3],
  [14000, 0],
  [7000, 4.5],
  [5000, -4],
  [18000, 1],
  [8000, 6.5],
  [6000, -5],
  [13000, 0],
  [9000, 7.5],
  [11400, -2],
]

export const COURSE_LENGTH_M = 128400
