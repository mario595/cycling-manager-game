import { Fragment } from 'react'

import type { AttributeSnapshot, CurrentWeek, Rider } from '../api'
import { attributeColor, color, font } from '../theme'
import type { AttrKey } from './AttributeRadar'

/** climb, sprint, flat, resistance, positioning — same order as the radar's
 * axes, so the legend lines up with it. */
const AXES: Array<{ key: AttrKey; label: string }> = [
  { key: 'climb', label: 'Climb' },
  { key: 'sprint', label: 'Sprint' },
  { key: 'flat', label: 'Flat' },
  { key: 'resistance', label: 'Resistance' },
  { key: 'positioning', label: 'Positioning' },
]

/** Mirrors schedule.models.SEASON_WEEKS — a season is always twelve weeks. */
const SEASON_WEEKS = 12

export interface HistoryPoint {
  x: number
  label: string
  values: Record<AttrKey, number>
}

function attrValues(source: Pick<Rider, AttrKey>): Record<AttrKey, number> {
  return {
    climb: source.climb,
    sprint: source.sprint,
    flat: source.flat,
    resistance: source.resistance,
    positioning: source.positioning,
  }
}

function weekX(season: number, week: number): number {
  return (season - 1) * SEASON_WEEKS + week
}

/**
 * Turns the raw attribute-history payload into the step chart's points —
 * pure, exported for tests. The baseline (week=null) sits one unit before
 * the first weekly snapshot, or one unit before the current week when
 * there are no weekly snapshots yet, or at 0 when there is no current week
 * either (no season has ever been declared). A final point is always
 * appended carrying the rider's *current* attribute values — never the
 * last snapshot's — so the chart's right-hand end always agrees with the
 * radar (D7).
 */
export function historySeries(
  history: AttributeSnapshot[],
  current: Pick<Rider, AttrKey>,
  currentWeek: CurrentWeek | null,
): { xMax: number; points: HistoryPoint[] } {
  const baseline = history.find((snapshot) => snapshot.week === null) ?? null
  const weekly = history.filter(
    (snapshot): snapshot is AttributeSnapshot & { season: number; week: number } =>
      snapshot.week !== null && snapshot.season !== null,
  )

  const currentX = currentWeek ? weekX(currentWeek.season, currentWeek.week) : 0
  const firstWeeklyX = weekly.length > 0 ? weekX(weekly[0].season, weekly[0].week) : null
  const baselineX = firstWeeklyX !== null ? firstWeeklyX - 1 : currentWeek ? currentX - 1 : 0

  const points: HistoryPoint[] = []
  if (baseline) {
    points.push({ x: baselineX, label: 'Start', values: attrValues(baseline) })
  }
  for (const snapshot of weekly) {
    points.push({
      x: weekX(snapshot.season, snapshot.week),
      label: `S${snapshot.season} W${snapshot.week}`,
      values: attrValues(snapshot),
    })
  }
  points.push({
    x: currentWeek ? currentX : baselineX,
    label: currentWeek ? `S${currentWeek.season} W${currentWeek.week}` : 'Now',
    values: attrValues(current),
  })

  return { xMax: points[points.length - 1].x, points }
}

const WIDTH = 560
const HEIGHT = 200
const PAD_LEFT = 24
const PAD_RIGHT = 12
const PAD_TOP = 10
const PAD_BOTTOM = 26
const PLOT_WIDTH = WIDTH - PAD_LEFT - PAD_RIGHT
const PLOT_HEIGHT = HEIGHT - PAD_TOP - PAD_BOTTOM

function xPixel(x: number, xMax: number): number {
  if (xMax === 0) return PAD_LEFT
  return PAD_LEFT + (x / xMax) * PLOT_WIDTH
}

function yPixel(value: number): number {
  return PAD_TOP + PLOT_HEIGHT - (value / 10) * PLOT_HEIGHT
}

/** A step path — the value holds until the next recorded point, then
 * jumps — never a sloped line, which would invent an intermediate value
 * the display scale never showed (D8). `xMax === 0` (no season has ever
 * been declared) draws the one recorded value as a flat line across the
 * chart's full width, per the backend's "no_season" rule. */
function stepPath(points: HistoryPoint[], key: AttrKey, xMax: number): string {
  if (points.length === 0) return ''
  if (xMax === 0) {
    const y = yPixel(points[0].values[key])
    return `M ${PAD_LEFT} ${y} L ${WIDTH - PAD_RIGHT} ${y}`
  }
  let d = `M ${xPixel(points[0].x, xMax)} ${yPixel(points[0].values[key])}`
  for (let i = 1; i < points.length; i++) {
    const holdY = yPixel(points[i - 1].values[key])
    const x = xPixel(points[i].x, xMax)
    const y = yPixel(points[i].values[key])
    d += ` L ${x} ${holdY} L ${x} ${y}`
  }
  return d
}

export function AttributeHistoryChart({
  history,
  current,
  currentWeek,
}: {
  history: AttributeSnapshot[]
  current: Pick<Rider, AttrKey>
  currentWeek: CurrentWeek | null
}) {
  const { xMax, points } = historySeries(history, current, currentWeek)
  const first = points[0]
  const last = points[points.length - 1]
  const onlyBaseline = history.length <= 1

  return (
    <div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%" role="img" aria-label="Attribute history">
        {Array.from({ length: 11 }, (_, v) => {
          const y = yPixel(v)
          return (
            <Fragment key={v}>
              <line x1={PAD_LEFT} y1={y} x2={WIDTH - PAD_RIGHT} y2={y} stroke={color.divider} strokeWidth={1} />
              {v % 5 === 0 ? (
                <text x={PAD_LEFT - 6} y={y} textAnchor="end" dominantBaseline="middle" fontSize={9} fontFamily={font.mono} fill={color.muted}>
                  {v}
                </text>
              ) : null}
            </Fragment>
          )
        })}
        {AXES.map((axis) => (
          <path
            key={axis.key}
            d={stepPath(points, axis.key, xMax)}
            fill="none"
            stroke={attributeColor[axis.key]}
            strokeWidth={2}
          />
        ))}
        {first ? (
          <text x={xPixel(first.x, xMax)} y={HEIGHT - 6} textAnchor="start" fontSize={10} fontFamily={font.mono} fill={color.muted}>
            {first.label}
          </text>
        ) : null}
        {last && last !== first ? (
          <text x={xPixel(last.x, xMax)} y={HEIGHT - 6} textAnchor="end" fontSize={10} fontFamily={font.mono} fill={color.muted}>
            {last.label}
          </text>
        ) : null}
      </svg>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 8 }}>
        {AXES.map((axis) => (
          <div key={axis.key} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 9, height: 9, borderRadius: 2, background: attributeColor[axis.key] }} />
            <span style={{ fontSize: 11, color: color.muted, fontFamily: font.mono }}>{axis.label}</span>
          </div>
        ))}
      </div>
      {onlyBaseline ? (
        <div style={{ fontSize: 12, color: color.muted, marginTop: 6 }}>
          Recording began at the start of this rider's history; no change yet.
        </div>
      ) : null}
    </div>
  )
}
