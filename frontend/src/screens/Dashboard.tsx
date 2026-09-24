import { Link } from 'react-router-dom'

import type { AuctionListing, MyBidStatus } from '../api'
import { Card, CardHeader, PageBody, PageHeading } from '../components/primitives'
import { formatMoney } from '../format'
import { nextRace } from '../nextRace'
import { seasonLabel } from '../seasonLabel'
import { color, font } from '../theme'
import { useAuctions } from '../useAuctions'
import { useAuth } from '../useAuth'
import { useCalendar } from '../useCalendar'
import { useCountdown } from '../useCountdown'
import { useMyBids } from '../useMyBids'
import { useNextRaceSquad } from '../useNextRaceSquad'
import { useSeason } from '../useSeason'
import { useStandings } from '../useStandings'

export function Dashboard() {
  const { me } = useAuth()
  const { position } = useSeason()

  return (
    <PageBody>
      <PageHeading
        eyebrow={seasonLabel(position)}
        title={me ? `Good morning, ${me.display_name}.` : ''}
        subtitle={me?.team?.name ?? ''}
      />

      <StandingsSection />

      <NextRaceCard />

      <MyAuctionsSection />
    </PageBody>
  )
}

function StandingsSection() {
  const { me } = useAuth()
  const { standings } = useStandings()

  const team = me?.team
  if (!standings || standings.state === 'no_season' || !team) return null

  const mine = standings.standings.find((entry) => entry.team.id === team.id)
  if (!mine) return null

  return (
    <Card>
      <CardHeader title="Standings" />
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 10,
          padding: '16px 20px',
        }}
      >
        <div style={{ fontSize: 20, fontWeight: 600, fontFamily: font.mono }}>
          #{mine.rank}
        </div>
        <div style={{ fontSize: 13, color: color.muted }}>
          {mine.points} pts
        </div>
      </div>
    </Card>
  )
}

function NextRaceCard() {
  const { calendar, loading } = useCalendar()
  const race = nextRace(calendar)
  const { saved } = useNextRaceSquad(race?.id ?? null)

  return (
    <Card>
      <CardHeader title="Next race" />
      {loading ? null : race === null ? (
        <div style={{ padding: '16px 20px', fontSize: 13, color: color.muted }}>
          The season has no races left.
        </div>
      ) : (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            padding: '16px 20px',
          }}
        >
          <Link
            to={`/race/${race.id}`}
            style={{ fontSize: 17, fontWeight: 600, color: color.ink, textDecoration: 'none' }}
          >
            {race.name}
          </Link>
          <div style={{ fontSize: 12.5, color: color.muted, fontFamily: font.mono }}>
            {race.starts_at
              ? new Date(race.starts_at).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                })
              : 'unscheduled'}
          </div>
          {saved === true ? (
            <div style={{ fontSize: 13, color: color.positive }}>Squad set</div>
          ) : saved === false ? (
            <div style={{ fontSize: 13, color: color.accentInk }}>
              No squad chosen — one will be picked for you
            </div>
          ) : null}
        </div>
      )}
    </Card>
  )
}

/** Every auction the manager is involved in — selling (their own open
 * listings) or bidding (from useMyBids, spec item 8's outbid tracking) —
 * so neither is buried inside the Transfers screen's tabs. Renders
 * nothing while loading, or once loaded if there is nothing to show. */
function MyAuctionsSection() {
  const { market, loading } = useAuctions()
  const { bids } = useMyBids()

  if (loading) return null

  const selling = market?.auctions.filter((a) => a.is_own_listing) ?? []
  if (selling.length === 0 && bids.length === 0) return null

  return (
    <Card>
      <CardHeader title="My auctions" />
      {selling.length > 0 ? (
        <>
          <SectionLabel>SELLING</SectionLabel>
          {selling.map((auction) => (
            <SellingRow key={auction.id} auction={auction} />
          ))}
        </>
      ) : null}
      {bids.length > 0 ? (
        <>
          <SectionLabel>BIDDING</SectionLabel>
          {bids.map((bid) => (
            <BiddingRow key={bid.auction_id} bid={bid} />
          ))}
        </>
      ) : null}
    </Card>
  )
}

function SectionLabel({ children }: { children: string }) {
  return (
    <div
      style={{
        padding: '10px 20px 2px',
        fontSize: 10.5,
        letterSpacing: '0.8px',
        color: color.mutedStrong,
        fontFamily: font.mono,
        borderTop: `1px solid ${color.dividerStrong}`,
      }}
    >
      {children}
    </div>
  )
}

function AuctionRowLayout({ name, right, countdown }: { name: string; right: string; countdown: string }) {
  return (
    <Link
      to="/transfers"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '11px 20px',
        textDecoration: 'none',
        color: color.ink,
      }}
    >
      <div style={{ flex: 1, minWidth: 0, fontSize: 14, fontWeight: 600, letterSpacing: '-0.2px' }}>
        {name}
      </div>
      <div style={{ fontSize: 13, fontFamily: font.mono, whiteSpace: 'nowrap' }}>{right}</div>
      <div style={{ fontSize: 11, color: color.muted, fontFamily: font.mono, whiteSpace: 'nowrap' }}>
        {countdown}
      </div>
    </Link>
  )
}

function SellingRow({ auction }: { auction: AuctionListing }) {
  const countdown = useCountdown(auction.deadline)
  return (
    <AuctionRowLayout name={auction.rider.name} right={formatMoney(auction.current_price)} countdown={countdown} />
  )
}

function BiddingRow({ bid }: { bid: MyBidStatus }) {
  const countdown = useCountdown(bid.deadline)
  const status = bid.is_high_bidder ? 'Winning' : 'Outbid'
  return (
    <Link
      to="/transfers"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '11px 20px',
        textDecoration: 'none',
        color: color.ink,
      }}
    >
      <div style={{ flex: 1, minWidth: 0, fontSize: 14, fontWeight: 600, letterSpacing: '-0.2px' }}>
        {bid.rider_name}
      </div>
      <div
        style={{
          fontSize: 11.5,
          fontWeight: 600,
          color: bid.is_high_bidder ? color.positive : color.negative,
        }}
      >
        {status}
      </div>
      <div style={{ fontSize: 13, fontFamily: font.mono, whiteSpace: 'nowrap' }}>
        {formatMoney(bid.current_price)}
      </div>
      <div style={{ fontSize: 11, color: color.muted, fontFamily: font.mono, whiteSpace: 'nowrap' }}>
        {countdown}
      </div>
    </Link>
  )
}