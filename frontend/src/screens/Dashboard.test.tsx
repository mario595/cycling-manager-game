import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Calendar, Me, Position, Standings } from '../api'
import { useAuth } from '../useAuth'
import { useCalendar } from '../useCalendar'
import { useNextRaceSquad } from '../useNextRaceSquad'
import { useSeason } from '../useSeason'
import { useStandings } from '../useStandings'
import { Dashboard } from './Dashboard'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useSeason', () => ({ useSeason: vi.fn() }))
vi.mock('../useCalendar', () => ({ useCalendar: vi.fn() }))
vi.mock('../useStandings', () => ({ useStandings: vi.fn() }))
vi.mock('../useNextRaceSquad', () => ({ useNextRaceSquad: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseSeason = vi.mocked(useSeason)
const mockUseCalendar = vi.mocked(useCalendar)
const mockUseStandings = vi.mocked(useStandings)
const mockUseNextRaceSquad = vi.mocked(useNextRaceSquad)

const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD' },
}

const position: Position = {
  state: 'in_season',
  season: 1,
  week: 1,
  week_ends_at: '2026-09-21T00:00:00Z',
}

const calendar: Calendar = {
  state: 'in_season',
  season: 1,
  current_week: 1,
  weeks: [
    {
      number: 1,
      starts_at: '2026-09-14T00:00:00Z',
      races: [
        {
          id: 42,
          name: 'Tour de Sancerre',
          starts_at: '2026-09-20T10:00:00Z',
          status: 'scheduled',
          distance_km: 180,
        },
      ],
    },
  ],
}

const standings: Standings = {
  state: 'in_season',
  season: 1,
  standings: [{ rank: 3, team: { id: 1, name: 'Squad Team', code: 'SQD' }, points: 144 }],
}

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockUseAuth.mockReturnValue({
    me: manager,
    loading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    claim: vi.fn(),
  })
  mockUseSeason.mockReturnValue({ position, loading: false, error: false })
  mockUseCalendar.mockReturnValue({ calendar, loading: false, error: false })
  mockUseStandings.mockReturnValue({ standings, loading: false, error: false })
  mockUseNextRaceSquad.mockReturnValue({ saved: false, loading: false })
})

describe('Dashboard', () => {
  it('greets the logged-in manager by name', () => {
    renderDashboard()

    expect(screen.getByText('Good morning, Mario.')).toBeInTheDocument()
  })

  it('shows the team name', () => {
    renderDashboard()

    expect(screen.getByText('Squad Team')).toBeInTheDocument()
  })

  it('shows the season and week', () => {
    renderDashboard()

    expect(screen.getByText('Season 1 · Week 1')).toBeInTheDocument()
  })

  it('shows the team\u2019s own rank and points', () => {
    renderDashboard()

    expect(screen.getByText('#3')).toBeInTheDocument()
    expect(screen.getByText('144 pts')).toBeInTheDocument()
  })

  it('shows nothing for standings when the team is not ranked', () => {
    mockUseStandings.mockReturnValue({
      standings: { ...standings, standings: [{ rank: 1, team: { id: 2, name: 'Other Team', code: 'OTH' }, points: 200 }] },
      loading: false,
      error: false,
    })

    renderDashboard()

    expect(screen.queryByText('Standings')).toBeNull()
  })

  it('shows the next race with its name', () => {
    renderDashboard()

    const link = screen.getByRole('link', { name: 'Tour de Sancerre' })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/race/42')
  })

  it('says the squad is set when it is', () => {
    mockUseNextRaceSquad.mockReturnValue({ saved: true, loading: false })

    renderDashboard()

    expect(screen.getByText('Squad set')).toBeInTheDocument()
  })

  it('nudges when no squad is chosen', () => {
    renderDashboard()

    expect(screen.getByText('No squad chosen — one will be picked for you')).toBeInTheDocument()
  })

  it('says the season has no races left when none remain', () => {
    mockUseCalendar.mockReturnValue({
      calendar: {
        ...calendar,
        weeks: [
          {
            number: 1,
            starts_at: '2026-09-14T00:00:00Z',
            races: [
              {
                id: 42,
                name: 'Tour de Sancerre',
                starts_at: '2026-09-20T10:00:00Z',
                status: 'finished',
                distance_km: 180,
              },
            ],
          },
        ],
      },
      loading: false,
      error: false,
    })

    renderDashboard()

    expect(screen.getByText('The season has no races left.')).toBeInTheDocument()
  })

  it('renders no standings block while standings are loading', () => {
    mockUseStandings.mockReturnValue({ standings: null, loading: true, error: false })

    renderDashboard()

    expect(screen.queryByText('Standings')).toBeNull()
  })

  it('renders the rest of the page while one block is still loading', () => {
    mockUseNextRaceSquad.mockReturnValue({ saved: null, loading: true })

    renderDashboard()

    expect(screen.getByText('Good morning, Mario.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Tour de Sancerre' })).toBeInTheDocument()
    expect(screen.queryByText('Squad set')).toBeNull()
    expect(screen.queryByText('No squad chosen — one will be picked for you')).toBeNull()
  })
})