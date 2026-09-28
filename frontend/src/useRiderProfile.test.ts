import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { getRiderProfile, RiderNotFound, type RiderProfile } from './api'
import { useRiderProfile } from './useRiderProfile'

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return { ...actual, getRiderProfile: vi.fn() }
})

const mockGetRiderProfile = vi.mocked(getRiderProfile)

function makeProfile(overrides: Partial<RiderProfile> = {}): RiderProfile {
  return {
    id: 1,
    name: 'Test Rider',
    speciality: 'Climber',
    nationality: 'Spain',
    age: 24,
    height_cm: 176,
    weight_kg: 61,
    climb: 8,
    sprint: 3,
    flat: 5,
    resistance: 6,
    positioning: 5,
    freshness: 7,
    weekly_salary: 4200,
    market_value: 310000,
    release_cost: null,
    final_season: false,
    team: { id: 1, name: 'Team', code: 'TEA' },
    current_week: { season: 1, week: 7 },
    retired: null,
    attribute_history: [],
    races: [],
    career: { starts: 0, wins: 0, podiums: 0, top_tens: 0, dnfs: 0 },
    ...overrides,
  }
}

describe('useRiderProfile', () => {
  it('sets notFound on a 404, not error', async () => {
    mockGetRiderProfile.mockRejectedValue(new RiderNotFound())

    const { result } = renderHook(() => useRiderProfile(1))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.notFound).toBe(true)
    expect(result.current.error).toBe(false)
  })

  it('sets error on a generic failure, not notFound', async () => {
    mockGetRiderProfile.mockRejectedValue(new Error('boom'))

    const { result } = renderHook(() => useRiderProfile(1))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe(true)
    expect(result.current.notFound).toBe(false)
  })

  it('resets profile to null while the next fetch is in flight', async () => {
    mockGetRiderProfile.mockResolvedValueOnce(makeProfile({ id: 1 }))

    const { result, rerender } = renderHook(({ riderId }) => useRiderProfile(riderId), {
      initialProps: { riderId: 1 },
    })

    await waitFor(() => expect(result.current.profile?.id).toBe(1))

    let resolveSecond: (profile: RiderProfile) => void = () => {}
    mockGetRiderProfile.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSecond = resolve
      }),
    )

    rerender({ riderId: 2 })

    expect(result.current.profile).toBeNull()
    expect(result.current.loading).toBe(true)

    resolveSecond(makeProfile({ id: 2 }))
    await waitFor(() => expect(result.current.profile?.id).toBe(2))
  })
})
