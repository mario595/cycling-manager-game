import { useMemo } from 'react'

export interface ProfileScale {
  width: number
  height: number
  margin: { top: number; right: number; bottom: number; left: number }
  x: (distance: number) => number
  y: (elevation: number) => number
}

/**
 * Linear scales mapping distance/elevation to SVG pixel coordinates.
 * Uses fixed margins so the chart area is predictable for overlays.
 */
export function profileScale(
  width: number,
  height: number,
  maxDistance: number,
  minElevation: number,
  maxElevation: number,
): ProfileScale {
  const margin = { top: 20, right: 20, bottom: 40, left: 85 }
  const plotWidth = width - margin.left - margin.right
  const plotHeight = height - margin.top - margin.bottom
  const elevRange = maxElevation - minElevation || 1

  const x = (distance: number) => margin.left + (distance / maxDistance) * plotWidth
  const y = (elevation: number) =>
    margin.top + (1 - (elevation - minElevation) / elevRange) * plotHeight

  return { width, height, margin, x, y }
}

export function useProfileScale(
  width: number,
  height: number,
  maxDistance: number,
  minElevation: number,
  maxElevation: number,
): ProfileScale {
  return useMemo(
    () => profileScale(width, height, maxDistance, minElevation, maxElevation),
    [width, height, maxDistance, minElevation, maxElevation],
  )
}