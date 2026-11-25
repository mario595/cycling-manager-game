import { useEffect, useState, type ReactNode } from 'react'

import type { AuctionListing, Bid } from '../api'
import { formatCountdown } from '../countdown'
import { formatMoney } from '../format'
import { color, font } from '../theme'
import { Button, Card, ForcedSaleTag, LabelBar } from './primitives'

type AttrKey = 'climb' | 'sprint' | 'flat' | 'resistance' | 'positioning'

const ATTR_KEYS: { key: AttrKey; label: string }[] = [
  { key: 'climb', label: 'CLM' },
  { key: 'sprint', label: 'SPR' },
  { key: 'flat', label: 'FLT' },
  { key: 'resistance', label: 'RES' },
  { key: 'positioning', label: 'POS' },
]

/** One live auction: rider, price, a live countdown, a bid action (hidden
 * on the caller's own listing) and its collapsible bid history. Shared by
 * the Transfers screen's Sell and Buy sections and the Dashboard's "My
 * auctions" card, so an auction reads identically wherever it appears.
 *
 * `gameNow` drives the countdown and comes from the caller's own
 * `useClock()` call, not from inside this component: `deadline` is a
 * game-time value, and under `MockClock` — the mode a developer runs to
 * exercise auctions by hand — the browser's wall clock can read days
 * away from it. One `useClock()` per screen also means one poll for
 * however many cards it renders, not one per card. */
export function AuctionCard({
  auction,
  balance,
  pending,
  gameNow,
  onBid,
  tag,
}: {
  auction: AuctionListing
  balance: number
  pending: boolean
  gameNow: Date | null
  onBid: (amount: number) => void
  /** An optional marker under the rider's name — the Transfers screen's
   * Buy list uses it to tell an auction from a free agent (#154). */
  tag?: ReactNode
}) {
  const [amount, setAmount] = useState(auction.min_next_bid)
  const rider = auction.rider
  const affordable = amount <= balance
  const clearsIncrement = amount >= auction.min_next_bid
  const countdown = gameNow ? formatCountdown(auction.deadline, gameNow.getTime()) : '—'

  // A poll can bring a higher price while this card is open. Bump the
  // pre-filled amount up to the new minimum so Bid doesn't sit silently
  // disabled on a stale value — but leave a bid the caller raised above
  // the minimum themselves alone.
  useEffect(() => {
    setAmount((current) => (current < auction.min_next_bid ? auction.min_next_bid : current))
  }, [auction.min_next_bid])

  return (
    <Card style={{ padding: '15px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 11,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 14,
            fontWeight: 700,
            fontFamily: font.mono,
            background: color.canvas,
            color: color.ink,
            flex: '0 0 40px',
          }}
        >
          {rider.speciality.slice(0, 2).toUpperCase()}
        </div>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
          <div
            style={{
              fontSize: 14.5,
              fontWeight: 600,
              letterSpacing: '-0.2px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {rider.name}
          </div>
          <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
            {rider.speciality.toUpperCase()} · {rider.age} yrs
          </div>
          {auction.forced || tag ? (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {tag}
              {auction.forced ? <ForcedSaleTag /> : null}
            </div>
          ) : null}
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {ATTR_KEYS.map(({ key, label }) => (
          <LabelBar key={key} label={label} value={rider[key]} />
        ))}
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
          borderTop: `1px solid ${color.dividerStrong}`,
          paddingTop: 10,
        }}
      >
        <span style={{ fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>
          Current {formatMoney(auction.current_price)}
        </span>
        <span style={{ fontSize: 11, color: color.muted, fontFamily: font.mono }}>
          Ends in {countdown}
        </span>
      </div>

      {auction.is_own_listing ? (
        <div style={{ fontSize: 12, color: color.muted }}>Your listing.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="number"
              min={auction.min_next_bid}
              step={1}
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
              aria-label={`Bid amount for ${rider.name}`}
              style={{
                flex: 1,
                minWidth: 0,
                fontFamily: font.mono,
                fontSize: 13,
                padding: '7px 9px',
                borderRadius: 8,
                border: `1px solid ${color.border}`,
                background: color.canvas,
                color: color.ink,
              }}
            />
            <Button
              onClick={() => onBid(amount)}
              disabled={pending || !affordable || !clearsIncrement}
              style={{ opacity: pending || !affordable || !clearsIncrement ? 0.6 : 1 }}
            >
              Bid
            </Button>
          </div>
          <div style={{ fontSize: 11, color: color.muted, fontFamily: font.mono }}>
            Minimum next bid {formatMoney(auction.min_next_bid)}
          </div>
          {!affordable ? (
            <div style={{ fontSize: 12, color: color.negative }}>You cannot afford that bid.</div>
          ) : null}
        </div>
      )}

      {auction.bids.length > 0 ? <BidHistory bids={auction.bids} /> : null}
    </Card>
  )
}

/** Collapsed by default — a card's primary job is the price and the bid
 * action; the history is there for whoever wants to check it, not
 * something every card should spend vertical space on up front. */
function BidHistory({ bids }: { bids: Bid[] }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 5,
        borderTop: `1px solid ${color.dividerStrong}`,
        paddingTop: 9,
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        style={{
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          textAlign: 'left',
          fontSize: 10.5,
          letterSpacing: '0.8px',
          color: color.mutedStrong,
          fontFamily: font.mono,
        }}
      >
        {expanded ? '▾' : '▸'} BID HISTORY ({bids.length})
      </button>
      {expanded
        ? bids.map((bid, i) => (
            <div
              key={`${bid.team_name}-${bid.placed_at}-${i}`}
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}
            >
              <span style={{ fontSize: 12.5, color: color.ink }}>{bid.team_name}</span>
              <span style={{ fontSize: 12, fontFamily: font.mono, color: color.mutedStrong }}>
                {formatMoney(bid.amount)}
              </span>
            </div>
          ))
        : null}
    </div>
  )
}
