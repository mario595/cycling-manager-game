import { describe, expect, it } from 'vitest'
import { arrowLength, unwrapAngle, windColor, windLabel } from './wind'

describe('unwrapAngle', () => {
  it('takes the short way across the 359->1 wrap', () => {
    // 350 -> 10 is a 20 degree step forward through the wrap, not 340 back.
    expect(unwrapAngle(350, 10)).toBeCloseTo(370, 5)
  })

  it('takes the short way across the 1->359 wrap', () => {
    expect(unwrapAngle(1, 359)).toBeCloseTo(-1, 5)
  })

  it('is a no-op for a small step with no wrap', () => {
    expect(unwrapAngle(45, 50)).toBeCloseTo(50, 5)
  })

  it('picks the shorter of two exactly-opposite directions consistently', () => {
    const result = unwrapAngle(0, 180)
    expect(Math.abs(result - 0)).toBeCloseTo(180, 5)
  })
})

describe('windLabel', () => {
  it('labels the four cardinal angles', () => {
    expect(windLabel(0)).toBe('Headwind')
    expect(windLabel(90)).toBe('Crosswind (R)')
    expect(windLabel(180)).toBe('Tailwind')
    expect(windLabel(270)).toBe('Crosswind (L)')
  })

  it('normalises angles outside [0, 360)', () => {
    expect(windLabel(360)).toBe('Headwind')
    expect(windLabel(-90)).toBe('Crosswind (L)')
  })
})

describe('windColor', () => {
  it('increases in visual weight with the band thresholds', () => {
    expect(windColor(0)).not.toBe(windColor(10))
    expect(windColor(10)).not.toBe(windColor(20))
    expect(windColor(20)).not.toBe(windColor(30))
  })
})

describe('arrowLength', () => {
  it('is clamped and monotonically non-decreasing with speed', () => {
    const zero = arrowLength(0)
    const mid = arrowLength(15)
    const max = arrowLength(100)
    expect(zero).toBeLessThanOrEqual(mid)
    expect(mid).toBeLessThanOrEqual(max)
    expect(arrowLength(1000)).toBe(max) // clamps, doesn't grow unbounded
  })
})
