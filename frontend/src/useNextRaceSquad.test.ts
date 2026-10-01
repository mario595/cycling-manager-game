import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { getSquad, type Squad } from './api'
import { useNextRaceSquad } from './useNextRaceSquad'

vi.mock('./api', () => ({ getSquad: vi.fn() }))

const mockGetSquad = vi.mocked(getSquad)

const squad: Squad = {
  race: 42,
  race_name: 'Circuit of Example',
  race_status: 'scheduled',
  starts_at: '2027-03-15T10:00:00Z',
  distance_km: 180,
  team: 1,
  team_name: 'Squad Team',
  editable: true,
  saved: false,
  squad_size: 4,
  candidates: [],
  stage_race: null,
}

describe('useNextRaceSquad', () => {
  it('fetches nothing when raceId is null', () => {
    const { result } = renderHook(() => useNextRaceSquad(null))

    expect(mockGetSquad).not.toHaveBeenCalled()
    expect(result.current).toEqual({ saved: null, loading: false })
  })

  it('reports saved', async () => {
    mockGetSquad.mockResolvedValue({ ...squad, saved: true })

    const { result } = renderHook(() => useNextRaceSquad(42))

    await waitFor(() => expect(result.current.saved).toBe(true))
    expect(result.current.loading).toBe(false)
  })

  it('reports not saved', async () => {
    mockGetSquad.mockResolvedValue(squad)

    const { result } = renderHook(() => useNextRaceSquad(42))

    await waitFor(() => expect(result.current.saved).toBe(false))
    expect(result.current.loading).toBe(false)
  })

  it('reports null on a failed request', async () => {
    mockGetSquad.mockRejectedValue(new Error('You do not manage a team.'))

    const { result } = renderHook(() => useNextRaceSquad(42))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.saved).toBeNull()
  })
})