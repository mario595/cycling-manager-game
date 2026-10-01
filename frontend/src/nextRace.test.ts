import { describe, expect, it } from 'vitest'

import type { Calendar, CalendarRace, CalendarWeek } from './api'
import { nextRace } from './nextRace'

describe('test runner', () => {
  it('executes', () => {
    expect(true).toBe(true)
  })
})

function race(id: number, status: CalendarRace['status'], startsAt: string | null): CalendarRace {
  return {
    id,
    name: `Race ${id}`,
    starts_at: startsAt,
    status,
    distance_km: 200,
    stage_race: null,
  }
}

function week(number: number, races: CalendarRace[]): CalendarWeek {
  return {
    number,
    starts_at: `2027-01-0${number}T00:00:00Z`,
    races,
  }
}

function calendar(weeks: CalendarWeek[]): Calendar {
  return {
    state: 'in_season',
    season: 1,
    current_week: 1,
    weeks,
  }
}

describe('nextRace', () => {
  it('returns the first scheduled race', () => {
    const cal = calendar([week(3, [race(6, 'scheduled', '2027-03-15T10:00:00Z')])])
    expect(nextRace(cal)?.id).toBe(6)
  })

  it('skips finished races', () => {
    const cal = calendar([
      week(2, [race(3, 'finished', '2027-03-01T10:00:00Z')]),
      week(3, [race(6, 'scheduled', '2027-03-15T10:00:00Z')]),
    ])
    expect(nextRace(cal)?.id).toBe(6)
  })

  it('treats a running race as next', () => {
    const cal = calendar([week(3, [race(6, 'running', '2027-03-15T10:00:00Z')])])
    expect(nextRace(cal)?.id).toBe(6)
  })

  it('skips failed races', () => {
    const cal = calendar([
      week(2, [race(3, 'failed', '2027-03-01T10:00:00Z')]),
      week(3, [race(6, 'scheduled', '2027-03-15T10:00:00Z')]),
    ])
    expect(nextRace(cal)?.id).toBe(6)
  })

  it('returns null when every race has finished', () => {
    const cal = calendar([
      week(2, [race(3, 'finished', '2027-03-01T10:00:00Z')]),
      week(3, [race(6, 'finished', '2027-03-15T10:00:00Z')]),
    ])
    expect(nextRace(cal)).toBeNull()
  })

  it('returns null for a null calendar', () => {
    expect(nextRace(null)).toBeNull()
  })

  it('orders races within a week by starts_at', () => {
    const cal = calendar([
      week(3, [
        race(5, 'scheduled', '2027-03-15T14:00:00Z'),
        race(4, 'finished', '2027-03-15T10:00:00Z'),
      ]),
    ])
    expect(nextRace(cal)?.id).toBe(5)
  })
})