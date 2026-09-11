/**
 * Hard-coded fixtures, copied from the design mockup.
 *
 * NOTHING here is real. There is no API yet; this module exists so that every
 * invented value in the UI sits in one file rather than being scattered
 * through the components. When the endpoints land, the screens keep their
 * shapes and this file is replaced by fetches — that is the whole point of
 * keeping it separate.
 */

import type { InboxTag, RiderStatus } from './theme'

// --- Team identity --------------------------------------------------------

export const TEAM = {
  name: 'Vallée Cycling',
  code: 'VC',
  tier: 'CONTINENTAL · DIV 2',
  budget: '€1.84M',
  manager: 'manager_rob',
  // Now only a fallback for the Sidebar footer, shown while the real game
  // clock (GET /api/world/clock/, see useClock.ts) is loading or unreachable.
  // DASHBOARD.eyebrow below still uses this invented season directly.
  season: 'SEASON 3 · WK 14',
} as const

// --- Dashboard ------------------------------------------------------------

export const DASHBOARD = {
  eyebrow: 'SEASON 3 · WEEK 14 OF 38',
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

// --- Roster ---------------------------------------------------------------

/**
 * The five attributes the race engine reads, in the order the design shows
 * them. `ATTR_KEYS` are the compact card labels, `ATTR_LABELS` the full names
 * used in the detail panel.
 */
export const ATTR_KEYS = ['CLB', 'SPR', 'FLT', 'RES', 'POS'] as const
export const ATTR_LABELS = ['Climb', 'Sprint', 'Flat', 'Resistance', 'Positioning'] as const

export type Speciality = 'Climber' | 'Sprinter' | 'Rouleur' | 'Puncheur' | 'Domestique'

export interface Rider {
  id: string
  name: string
  age: number
  /** 'Leader' or 'Support' — the rider's standing in the squad. */
  role: string
  spec: Speciality
  /** Five values 0-100, ordered to match `ATTR_KEYS`. */
  attrs: number[]
  form: number
  condition: number
  /** Contract years remaining. */
  years: number
  wage: string
  value: string
  status: RiderStatus
  /** Mean of `attrs`, precomputed at module load. */
  ovr: number
}

type RiderSeed = [
  name: string,
  age: number,
  role: string,
  spec: Speciality,
  attrs: number[],
  form: number,
  condition: number,
  years: number,
  wage: string,
  value: string,
  status: RiderStatus,
]

const RIDER_SEEDS: RiderSeed[] = [
  ['Mira Kestrel', 27, 'Leader', 'Climber', [94, 38, 61, 86, 72], 92, 97, 2, '€480k', '€2.4M', 'fit'],
  ['Anders Bergström', 31, 'Support', 'Rouleur', [58, 52, 91, 84, 88], 78, 94, 1, '€310k', '€1.1M', 'fit'],
  ['Tunde Okafor', 24, 'Leader', 'Sprinter', [31, 93, 82, 64, 79], 54, 88, 3, '€395k', '€2.1M', 'fit'],
  ['Renzo Vance', 29, 'Support', 'Domestique', [64, 41, 76, 90, 83], 66, 71, 2, '€180k', '€620k', 'injured'],
  ['Luca Duarte', 22, 'Support', 'Climber', [81, 29, 55, 68, 58], 71, 96, 4, '€120k', '€880k', 'fit'],
  ['Jonas Hoffmann', 33, 'Support', 'Rouleur', [49, 58, 88, 79, 85], 63, 92, 1, '€240k', '€410k', 'fit'],
  ['Émile Rouvier', 26, 'Leader', 'Puncheur', [77, 66, 74, 72, 76], 84, 95, 2, '€330k', '€1.6M', 'fit'],
  ['Kaito Mori', 25, 'Support', 'Sprinter', [34, 84, 86, 61, 81], 69, 90, 2, '€215k', '€940k', 'fit'],
  ['Piet Vandaele', 28, 'Support', 'Domestique', [55, 47, 83, 88, 74], 58, 86, 1, '€165k', '€520k', 'tired'],
  ['Nikola Havel', 30, 'Support', 'Climber', [86, 26, 52, 81, 63], 75, 93, 3, '€275k', '€1.2M', 'fit'],
  ['Sam Whitlock', 23, 'Support', 'Rouleur', [52, 61, 79, 66, 70], 61, 98, 4, '€105k', '€560k', 'fit'],
  ['Ciro Battaglia', 34, 'Support', 'Puncheur', [70, 55, 71, 77, 80], 47, 84, 1, '€190k', '€230k', 'tired'],
  ['Otto Lindqvist', 21, 'Support', 'Climber', [74, 33, 48, 59, 54], 66, 99, 4, '€95k', '€640k', 'fit'],
  ['Marcel Aubin', 27, 'Support', 'Domestique', [60, 44, 80, 85, 87], 72, 91, 2, '€175k', '€580k', 'fit'],
  ['Diego Ferrán', 29, 'Leader', 'Sprinter', [28, 89, 84, 67, 82], 80, 89, 2, '€360k', '€1.8M', 'fit'],
  ['Tomas Brandt', 26, 'Support', 'Rouleur', [57, 50, 86, 80, 78], 64, 94, 3, '€200k', '€730k', 'fit'],
  ['Yusuf Demir', 24, 'Support', 'Puncheur', [72, 60, 69, 70, 68], 69, 95, 3, '€150k', '€690k', 'fit'],
  ['Erik Solheim', 32, 'Support', 'Domestique', [62, 39, 77, 89, 81], 55, 87, 1, '€170k', '€300k', 'injured'],
]

export const SQUAD: Rider[] = RIDER_SEEDS.map(
  ([name, age, role, spec, attrs, form, condition, years, wage, value, status], i) => ({
    id: `r${i}`,
    name,
    age,
    role,
    spec,
    attrs,
    form,
    condition,
    years,
    wage,
    value,
    status,
    ovr: Math.round(attrs.reduce((a, b) => a + b, 0) / attrs.length),
  }),
)

export const SPEC_FILTERS: Array<'All' | Speciality> = [
  'All',
  'Climber',
  'Sprinter',
  'Rouleur',
  'Puncheur',
  'Domestique',
]

export type SortKey = 'ovr' | 'form' | 'age' | 'wage' | 'name'

export const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: 'ovr', label: 'Overall' },
  { key: 'form', label: 'Form' },
  { key: 'age', label: 'Age' },
  { key: 'wage', label: 'Wage' },
  { key: 'name', label: 'Name' },
]

/** The wage bill is a fixed string in the design rather than a sum. */
export const WAGE_BILL = '€4.0M'
