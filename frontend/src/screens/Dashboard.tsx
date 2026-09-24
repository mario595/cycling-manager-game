import { useState } from 'react'
import { Link } from 'react-router-dom'

import { placeBid, type AuctionListing } from '../api'
import { AuctionCard } from '../components/AuctionCard'
import { Card, CardHeader, PageBody, PageHeading } from '../components/primitives'
import { nextRace } from '../nextRace'
import { seasonLabel } from '../seasonLabel'
import { color, font } from '../theme'
import { useAuctions } from '../useAuctions'
import { useAuth } from '../useAuth'
import { useCalendar } from '../useCalendar'
import { useClock } from '../useClock'
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
 * as the same AuctionCard the Transfers screen uses, so an auction reads
 * and acts identically wherever it appears. Renders nothing while
 * loading, or once loaded if there is nothing to show. */
function MyAuctionsSection() {
  const { market, loading, refresh: refreshMarket } = useAuctions()
  const { bids, refresh: refreshMyBids } = useMyBids()
  const { now: gameNow } = useClock()
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  if (loading) return null

  const auctions = market?.auctions ?? []
  const selling = auctions.filter((a) => a.is_own_listing)
  const biddingIds = new Set(bids.map((b) => b.auction_id))
  const bidding = auctions.filter((a) => biddingIds.has(a.id))

  if (selling.length === 0 && bidding.length === 0) return null

  const handleBid = async (auction: AuctionListing, amount: number) => {
    setPending(true)
    setActionError(null)
    try {
      await placeBid(auction.id, amount)
      refreshMarket()
      refreshMyBids()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not place that bid.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.2px' }}>My auctions</div>

      {actionError ? (
        <Card style={{ padding: '12px 16px', borderColor: '#D9534F' }}>
          <div style={{ fontSize: 13, color: '#D9534F' }}>{actionError}</div>
        </Card>
      ) : null}

      {selling.length > 0 ? (
        <AuctionGroup
          title="Selling"
          auctions={selling}
          balance={market?.balance ?? 0}
          pending={pending}
          gameNow={gameNow}
          onBid={handleBid}
        />
      ) : null}
      {bidding.length > 0 ? (
        <AuctionGroup
          title="Bidding"
          auctions={bidding}
          balance={market?.balance ?? 0}
          pending={pending}
          gameNow={gameNow}
          onBid={handleBid}
        />
      ) : null}
    </div>
  )
}

function AuctionGroup({
  title,
  auctions,
  balance,
  pending,
  gameNow,
  onBid,
}: {
  title: string
  auctions: AuctionListing[]
  balance: number
  pending: boolean
  gameNow: Date | null
  onBid: (auction: AuctionListing, amount: number) => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 10.5, letterSpacing: '0.8px', color: color.mutedStrong, fontFamily: font.mono }}>
        {title.toUpperCase()}
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(288px, 1fr))',
          gap: 12,
        }}
      >
        {auctions.map((auction) => (
          <AuctionCard
            key={auction.id}
            auction={auction}
            balance={balance}
            pending={pending}
            gameNow={gameNow}
            onBid={(amount) => onBid(auction, amount)}
          />
        ))}
      </div>
    </div>
  )
}