import { describe, expect, it } from 'vitest'

import { formatCountdown } from './useCountdown'

describe('formatCountdown', () => {
  it('formats days, hours, minutes and seconds, zero-padded', () => {
    const now = Date.parse('2027-03-01T00:00:00Z')
    const deadline = new Date(now + (2 * 86_400 + 4 * 3_600 + 13 * 60 + 7) * 1000).toISOString()

    expect(formatCountdown(deadline, now)).toBe('02d 04h 13m 07s')
  })

  it('clamps at zero once the deadline has passed', () => {
    const now = Date.parse('2027-03-01T00:00:00Z')
    const deadline = new Date(now - 60_000).toISOString()

    expect(formatCountdown(deadline, now)).toBe('00d 00h 00m 00s')
  })
})
