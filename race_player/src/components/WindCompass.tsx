import { memo, useEffect, useRef, useState } from 'react'
import type { Wind } from '../types/race'
import { arrowLength, unwrapAngle, windColor, windLabel } from '../utils/wind'

interface WindCompassProps {
  wind: Wind | undefined
}

const SIZE = 110
const CENTER = SIZE / 2
const ROSE_RADIUS = 48

/**
 * The forward marker never rotates — it always points "up", away from the
 * viewer. Only the arrow rotates around it, a direct translation of the
 * engine's rider-relative wind model (WIND_VISUALIZATION_PLAN.md decision
 * 1). No N/S/E/W or HEAD/TAIL/L/R labels — there is no geography in this
 * model, and the readout below (speed + windLabel()) already says which way
 * the wind is coming from in words.
 */
function WindCompass({ wind }: WindCompassProps) {
  const unwrappedAngleRef = useRef<number | null>(null)
  const [displayAngle, setDisplayAngle] = useState(0)

  useEffect(() => {
    if (!wind) return
    const prev = unwrappedAngleRef.current
    const next = prev === null ? wind.angle : unwrapAngle(prev, wind.angle)
    unwrappedAngleRef.current = next
    setDisplayAngle(next)
  }, [wind])

  if (!wind) return null

  const color = windColor(wind.speed)
  const length = arrowLength(wind.speed)
  const thickness = 2 + (length / 34) * 2.5

  // angle=0 (headwind) sits ahead of the marker pointing back at the viewer;
  // angle=180 (tailwind) sits behind pointing away. SVG 0deg rotation points
  // "up" (the rider's forward direction) by construction of the arrow
  // geometry below, so the wind angle maps straight onto a CSS rotation
  // with no extra offset.
  const label = windLabel(wind.angle)
  const title = `${label}, ${wind.speed.toFixed(1)} km/h (${wind.band})`

  return (
    <div
      className="flex flex-col items-center gap-1"
      style={{ width: SIZE }}
      role="img"
      aria-label={title}
    >
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        <title>{title}</title>

        {/* Compass rose backdrop — plain circle, no directional labels. */}
        <circle
          cx={CENTER}
          cy={CENTER}
          r={ROSE_RADIUS}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth={1}
        />

        {/* Forward marker: a simple fixed chevron pointing "up" (the rider's
            direction of travel). Easier to render crisply at this size than
            a bike silhouette, and the convention (an arrow through/at a
            forward-pointing marker) reads instantly without labels. */}
        <g fill="#0f172a">
          <circle cx={CENTER} cy={CENTER} r={5} />
          <polygon
            points={`${CENTER},${CENTER - 16} ${CENTER - 6},${CENTER - 7} ${CENTER + 6},${CENTER - 7}`}
          />
        </g>

        {/* Wind arrow — rotates around the forward marker's centre per the
            angle convention. Smoothed via a CSS transition on transform,
            driven by a continuously-unwrapped angle so a 359->1 wrap takes
            the short way rather than spinning through 180. */}
        <g
          style={{
            transform: `rotate(${displayAngle}deg)`,
            transformOrigin: `${CENTER}px ${CENTER}px`,
            transition: 'transform 120ms linear',
          }}
        >
          {/* The arrow sits above the marker (up, angle=0) at rest and
              points DOWN, toward the rider — i.e. from the wind's origin
              toward the rider, per the angle convention. Rotating this group
              by `angle` degrees then sweeps it to originate from wherever
              the wind is actually coming from. */}
          <line
            x1={CENTER}
            y1={CENTER - ROSE_RADIUS + 6}
            x2={CENTER}
            y2={CENTER - ROSE_RADIUS + 6 + length}
            stroke={color}
            strokeWidth={thickness}
            strokeLinecap="round"
          />
          <polygon
            points={`${CENTER},${CENTER - ROSE_RADIUS + 6 + length + 8} ${CENTER - 4},${CENTER - ROSE_RADIUS + 6 + length - 1} ${CENTER + 4},${CENTER - ROSE_RADIUS + 6 + length - 1}`}
            fill={color}
          />
        </g>
      </svg>

      <div className="flex flex-col items-center leading-tight">
        <span className="text-sm font-semibold tabular-nums text-slate-700">
          {wind.speed.toFixed(1)} km/h
        </span>
        <span className="text-xs text-slate-400">{label}</span>
      </div>
    </div>
  )
}

export default memo(WindCompass)
