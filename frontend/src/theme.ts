/**
 * Design tokens lifted from `design/Cycling Manager UI.dc.html`.
 *
 * The design is authored as one file of inline styles with the hex codes
 * repeated inline. Rather than copy those literals across every component,
 * they are named once here. If the design is re-exported, this is the file
 * to reconcile against it.
 */

export const color = {
  /** Page background. */
  canvas: '#F4F5F7',
  /** Cards, panels, anything raised off the canvas. */
  surface: '#FFFFFF',
  /** Sidebar background — very slightly darker than the canvas. */
  rail: '#ECEEF1',
  /** Body text and the dark buttons. */
  ink: '#2A2D33',
  /** Dark button hover. */
  inkHover: '#1E2127',
  /** Secondary text. */
  muted: '#6F737A',
  /** Labels, the DM Mono captions. */
  mutedStrong: '#5F636B',
  /** Card and panel borders. */
  border: '#E4E6EA',
  /** Row separators inside cards — lighter than `border`. */
  divider: '#F1F3F5',
  /** Slightly stronger divider, used under card headers. */
  dividerStrong: '#EDEFF2',
  /** Sidebar border. */
  railBorder: '#E1E4E8',
  /** Secondary button border. */
  borderButton: '#DFE3E7',
  /** The brand accent. */
  accent: '#EBA76B',
  /** Accent-on-light text, e.g. eyebrow labels and links. */
  accentInk: '#7A4520',
  /** Tinted row background for "your team" highlights. */
  accentWash: '#FCF1E8',
  /** Positive — good form, points gained. */
  positive: '#3E8571',
  /** Negative — lost form, cracking riders. */
  negative: '#B4614C',
  /** Empty track behind a progress bar. */
  track: '#EDEFF2',
  /** A filled bar with no status meaning. */
  neutralBar: '#CFD3D9',
} as const

export const font = {
  sans: "'Plus Jakarta Sans', system-ui, sans-serif",
  /** Used for every number, label and code-like caption in the design. */
  mono: "'DM Mono', ui-monospace, monospace",
} as const

export const radius = {
  sm: '5px',
  md: '9px',
  lg: '12px',
  xl: '14px',
} as const

/** Status pill colours for a rider's availability. */
export const riderStatus = {
  fit: { label: 'Fit', bg: '#E6F0EC', fg: '#2E6B58' },
  tired: { label: 'Fatigued', bg: '#FCF1E8', fg: '#7A4520' },
  injured: { label: 'Injured', bg: '#FAECE6', fg: '#A0553F' },
} as const

export type RiderStatus = keyof typeof riderStatus

/**
 * The warmer, more saturated accent wash used for "this is happening right
 * now" emphasis on the calendar screen — the current week's rail and row,
 * and the current season's card border/header. Distinct from `accentWash`
 * (a lighter tint used for "your team" rows elsewhere).
 */
export const calendarAccent = {
  /** Current week's row background. */
  rowWash: '#FFFBF6',
  /** Current week's rail background. */
  railWash: '#F6E7D6',
  /** Current week's rail border, and the current season's card border. */
  border: '#E6C9AC',
  /** Current-week rail text. */
  ink: '#7A4520',
  /** Current-season card header background. */
  headerWash: '#FDF8F2',
} as const

/** Below this width the sidebar collapses into a drawer. */
export const MOBILE_BREAKPOINT = 900

/**
 * Colour for a 0-100 attribute bar: green when strong, accent when decent,
 * grey otherwise. Matches the thresholds in the design.
 */
export function barColor(value: number): string {
  if (value >= 80) return color.positive
  if (value >= 60) return color.accent
  return color.neutralBar
}
