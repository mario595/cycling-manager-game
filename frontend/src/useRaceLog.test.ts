import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { getRaceLog } from './api'
import { useRaceLog } from './useRaceLog'

vi.mock('./api', () => ({ getRaceLog: vi.fn() }))

const mockGetRaceLog = vi.mocked(getRaceLog)

const LOG = [
  JSON.stringify({
    v: 1,
    tick_interval: 2,
    course_length: 5000,
    segments: [{ length: 5000, gradient: 0 }],
    teams: { '7': { code: 'ALP', name: 'Alpine Racing' } },
    riders: [{ id: 'r1', name: 'Rider One', team: '7', role: 'leader' }],
  }),
  JSON.stringify([0, [[100, 10, 80, 70, 1, null]]]),
  JSON.stringify([2, [[120, 10, 78, 68, 1, null]]]),
  JSON.stringify([4, [[140, 10, 76, 66, 1, null]]]),
].join('\n')

describe('useRaceLog', () => {
  it('does not fetch when disabled', () => {
    const { result } = renderHook(() => useRaceLog(7, false))

    expect(mockGetRaceLog).not.toHaveBeenCalled()
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe(false)
    expect(result.current.race).toBeNull()
  })

  it('parses the fetched log', async () => {
    mockGetRaceLog.mockResolvedValue(LOG)

    const { result } = renderHook(() => useRaceLog(7, true))

    await waitFor(() => expect(result.current.race).not.toBeNull())
    expect(result.current.race!.maxTicks).toBe(2)
    expect(result.current.race!.tickInterval).toBe(2)
    expect(result.current.race!.snapshots).toHaveLength(3)
  })

  it('reports an error when the log cannot be fetched', async () => {
    mockGetRaceLog.mockRejectedValue(new Error('404'))

    const { result } = renderHook(() => useRaceLog(7, true))

    await waitFor(() => expect(result.current.error).toBe(true))
    expect(result.current.race).toBeNull()
  })

  it('reports an error when the log cannot be parsed', async () => {
    const unsupported = LOG.replace('"v":1', '"v":99')
    mockGetRaceLog.mockResolvedValue(unsupported)

    const { result } = renderHook(() => useRaceLog(7, true))

    // A rejected parse is an error state, not a thrown render.
    await waitFor(() => expect(result.current.error).toBe(true))
    expect(result.current.race).toBeNull()
  })
})
