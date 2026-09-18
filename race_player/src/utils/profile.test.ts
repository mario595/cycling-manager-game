import { describe, expect, it } from 'vitest'

import { courseBounds, courseSegments } from '../components/CourseChart'
import { profileScale } from './useProfileScale'
import { computeProfile } from './profile'

describe('computeProfile', () => {
  it('derives correct cumulative elevation', () => {
    const profile = computeProfile([
      { length: 40_000, gradient: 4 },
      { length: 60_000, gradient: 2 },
    ])
    expect(profile[0]).toEqual({ distance: 0, elevation: 0, gradient: 4 })
    expect(profile[1]).toEqual({ distance: 40_000, elevation: 1600, gradient: 4 })
    expect(profile[2]).toEqual({ distance: 100_000, elevation: 2800, gradient: 2 })
  })

  it('handles a flat course', () => {
    const profile = computeProfile([{ length: 100_000, gradient: 0 }])
    expect(profile.map((p) => p.elevation)).toEqual([0, 0])
  })

  it('handles an empty course by returning the origin point', () => {
    const profile = computeProfile([])
    expect(profile).toEqual([{ distance: 0, elevation: 0, gradient: 0 }])
  })
})

describe('courseBounds', () => {
  it('returns 20 m headroom over the peak elevation', () => {
    const profile = computeProfile([{ length: 10_000, gradient: 10 }])
    const bounds = courseBounds(profile)
    // 10 km at 10% = 1000 m
    expect(bounds.maxElevation).toBe(1020)
    expect(bounds.minElevation).toBe(0)
  })
})

describe('courseSegments', () => {
  it('returns one fewer segment than profile points', () => {
    const profile = computeProfile([{ length: 10_000, gradient: 4 }])
    const scale = profileScale(900, 300, 10_000, 0, 420)
    const segs = courseSegments(profile, scale, 0)
    expect(segs).toHaveLength(profile.length - 1)
  })
})