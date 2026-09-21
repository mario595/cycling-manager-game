import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { RaceDetail, RaceResults, Squad } from '../api'
import { useRaceDetail } from '../useRaceDetail'
import { useRaceResults } from '../useRaceResults'
import { useSquad } from '../useSquad'
import { Race } from './Race'

vi.mock('../useRaceDetail', () => ({ useRaceDetail: vi.fn() }))
vi.mock('../useRaceResults', () => ({ useRaceResults: vi.fn() }))
vi.mock('../useSquad', () => ({ useSquad: vi.fn() }))

const mockUseRaceDetail = vi.mocked(useRaceDetail)
const mockUseRaceResults = vi.mocked(useRaceResults)
const mockUseSquad = vi.mocked(useSquad)

const upcomingRace: RaceDetail = {
  id: 42,
  name: 'Circuit of Example',
  status: 'scheduled',
  starts_at: '2027-03-15T10:00:00Z',
  distance_km: 50,
  course: [
    { length: 40000, gradient: 0.02 },
    { length: 10000, gradient: 0 },
  ],
  payout: [
    { position: 1, points: 20, prize: 20_000 },
    { position: 2, points: 15, prize: 15_000 },
    { position: 10, points: 1, prize: 1_000 },
  ],
}

const finishedResults: RaceResults = {
  race: { id: 42, name: 'Circuit of Example', status: 'finished' },
  results: [
    {
      position: 1,
      rider: { id: 1, name: 'Winner Rider' },
      team: { id: 1, name: 'Results Team', code: 'RES' },
      finish_time: 3600,
      finished: true,
    },
    {
      position: 2,
      rider: { id: 2, name: 'Second Rider' },
      team: { id: 1, name: 'Results Team', code: 'RES' },
      finish_time: 3642,
      finished: true,
    },
  ],
  points: [
    { team: { id: 1, name: 'Results Team', code: 'RES' }, position: 1, points: 20, prize: 20_000 },
    { team: { id: 2, name: 'Zero Team', code: 'ZRO' }, position: null, points: 0, prize: 0 },
  ],
}

const squad: Squad = {
  race: 42,
  race_name: 'Circuit of Example',
  race_status: 'scheduled',
  starts_at: '2027-03-15T10:00:00Z',
  distance_km: 50,
  team: 1,
  team_name: 'Squad Team',
  editable: true,
  saved: false,
  squad_size: 4,
  candidates: [
    { id: 1, name: 'Rider One', speciality: 'Climber', age: 25, climb: 8, sprint: 5, flat: 6, resistance: 7, positioning: 6, freshness: 8, selected: true, is_leader: true },
    { id: 2, name: 'Rider Two', speciality: 'Sprinter', age: 26, climb: 4, sprint: 9, flat: 8, resistance: 6, positioning: 7, freshness: 7, selected: true, is_leader: false },
    { id: 3, name: 'Rider Three', speciality: 'Puncher', age: 27, climb: 6, sprint: 6, flat: 6, resistance: 6, positioning: 6, freshness: 7, selected: true, is_leader: false },
    { id: 4, name: 'Rider Four', speciality: 'Time trialist', age: 28, climb: 5, sprint: 5, flat: 5, resistance: 8, positioning: 5, freshness: 6, selected: true, is_leader: false },
  ],
}

function renderRace() {
  return render(
    <MemoryRouter initialEntries={['/race/42']}>
      <Routes>
        <Route path="/race/:raceId" element={<Race />} />
      </Routes>
    </MemoryRouter>,
  )
}

function noSquad() {
  mockUseSquad.mockReturnValue({
    squad: null,
    loading: false,
    error: false,
    save: vi.fn(),
    saving: false,
    saveError: null,
  })
}

beforeEach(() => {
  noSquad()
})

describe('Race', () => {
  it('renders the course profile for an upcoming race', () => {
    mockUseRaceDetail.mockReturnValue({ race: upcomingRace, loading: false, error: false })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })
    mockUseSquad.mockReturnValue({
      squad,
      loading: false,
      error: false,
      save: vi.fn(),
      saving: false,
      saveError: null,
    })

    const { container } = renderRace()

    expect(screen.getByText('Circuit of Example')).toBeInTheDocument()
    expect(container.querySelector('svg[aria-label="Elevation profile"]')).not.toBeNull()
  })

  it('renders the payout table for an upcoming race', () => {
    mockUseRaceDetail.mockReturnValue({ race: upcomingRace, loading: false, error: false })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })
    mockUseSquad.mockReturnValue({
      squad,
      loading: false,
      error: false,
      save: vi.fn(),
      saving: false,
      saveError: null,
    })

    renderRace()

    expect(screen.getByText('Prize list')).toBeInTheDocument()
    expect(screen.getByText('$20,000')).toBeInTheDocument()
    expect(screen.getByText('$1,000')).toBeInTheDocument()
  })

  it('renders the course profile and both tables for a finished race', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'finished' },
      loading: false,
      error: false,
    })
    mockUseRaceResults.mockReturnValue({ results: finishedResults, loading: false, error: false })

    renderRace()

    expect(screen.getByText('Winner Rider')).toBeInTheDocument()
    expect(screen.getByText('Zero Team')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Elevation profile' })).toBeInTheDocument()
    expect(screen.getByText('Team points and prizes')).toBeInTheDocument()
    // Once in the team points table, once in the prize list.
    expect(screen.getAllByText('$20,000')).toHaveLength(2)
  })

  it('renders without a squad panel when the manager has no team', () => {
    mockUseRaceDetail.mockReturnValue({ race: upcomingRace, loading: false, error: false })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })
    mockUseSquad.mockReturnValue({
      squad: null,
      loading: false,
      error: true,
      save: vi.fn(),
      saving: false,
      saveError: null,
    })

    renderRace()

    expect(screen.getByText('Circuit of Example')).toBeInTheDocument()
    expect(screen.queryByText('Select squad')).toBeNull()
  })

  it('renders a plain message for a failed race', () => {
    mockUseRaceDetail.mockReturnValue({
      race: { ...upcomingRace, status: 'failed' },
      loading: false,
      error: false,
    })
    mockUseRaceResults.mockReturnValue({ results: null, loading: false, error: false })

    renderRace()

    expect(screen.getByText('This race did not run.')).toBeInTheDocument()
  })
})