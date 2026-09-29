import CourseChart from '../../../race_player/src/components/CourseChart'
import { computeProfile } from '../../../race_player/src/utils/profile'
import type { Segment } from '../../../race_player/src/types/race'

import type { RaceMarker } from '../api'
import { color, font } from '../theme'

const KIND_SYMBOL: Record<RaceMarker['kind'], string> = {
  sprint: 'S',
  mountain: 'M',
}

const KIND_LABEL: Record<RaceMarker['kind'], string> = {
  sprint: 'Sprint',
  mountain: 'Mountain',
}

const WEIGHT_LABEL: Record<NonNullable<RaceMarker['weight']>, string> = {
  minor: 'Minor',
  standard: 'Standard',
  major: 'Major',
}

/** The course as the shared elevation chart — the same derivation and drawing
 * code as the race_player visualizer, imported directly from its source so
 * the calendar and the visualizer can never drift apart. No rider markers
 * here; the race has not necessarily run, and the chart stands alone.
 *
 * Course markers, when present, overlay as dashed vertical lines with a
 * short label at the top margin, and are repeated in a compact list beneath —
 * labels at near or shared distances collide on the chart, and the list is
 * always legible. Nothing extra renders when `markers` is empty or absent. */
export function CourseProfile({
  course,
  markers = [],
}: {
  course: Segment[]
  markers?: RaceMarker[]
}) {
  return (
    <>
      <CourseChart
        profile={computeProfile(course)}
        height={200}
        overlay={(scale, bounds) => (
          <>
            {markers.map((m) => {
              const x = scale.x(m.distance)
              return (
                <g key={m.id}>
                  <line
                    x1={x}
                    y1={scale.y(bounds.minElevation)}
                    x2={x}
                    y2={scale.margin.top}
                    stroke={color.ink}
                    strokeWidth={1}
                    strokeDasharray="4 4"
                  />
                  <text
                    x={x}
                    y={scale.margin.top + 13}
                    textAnchor="middle"
                    fontSize={10}
                    fontWeight={700}
                    fill={color.ink}
                  >
                    {`${KIND_SYMBOL[m.kind]} ${m.name}`}
                  </text>
                </g>
              )
            })}
          </>
        )}
      />
      {markers.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {markers.map((m) => (
            <div key={m.id} style={{ fontSize: 12.5, fontFamily: font.mono, color: color.muted }}>
              {KIND_LABEL[m.kind]} · {m.name} · km {(m.distance / 1000).toFixed(1)}
              {m.weight !== null && m.points !== null ? (
                <> · {WEIGHT_LABEL[m.weight]} · {m.points[0]} pts to the winner</>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </>
  )
}