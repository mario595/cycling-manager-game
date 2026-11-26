import { describe, expect, it } from 'vitest'

import type { Departure } from './api'
import { departureText } from './departures'

function departure(overrides: Partial<Departure>): Departure {
  return {
    id: 1,
    kind: 'retired',
    at: '2027-02-25T00:00:00Z',
    season: 4,
    week: 3,
    rider: { id: 7, name: 'Pablo Fernandez', speciality: 'rouleur', age: 24 },
    buyer: null,
    fee: null,
    ...overrides,
  }
}

describe('departureText', () => {
  it('says an unsold forced sale left the rider a free agent, with the week (#170)', () => {
    expect(departureText(departure({ kind: 'unsold' }))).toBe(
      'found no buyer at a forced sale and joined the free agents in Season 4, Week 3',
    )
  })

  it('drops the week for an unsold forced sale outside the calendar', () => {
    expect(departureText(departure({ kind: 'unsold', season: null, week: null }))).toBe(
      'found no buyer at a forced sale and joined the free agents',
    )
  })
})
