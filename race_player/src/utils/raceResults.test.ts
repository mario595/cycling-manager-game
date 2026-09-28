import { describe, expect, it } from 'vitest'

import { resultLabel } from './raceResults'
import type { Rider } from '../types/race'

function rider(overrides: Partial<Rider> = {}): Rider {
  return {
    id: 'r1',
    name: 'Rider One',
    team: 't1',
    role: 'support',
    pos: 1000,
    speed: 10,
    energy: 90,
    stamina: 90,
    pulling: false,
    surging: false,
    finished: false,
    dnf: false,
    finish_time: null,
    ...overrides,
  }
}

describe('resultLabel', () => {
  it('is blank while the rider is still racing', () => {
    expect(resultLabel(rider(), { finishTime: 4000, gapSeconds: null })).toBe('—')
    expect(resultLabel(rider(), undefined)).toBe('—')
  })

  it('shows the winner their own finish time', () => {
    expect(resultLabel(rider({ finished: true }), { finishTime: 4000, gapSeconds: null }))
      .toBe('01:06:40')
  })

  it('shows a rider in the same group as the rider ahead as +0', () => {
    expect(resultLabel(rider({ finished: true }), { finishTime: null, gapSeconds: 0 })).toBe('+0')
  })

  it('shows a rider with a real gap as +m:ss', () => {
    expect(resultLabel(rider({ finished: true }), { finishTime: null, gapSeconds: 194 }))
      .toBe('+3m 14s')
  })

  it('is blank for a rider the results know about who has not crossed yet', () => {
    // The results map holds a finish time from the whole race, so the cell
    // must gate on the live `finished` flag, not on presence in the map.
    expect(resultLabel(rider({ finished: false }), { finishTime: 4000, gapSeconds: null }))
      .toBe('—')
  })
})
