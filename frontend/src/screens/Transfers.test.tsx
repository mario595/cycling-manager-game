import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { placeBid, signFreeAgent, type AuctionMarket, type FreeAgentPool, type Me } from '../api'
import { useAuctions } from '../useAuctions'
import { useAuth } from '../useAuth'
import { useFreeAgents } from '../useFreeAgents'
import { useMyBids } from '../useMyBids'
import { Transfers } from './Transfers'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useFreeAgents', () => ({ useFreeAgents: vi.fn() }))
vi.mock('../useAuctions', () => ({ useAuctions: vi.fn() }))
vi.mock('../useMyBids', () => ({ useMyBids: vi.fn() }))
vi.mock('../api', () => ({ signFreeAgent: vi.fn(), placeBid: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseFreeAgents = vi.mocked(useFreeAgents)
const mockUseAuctions = vi.mocked(useAuctions)
const mockUseMyBids = vi.mocked(useMyBids)
const mockSignFreeAgent = vi.mocked(signFreeAgent)
const mockPlaceBid = vi.mocked(placeBid)

const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD' },
  lost_team: null,
}

const pool: FreeAgentPool = {
  balance: 500_000,
  riders: [
    {
      id: 7,
      name: 'Coach One',
      speciality: 'climber',
      nationality: 'FR',
      age: 27,
      height_cm: 178,
      weight_kg: 70,
      climb: 9,
      sprint: 4,
      flat: 5,
      resistance: 5,
      positioning: 4,
      freshness: 10,
      weekly_salary: 3_900,
      market_value: 90_000,
      release_cost: null,
      signing_fee: 46_800,
    },
    {
      id: 8,
      name: 'Helper Two',
      speciality: 'rouleur',
      nationality: 'BE',
      age: 24,
      height_cm: 182,
      weight_kg: 74,
      climb: 2,
      sprint: 5,
      flat: 8,
      resistance: 6,
      positioning: 5,
      freshness: 10,
      weekly_salary: 1_700,
      market_value: 40_000,
      release_cost: null,
      signing_fee: 20_000,
    },
    {
      id: 9,
      name: 'Sprinter Three',
      speciality: 'sprinter',
      nationality: 'IT',
      age: 25,
      height_cm: 180,
      weight_kg: 76,
      climb: 1,
      sprint: 9,
      flat: 5,
      resistance: 4,
      positioning: 6,
      freshness: 10,
      weekly_salary: 2_800,
      market_value: 75_000,
      release_cost: null,
      signing_fee: 34_000,
    },
  ],
}

const auctionMarket: AuctionMarket = {
  balance: 500_000,
  auctions: [
    {
      id: 1,
      current_price: 60_000,
      min_next_bid: 63_000,
      deadline: '2027-03-04T12:00:00Z',
      is_own_listing: false,
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
    },
  ],
}

function visibleNames() {
  return screen.getAllByText(/^(Coach One|Helper Two|Sprinter Three)$/).map((el) => el.textContent)
}

function renderTransfers() {
  return render(
    <MemoryRouter>
      <Transfers />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuth.mockReturnValue({
    me: manager,
    loading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    claim: vi.fn(),
    acknowledgeLostTeam: vi.fn(),
  })
  mockUseFreeAgents.mockReturnValue({ pool, loading: false, error: false, refresh: vi.fn() })
  mockUseAuctions.mockReturnValue({ market: auctionMarket, loading: false, error: false, refresh: vi.fn() })
  mockUseMyBids.mockReturnValue({ bids: [], refresh: vi.fn() })
  mockSignFreeAgent.mockResolvedValue(undefined)
  mockPlaceBid.mockResolvedValue(undefined)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('Transfers', () => {
  it('renders the signing fee and weekly salary on the card', () => {
    renderTransfers()

    expect(screen.getByText('Fee $46,800')).toBeInTheDocument()
    expect(screen.getByText('$3,900/wk')).toBeInTheDocument()
  })

  it('disables Sign with a reason when the fee exceeds the balance', () => {
    mockUseFreeAgents.mockReturnValue({
      pool: { ...pool, balance: 10_000 },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderTransfers()

    for (const button of screen.getAllByRole('button', { name: 'Sign' })) {
      expect(button).toBeDisabled()
    }
    expect(screen.getAllByText(/cannot afford/i)).toHaveLength(3)
  })

  it('enables Sign when the balance covers the fee', () => {
    renderTransfers()

    for (const button of screen.getAllByRole('button', { name: 'Sign' })) {
      expect(button).toBeEnabled()
    }
    expect(screen.queryByText(/cannot afford/i)).not.toBeInTheDocument()
  })

  it('lists the cheapest signing fee first by default', () => {
    renderTransfers()

    expect(visibleNames()).toEqual(['Helper Two', 'Sprinter Three', 'Coach One'])
  })

  it('sorts by name', () => {
    renderTransfers()

    fireEvent.click(screen.getByRole('button', { name: 'Name' }))

    expect(visibleNames()).toEqual(['Coach One', 'Helper Two', 'Sprinter Three'])
  })

  it('filters the pool by speciality', () => {
    renderTransfers()

    fireEvent.click(screen.getByRole('button', { name: 'sprinter' }))

    expect(visibleNames()).toEqual(['Sprinter Three'])
    expect(screen.getByText(/1 of 3 free agents/)).toBeInTheDocument()
  })

  it('returns every rider when the All filter is back on', () => {
    renderTransfers()

    fireEvent.click(screen.getByRole('button', { name: 'sprinter' }))
    fireEvent.click(screen.getByRole('button', { name: 'All' }))

    expect(visibleNames()).toEqual(['Helper Two', 'Sprinter Three', 'Coach One'])
    expect(screen.getByText(/3 of 3 free agents/)).toBeInTheDocument()
  })

  it('signs a rider and re-fetches the pool', async () => {
    const refresh = vi.fn()
    mockUseFreeAgents.mockReturnValue({ pool, loading: false, error: false, refresh })
    const sign = mockSignFreeAgent.mockResolvedValue(undefined)

    renderTransfers()

    fireEvent.click(screen.getAllByRole('button', { name: 'Sign' })[0])

    await waitFor(() => expect(sign).toHaveBeenCalledWith(8))
    await waitFor(() => expect(refresh).toHaveBeenCalled())
  })

  it('switches to the auctions tab and shows a live listing', () => {
    renderTransfers()

    fireEvent.click(screen.getByRole('button', { name: 'Auctions' }))

    expect(screen.getByText('For Sale Rider')).toBeInTheDocument()
    expect(screen.getByText('Current $60,000')).toBeInTheDocument()
    expect(screen.getByText('Minimum next bid $63,000')).toBeInTheDocument()
  })

  it('counts the deadline down in dd hh mm ss and keeps it live', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2027-03-01T00:00:00Z'))

    renderTransfers()
    fireEvent.click(screen.getByRole('button', { name: 'Auctions' }))

    // auctionMarket's listing deadline is 2027-03-04T12:00:00Z — exactly
    // 3 days 12 hours from the mocked "now".
    expect(screen.getByText('Ends in 03d 12h 00m 00s')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1_000)
    })
    expect(screen.getByText('Ends in 03d 11h 59m 59s')).toBeInTheDocument()
  })

  it('hides the bid action on the caller\'s own listing', () => {
    mockUseAuctions.mockReturnValue({
      market: { ...auctionMarket, auctions: [{ ...auctionMarket.auctions[0], is_own_listing: true }] },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderTransfers()
    fireEvent.click(screen.getByRole('button', { name: 'Auctions' }))

    expect(screen.getByText('Your listing.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bid' })).not.toBeInTheDocument()
  })

  it('places a bid at the pre-filled minimum and refreshes the market', async () => {
    const refreshMarket = vi.fn()
    const refreshMyBids = vi.fn()
    mockUseAuctions.mockReturnValue({ market: auctionMarket, loading: false, error: false, refresh: refreshMarket })
    mockUseMyBids.mockReturnValue({ bids: [], refresh: refreshMyBids })
    const bid = mockPlaceBid.mockResolvedValue(undefined)

    renderTransfers()
    fireEvent.click(screen.getByRole('button', { name: 'Auctions' }))
    fireEvent.click(screen.getByRole('button', { name: 'Bid' }))

    await waitFor(() => expect(bid).toHaveBeenCalledWith(1, 63_000))
    await waitFor(() => expect(refreshMarket).toHaveBeenCalled())
    await waitFor(() => expect(refreshMyBids).toHaveBeenCalled())
  })

  it('disables Bid when the amount exceeds the balance', () => {
    mockUseAuctions.mockReturnValue({
      market: { ...auctionMarket, balance: 1_000 },
      loading: false,
      error: false,
      refresh: vi.fn(),
    })

    renderTransfers()
    fireEvent.click(screen.getByRole('button', { name: 'Auctions' }))

    expect(screen.getByRole('button', { name: 'Bid' })).toBeDisabled()
    expect(screen.getByText('You cannot afford that bid.')).toBeInTheDocument()
  })

  it('shows an outbid notice from active bids', () => {
    mockUseMyBids.mockReturnValue({
      bids: [
        {
          auction_id: 1,
          rider_name: 'For Sale Rider',
          my_last_bid: 60_000,
          current_price: 63_000,
          is_high_bidder: false,
          deadline: '2027-03-04T12:00:00Z',
        },
      ],
      refresh: vi.fn(),
    })

    renderTransfers()

    expect(screen.getByText(/You've been outbid on For Sale Rider/)).toBeInTheDocument()
  })
})