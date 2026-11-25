import { describe, expect, it } from 'vitest'

import { formatDate, formatMonth, formatShortDate, formatWeekday } from './format'

// Midday UTC, so the calendar day is the same in every time zone the test
// runner might sit in.
const DATE = '2026-11-05T12:00:00Z'

describe('date formatting (#153)', () => {
  it('puts the day before the month in a numeric date', () => {
    expect(formatDate(DATE)).toBe('05/11/2026')
  })

  it('accepts a Date as well as an ISO string', () => {
    expect(formatDate(new Date(DATE))).toBe('05/11/2026')
  })

  it('puts the day before the month in a short date', () => {
    expect(formatShortDate(DATE)).toBe('5 Nov')
  })

  it('names the month and weekday on their own', () => {
    expect(formatMonth(DATE)).toBe('Nov')
    expect(formatWeekday(DATE)).toBe('Thu')
  })
})
