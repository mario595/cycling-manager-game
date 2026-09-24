import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuctionMarket, Calendar, Me, MyBidStatus, Position, Standings } from '../api'
import { useAuctions } from '../useAuctions'
import { useAuth } from '../useAuth'
import { useCalendar } from '../useCalendar'
import { useMyBids } from '../useMyBids'
import { useNextRaceSquad } from '../useNextRaceSquad'
import { useSeason } from '../useSeason'
import { useStandings } from '../useStandings'
import { Dashboard } from './Dashboard'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useSeason', () => ({ useSeason: vi.fn() }))
vi.mock('../useCalendar', () => ({ useCalendar: vi.fn() }))
vi.mock('../useStandings', () => ({ useStandings: vi.fn() }))
vi.mock('../useNextRaceSquad', () => ({ useNextRaceSquad: vi.fn() }))
vi.mock('../useAuctions', () => ({ useAuctions: vi.fn() }))
vi.mock('../useMyBids', () => ({ useMyBids: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseSeason = vi.mocked(useSeason)
const mockUseCalendar = vi.mocked(useCalendar)
const mockUseStandings = vi.mocked(useStandings)
const mockUseNextRaceSquad = vi.mocked(useNextRaceSquad)
const mockUseAuctions = vi.mocked(useAuctions)
const mockUseMyBids = vi.mocked(useMyBids)

const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD' },
  lost_team: null,
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
    acknowledgeLostTeam: vi.fn(),
  })
  mockUseSeason.mockReturnValue({ position, loading: false, error: false })
  mockUseCalendar.mockReturnValue({ calendar, loading: false, error: false })
  mockUseStandings.mockReturnValue({ standings, loading: false, error: false })
  mockUseNextRaceSquad.mockReturnValue({ saved: false, loading: false })
  mockUseAuctions.mockReturnValue({
    market: { balance: 500_000, auctions: [] },
    loading: false,
    error: false,
    refresh: vi.fn(),
  })
  mockUseMyBids.mockReturnValue({ bids: [], refresh: vi.fn() })
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

  it('shows nothing for My auctions when the team has none', () => {
    renderDashboard()

    expect(screen.queryByText('My auctions')).toBeNull()
  })

  it('lists a rider the team is selling', () => {
    const auction: AuctionMarket['auctions'][number] = {
      id: 1,
      current_price: 60_000,
      min_next_bid: 63_000,
      deadline: '2027-03-04T12:00:00Z',
      is_own_listing: true,
      rider: {
        id: 21,
        name: 'For Sale Rider',
        speciality: 'climber',
        nationality: 'FR',
        age: 26,
        height_cm: 176,
        weight_kg: 68,
        climb: 8,
        sprint: 4,
        flat: 5,
        resistance: 5,
        positioning: 4,
        freshness: 10,
        weekly_salary: 3_500,
        market_value: 120_000,
        release_cost: null,
      },
    }
    mockUseAuctions.mockReturnValue({
      market: { balance: 500_000, auctions: [auction] },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderDashboard()

    expect(screen.getByText('My auctions')).toBeInTheDocument()
    expect(screen.getByText('SELLING')).toBeInTheDocument()
    expect(screen.getByText('For Sale Rider')).toBeInTheDocument()
    expect(screen.getByText('$60,000')).toBeInTheDocument()
  })

  it('lists an auction the team is bidding on, with its status', () => {
    const bid: MyBidStatus = {
      auction_id: 2,
      rider_name: 'Target Rider',
      my_last_bid: 40_000,
      current_price: 45_000,
      is_high_bidder: false,
      deadline: '2027-03-04T12:00:00Z',
    }
    mockUseMyBids.mockReturnValue({ bids: [bid], refresh: vi.fn() })

    renderDashboard()

    expect(screen.getByText('BIDDING')).toBeInTheDocument()
    expect(screen.getByText('Target Rider')).toBeInTheDocument()
    expect(screen.getByText('Outbid')).toBeInTheDocument()
    expect(screen.getByText('$45,000')).toBeInTheDocument()
  })

  it('does not confuse listings the team is not selling with its own', () => {
    const auction: AuctionMarket['auctions'][number] = {
      id: 3,
      current_price: 10_000,
      min_next_bid: 11_000,
      deadline: '2027-03-04T12:00:00Z',
      is_own_listing: false,
      rider: {
        id: 22,
        name: 'Someone Elses Rider',
        speciality: 'sprinter',
        nationality: 'BE',
        age: 24,
        height_cm: 180,
        weight_kg: 74,
        climb: 2,
        sprint: 8,
        flat: 7,
        resistance: 4,
        positioning: 6,
        freshness: 10,
        weekly_salary: 2_000,
        market_value: 30_000,
        release_cost: null,
      },
    }
    mockUseAuctions.mockReturnValue({
      market: { balance: 500_000, auctions: [auction] },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderDashboard()

    expect(screen.queryByText('My auctions')).toBeNull()
  })
})