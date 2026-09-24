import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { AuctionListing } from '../api'
import { AuctionCard } from './AuctionCard'

const auction: AuctionListing = {
  id: 1,
  current_price: 60_000,
  min_next_bid: 63_000,
  deadline: new Date(Date.now() + 3 * 86_400_000).toISOString(),
  is_own_listing: false,
  bids: [
    { team_name: 'Rival Racing', amount: 60_000, placed_at: '2027-03-01T10:00:00Z' },
    { team_name: 'Squad Team', amount: 55_000, placed_at: '2027-03-01T09:00:00Z' },
  ],
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

describe('AuctionCard', () => {
  it('renders the rider, current price and a Bid action', () => {
    render(<AuctionCard auction={auction} balance={500_000} pending={false} onBid={vi.fn()} />)

    expect(screen.getByText('For Sale Rider')).toBeInTheDocument()
    expect(screen.getByText('Current $60,000')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Bid' })).toBeEnabled()
  })

  it('hides the bid action and shows "Your listing." for the caller\'s own listing', () => {
    render(
      <AuctionCard
        auction={{ ...auction, is_own_listing: true }}
        balance={500_000}
        pending={false}
        onBid={vi.fn()}
      />,
    )

    expect(screen.getByText('Your listing.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bid' })).not.toBeInTheDocument()
  })

  it('calls onBid with the entered amount', () => {
    const onBid = vi.fn()
    render(<AuctionCard auction={auction} balance={500_000} pending={false} onBid={onBid} />)

    fireEvent.click(screen.getByRole('button', { name: 'Bid' }))

    expect(onBid).toHaveBeenCalledWith(auction.min_next_bid)
  })

  it('keeps the bid history collapsed until expanded', () => {
    render(<AuctionCard auction={auction} balance={500_000} pending={false} onBid={vi.fn()} />)

    expect(screen.getByRole('button', { name: /BID HISTORY \(2\)/ })).toBeInTheDocument()
    expect(screen.queryByText('Rival Racing')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /BID HISTORY/ }))

    expect(screen.getByText('Rival Racing')).toBeInTheDocument()
    expect(screen.getByText('Squad Team')).toBeInTheDocument()
  })

  it('renders no bid history toggle when nobody has bid', () => {
    render(
      <AuctionCard auction={{ ...auction, bids: [] }} balance={500_000} pending={false} onBid={vi.fn()} />,
    )

    expect(screen.queryByText(/BID HISTORY/)).not.toBeInTheDocument()
  })
})
