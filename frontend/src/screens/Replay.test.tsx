import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { parseRaceLog } from '../../../race_player/src/utils/parseRaceLog'
import { computeRaceResults } from '../../../race_player/src/utils/raceResults'

vi.mock('../../../race_player/src/utils/raceResults', { spy: true })

import type { RaceDetail } from '../api'
import { useAuth } from '../useAuth'
import { useRaceDetail } from '../useRaceDetail'
import { useRaceLog } from '../useRaceLog'
import { useRaceResults } from '../useRaceResults'
import { Replay } from './Replay'

vi.mock('../useRaceDetail', () => ({ useRaceDetail: vi.fn() }))
vi.mock('../useRaceLog', () => ({ useRaceLog: vi.fn() }))
vi.mock('../useRaceResults', () => ({ useRaceResults: vi.fn() }))
vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))

const mockUseRaceDetail = vi.mocked(useRaceDetail)
const mockUseRaceLog = vi.mocked(useRaceLog)
const mockUseRaceResults = vi.mocked(useRaceResults)
const mockUseAuth = vi.mocked(useAuth)

const race: RaceDetail = {
  id: 42,
  name: 'Circuit of Example',
  status: 'finished',
  starts_at: '2027-03-15T10:00:00Z',
  distance_km: 20,
  course: [{ length: 20000, gradient: 0.02 }],
  payout: [],
  markers: [],
  has_replay: true,
}

function header(teams: string[], riders: Array<{ id: string; name: string; team: string; role: 'leader' | 'support' }>) {
  return JSON.stringify({
    v: 1,
    tick_interval: 10,
    course_length: 20000,
    segments: [{ length: 20000, gradient: 0.02 }],
    teams: Object.fromEntries(teams.map((t) => [t, { code: `T${t}`, name: `Team ${t}` }])),
    riders,
  })
}

/** Team "7" is the player's (D7: the log spells a team id as a string, and
 * the SPA's own team id is a number — the highlight must survive the
 * String()). */
const LOG = [
  header(['7', '9'], [
    { id: 'mine', name: 'Mine Rider', team: '7', role: 'leader' },
    { id: 'theirs', name: 'Their Rider', team: '9', role: 'leader' },
    { id: 'cut', name: 'Cut Rider', team: '9', role: 'support' },
  ]),
  JSON.stringify([0, [[100, 12, 90, 90, 0, null], [100, 12, 90, 90, 0, null], [100, 12, 90, 90, 0, null]]]),
  JSON.stringify([10, [[200, 12, 88, 88, 1, null], [200, 12, 88, 88, 0, null], [200, 12, 88, 88, 8, null]]]),
].join('\n')

function renderReplay() {
  return render(
    <MemoryRouter initialEntries={['/race/42/replay']}>
      <Routes>
        <Route path="/race/:raceId/replay" element={<Replay />} />
        <Route path="/race/:raceId" element={<div>Race screen</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockUseAuth.mockReturnValue({
    me: { authenticated: true, display_name: 'Mario', team: { id: 7, name: 'My Team', code: 'MYT' }, lost_team: null },
    loading: false,
  } as unknown as ReturnType<typeof useAuth>)
  mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })
  mockUseRaceDetail.mockReturnValue({ race, loading: false, error: false })
  mockUseRaceLog.mockReturnValue({ race: parseRaceLog(LOG), loading: false, error: false })
})

