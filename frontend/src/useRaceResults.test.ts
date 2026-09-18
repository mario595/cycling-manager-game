import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { getRaceResults } from './api'
import { useRaceResults } from './useRaceResults'

vi.mock('./api', () => ({ getRaceResults: vi.fn() }))

const mockGetRaceResults = vi.mocked(getRaceResults)

describe('useRaceResults', () => {
  it('does not fetch when disabled', () => {
    const { result } = renderHook(() => useRaceResults(7, false))

    expect(mockGetRaceResults).not.toHaveBeenCalled()
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe(false)
    expect(result.current.results).toBeNull()
  })
})