import { describe, expect, it } from 'vitest'

import { formatGap, formatRaceTime } from './raceTime'

describe('formatRaceTime', () => {
  it('drops the hour under an hour', () => {
    expect(formatRaceTime(1000)).toBe('16m 40s')
  })

  it('shows the full hours/minutes/seconds over an hour', () => {
    expect(formatRaceTime(12194)).toBe('3h 23m 14s')
  })

  it('floors fractional seconds', () => {
    expect(formatRaceTime(1000.9)).toBe('16m 40s')
  })
})

describe('formatGap', () => {
  it('renders a zero gap as +0:00, not empty', () => {
    expect(formatGap(0)).toBe('+0:00')
  })

  it('renders a gap as m:ss across a minute boundary', () => {
    expect(formatGap(42)).toBe('+0:42')
    expect(formatGap(61)).toBe('+1:01')
  })

  it('extends to h:mm:ss past an hour', () => {
    expect(formatGap(3599)).toBe('+59:59')
    expect(formatGap(3600)).toBe('+1:00:00')
    expect(formatGap(3723)).toBe('+1:02:03')
  })

  it('floors fractional seconds', () => {
    expect(formatGap(41.9)).toBe('+0:41')
  })
})