describe('Replay', () => {
  it('renders nothing while the race is loading', () => {
    mockUseRaceDetail.mockReturnValue({ race: null, loading: true, error: false })

    const { container } = renderReplay()

    expect(container).toBeEmptyDOMElement()
  })

  it('says so when the race cannot be loaded', () => {
    mockUseRaceDetail.mockReturnValue({ race: null, loading: false, error: true })

    renderReplay()

    expect(screen.getByText("Couldn't load this race.")).toBeInTheDocument()
  })

  it('refuses a race that has not finished', () => {
    mockUseRaceDetail.mockReturnValue({ race: { ...race, status: 'running' }, loading: false, error: false })

    renderReplay()

    expect(screen.getByText("This race hasn't finished yet.")).toBeInTheDocument()
    expect(screen.getByText('← Back to race')).toHaveAttribute('href', '/race/42')
    // Nothing is fetched for a race that cannot be replayed.
    expect(mockUseRaceLog).toHaveBeenLastCalledWith(42, false)
  })

  it('says so when there is no replay', () => {
    mockUseRaceDetail.mockReturnValue({ race: { ...race, has_replay: false }, loading: false, error: false })

    renderReplay()

    expect(screen.getByText('No replay is available for this race.')).toBeInTheDocument()
    expect(screen.getByText('← Back to race')).toHaveAttribute('href', '/race/42')
  })

  it('says so while the log is loading, and keeps the back link', () => {
    mockUseRaceLog.mockReturnValue({ race: null, loading: true, error: false })

    renderReplay()

    expect(screen.getByText('Loading replay…')).toBeInTheDocument()
    expect(screen.getByText('← Back to race')).toHaveAttribute('href', '/race/42')
  })

  it('says so when the log cannot be read', () => {
    mockUseRaceLog.mockReturnValue({ race: null, loading: false, error: true })

    renderReplay()

    expect(screen.getByText("This race's replay couldn't be loaded.")).toBeInTheDocument()
  })

  it('plays the race', () => {
    renderReplay()

    expect(screen.getByText('REPLAY')).toBeInTheDocument()
    expect(screen.getByText('Circuit of Example')).toBeInTheDocument()
    expect(screen.getByRole('slider', { name: 'Seek' })).toBeInTheDocument()
    expect(screen.getByText('Mine Rider')).toBeInTheDocument()
  })

  it('highlights only the riders who raced for the player team', () => {
    renderReplay()

    const own = screen.getByText('Mine Rider').closest('[data-own-team]')
    const other = screen.getByText('Their Rider').closest('[data-own-team]')
    expect(own).not.toBeNull()
    expect(own).toHaveAttribute('data-own-team', 'true')
    expect(other).toBeNull()
  })

  it('highlights nobody when the player has no team', () => {
    mockUseAuth.mockReturnValue({
      me: { authenticated: true, display_name: 'Mario', team: null, lost_team: null },
      loading: false,
    } as unknown as ReturnType<typeof useAuth>)

    renderReplay()

    expect(screen.getByText('Mine Rider').closest('[data-own-team]')).toBeNull()
  })

  it('lists a time-cut rider out of the race', () => {
    renderReplay()
    fireEvent.click(screen.getByRole('button', { name: 'Step forward' }))

    expect(screen.getByText('Out of the race')).toBeInTheDocument()
    expect(screen.getByText('Cut Rider')).toBeInTheDocument()
    expect(screen.getByText('DNF')).toBeInTheDocument()
  })

  it('keeps the results hidden until asked for', () => {
    renderReplay()

    expect(screen.queryByText('Rider results')).toBeNull()
    expect(mockUseRaceResults).toHaveBeenLastCalledWith(42, false)

    fireEvent.click(screen.getByRole('button', { name: 'Show results' }))

    expect(mockUseRaceResults).toHaveBeenLastCalledWith(42, true)
  })

  it('toggles play to pause', () => {
    renderReplay()

    fireEvent.click(screen.getByRole('button', { name: 'Play' }))
    expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument()
  })

  it('computes the finishing order once per loaded race, not per tick', () => {
    // The whole-race results never change during playback, and deriving them
    // per frame would make playing a race cost the square of its length — so
    // stepping through ticks must not recompute them. Regression for a review
    // finding: they used to sit in the per-snapshot `useMemo`.
    vi.mocked(computeRaceResults).mockClear()

    renderReplay()
    fireEvent.click(screen.getByRole('button', { name: 'Step forward' }))
    fireEvent.click(screen.getByRole('button', { name: 'Step forward' }))

    expect(vi.mocked(computeRaceResults)).toHaveBeenCalledTimes(1)
  })
})
