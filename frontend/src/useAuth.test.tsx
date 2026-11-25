import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Me } from './api'
import { getMe } from './api'
import { AuthProvider, useAuth } from './useAuth'

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return { ...actual, getMe: vi.fn() }
})

const mockGetMe = vi.mocked(getMe)

function me(sponsorMissing: boolean): Me {
  return {
    authenticated: true,
    display_name: 'Mario',
    team: { id: 1, name: 'Squad Team', code: 'SQD', sponsor_missing: sponsorMissing, smallest_offer_weekly: null },
    lost_team: null,
  }
}

let renders = 0

function Probe() {
  const { me } = useAuth()
  renders += 1
  return <div data-testid="missing">{String(me?.team?.sponsor_missing ?? 'none')}</div>
}

beforeEach(() => {
  vi.useFakeTimers()
  renders = 0
  mockGetMe.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('AuthProvider', () => {
  it('re-reads me every minute, so a season opening shows without a reload (#161)', async () => {
    mockGetMe.mockResolvedValueOnce(me(false)).mockResolvedValue(me(true))

    render(<AuthProvider><Probe /></AuthProvider>)
    await act(async () => {})
    expect(screen.getByTestId('missing').textContent).toBe('false')

    await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })

    expect(screen.getByTestId('missing').textContent).toBe('true')
  })

  it('does not re-render when a poll brings back the same answer', async () => {
    mockGetMe.mockResolvedValue(me(false))

    render(<AuthProvider><Probe /></AuthProvider>)
    await act(async () => {})
    const settled = renders

    await act(async () => { await vi.advanceTimersByTimeAsync(180_000) })

    expect(mockGetMe).toHaveBeenCalledTimes(4)
    expect(renders).toBe(settled)
  })
})
