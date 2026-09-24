import { Fragment } from 'react'

import type { Rider } from '../api'
import { attributeColor, color, font } from '../theme'

export type AttrKey = 'climb' | 'sprint' | 'flat' | 'resistance' | 'positioning'

/** climb, sprint, flat, resistance, positioning — ENGINE_ATTRIBUTES order,
 * matching Roster.tsx and the rider page's history chart legend. */
const AXES: Array<{ key: AttrKey; label: string }> = [
  { key: 'climb', label: 'Climb' },
  { key: 'sprint', label: 'Sprint' },
  { key: 'flat', label: 'Flat' },
  { key: 'resistance', label: 'Resistance' },
  { key: 'positioning', label: 'Positioning' },
]

const RINGS = 10
// Wide enough that a long axis label ("Positioning") never clips the
// viewBox — an SVG root clips at its own bounds by default.
const SIZE = 300
const CENTER = SIZE / 2
const RADIUS = 90

/**
 * Vertex positions for a five-axis radar: axis 0 straight up, each
 * following axis 72° clockwise, value `v` (0-10) sitting at
 * `radius * v / 10`. Pure and exported for tests. Returned relative to the
 * origin (0,0) — the component translates by the chart's own centre.
 */
export function radarVertices(values: number[], radius: number): Array<[number, number]> {
  return values.map((value, i) => {
    const angle = ((-90 + i * 72) * Math.PI) / 180
    const r = (radius * value) / 10
    return [r * Math.cos(angle), r * Math.sin(angle)]
  })
}

/**
 * A rider's five attributes as a hand-written SVG radar — ten whole-step
 * rings, one polygon, each vertex's integer value printed beside it. The
 * input values are already integers from the API; this component never
 * interpolates, smooths or animates between them (spec: "points only on
 * whole numbers"). No chart dependency.
 */
export function AttributeRadar({ rider }: { rider: Pick<Rider, AttrKey> }) {
  const values = AXES.map((axis) => rider[axis.key])
  const vertices = radarVertices(values, RADIUS)
  const points = vertices.map(([x, y]) => `${CENTER + x},${CENTER + y}`).join(' ')

  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width="100%" role="img" aria-label="Attribute radar">
      {Array.from({ length: RINGS }, (_, i) => {
        const step = i + 1
        const strong = step === 5 || step === 10
        return (
          <circle
            key={step}
            cx={CENTER}
            cy={CENTER}
            r={(RADIUS * step) / RINGS}
            fill="none"
            stroke={strong ? color.border : color.divider}
            strokeWidth={strong ? 1.2 : 1}
          />
        )
      })}
      {AXES.map((axis, i) => {
        const angle = ((-90 + i * 72) * Math.PI) / 180
        const x = CENTER + RADIUS * Math.cos(angle)
        const y = CENTER + RADIUS * Math.sin(angle)
        const labelX = CENTER + (RADIUS + 20) * Math.cos(angle)
        const labelY = CENTER + (RADIUS + 20) * Math.sin(angle)
        return (
          <Fragment key={axis.key}>
            <line x1={CENTER} y1={CENTER} x2={x} y2={y} stroke={color.border} strokeWidth={1} />
            <text
              x={labelX}
              y={labelY}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={10.5}
              fontFamily={font.mono}
              fill={color.muted}
            >
              {axis.label}
            </text>
          </Fragment>
        )
      })}
      <polygon
        points={points}
        fill={color.accent}
        fillOpacity={0.28}
        stroke={color.accent}
        strokeWidth={2}
      />
      {vertices.map(([x, y], i) => {
        const axis = AXES[i]
        return (
          <Fragment key={axis.key}>
            <circle cx={CENTER + x} cy={CENTER + y} r={3} fill={attributeColor[axis.key]} />
            <text
              x={CENTER + x}
              y={CENTER + y - 10}
              textAnchor="middle"
              fontSize={11}
              fontWeight={600}
              fontFamily={font.mono}
              fill={color.ink}
            >
              {values[i]}
            </text>
          </Fragment>
        )
      })}
    </svg>
  )
}
