import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { AuctionListing } from '../api'
import { formatCountdown } from '../countdown'
import { AuctionCard } from './AuctionCard'

const gameNow = new Date('2027-03-01T00:00:00Z')

const auction: AuctionListing = {
  id: 1,
  current_price: 60_000,
  min_next_bid: 63_000,
  deadline: '2027-03-04T12:00:00Z',
  is_own_listing: false,
  forced: false,
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
    final_season: false,
  },
}

describe('AuctionCard', () => {
  it('renders the rider, current price and a Bid action', () => {
    render(<AuctionCard auction={auction} balance={500_000} pending={false} gameNow={gameNow} onBid={vi.fn()} />)

    expect(screen.getByText('For Sale Rider')).toBeInTheDocument()
    expect(screen.getByText('Current $60,000')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Bid' })).toBeEnabled()
  })

  it('counts down against the game clock, not the browser clock', () => {
    // gameNow is 2027-03-01, real wall-clock "now" is whenever the test
    // actually runs — if the countdown used Date.now() this would read a
    // wildly different (likely negative-clamped) value under MockClock.
    render(<AuctionCard auction={auction} balance={500_000} pending={false} gameNow={gameNow} onBid={vi.fn()} />)

    const expected = formatCountdown(auction.deadline, gameNow.getTime())
    expect(screen.getByText(`Ends in ${expected}`)).toBeInTheDocument()
  })

  it('shows a placeholder countdown while the game clock has not loaded', () => {
    render(<AuctionCard auction={auction} balance={500_000} pending={false} gameNow={null} onBid={vi.fn()} />)

    expect(screen.getByText('Ends in —')).toBeInTheDocument()
  })

  it('hides the bid action and shows "Your listing." for the caller\'s own listing', () => {
    render(
      <AuctionCard
        auction={{ ...auction, is_own_listing: true }}
        balance={500_000}
        pending={false}
        gameNow={gameNow}
        onBid={vi.fn()}
      />,
    )

    expect(screen.getByText('Your listing.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bid' })).not.toBeInTheDocument()
  })

  it('calls onBid with the entered amount', () => {
    const onBid = vi.fn()
    render(<AuctionCard auction={auction} balance={500_000} pending={false} gameNow={gameNow} onBid={onBid} />)

    fireEvent.click(screen.getByRole('button', { name: 'Bid' }))

    expect(onBid).toHaveBeenCalledWith(auction.min_next_bid)
  })

  it('keeps the bid history collapsed until expanded', () => {
    render(<AuctionCard auction={auction} balance={500_000} pending={false} gameNow={gameNow} onBid={vi.fn()} />)

    expect(screen.getByRole('button', { name: /BID HISTORY \(2\)/ })).toBeInTheDocument()
    expect(screen.queryByText('Rival Racing')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /BID HISTORY/ }))

    expect(screen.getByText('Rival Racing')).toBeInTheDocument()
    expect(screen.getByText('Squad Team')).toBeInTheDocument()
  })

  it('renders no bid history toggle when nobody has bid', () => {
    render(
      <AuctionCard
        auction={{ ...auction, bids: [] }}
        balance={500_000}
        pending={false}
        gameNow={gameNow}
        onBid={vi.fn()}
      />,
    )

    expect(screen.queryByText(/BID HISTORY/)).not.toBeInTheDocument()
  })

  it('bumps the pre-filled amount up when a poll raises the minimum', () => {
    const onBid = vi.fn()
    const { rerender } = render(
      <AuctionCard auction={auction} balance={500_000} pending={false} gameNow={gameNow} onBid={onBid} />,
    )
    const input = screen.getByLabelText('Bid amount for For Sale Rider') as HTMLInputElement
    expect(input.value).toBe('63000')

    rerender(
      <AuctionCard
        auction={{ ...auction, current_price: 66_000, min_next_bid: 69_000 }}
        balance={500_000}
        pending={false}
        gameNow={gameNow}
        onBid={onBid}
      />,
    )

    expect(input.value).toBe('69000')
    fireEvent.click(screen.getByRole('button', { name: 'Bid' }))
    expect(onBid).toHaveBeenCalledWith(69_000)
  })

  it('does not clobber a bid the caller manually raised above the minimum', () => {
    const { rerender } = render(
      <AuctionCard auction={auction} balance={500_000} pending={false} gameNow={gameNow} onBid={vi.fn()} />,
    )
    const input = screen.getByLabelText('Bid amount for For Sale Rider') as HTMLInputElement
    fireEvent.change(input, { target: { value: '100000' } })

    // A poll brings a small rise that the manual bid already clears.
    rerender(
      <AuctionCard
        auction={{ ...auction, current_price: 66_000, min_next_bid: 69_000 }}
        balance={500_000}
        pending={false}
        gameNow={gameNow}
        onBid={vi.fn()}
      />,
    )

    expect(input.value).toBe('100000')
  })
})
