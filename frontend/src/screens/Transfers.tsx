import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { placeBid, signFreeAgent, type AuctionListing, type FreeAgent } from '../api'
import { AuctionCard } from '../components/AuctionCard'
import { Button, Card, Chip, ChipLabel, FinalSeasonTag, LabelBar, PageBody, PageHeading, StatTile } from '../components/primitives'
import { formatMoney } from '../format'
import { riderPath } from '../navigation'
import { color, font } from '../theme'
import { useAuctions } from '../useAuctions'
import { useAuth } from '../useAuth'
import { useClock } from '../useClock'
import { useFreeAgents } from '../useFreeAgents'
import { useMyBids } from '../useMyBids'

type AttrKey = 'climb' | 'sprint' | 'flat' | 'resistance' | 'positioning'

const ATTR_KEYS: { key: AttrKey; label: string }[] = [
  { key: 'climb', label: 'CLM' },
  { key: 'sprint', label: 'SPR' },
  { key: 'flat', label: 'FLT' },
  { key: 'resistance', label: 'RES' },
  { key: 'positioning', label: 'POS' },
]

type SortKey = 'price' | 'name' | 'age' | 'weekly_salary' | 'market_value' | AttrKey

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: 'price', label: 'Price' },
  { key: 'weekly_salary', label: 'Salary' },
  { key: 'market_value', label: 'Value' },
  { key: 'name', label: 'Name' },
  { key: 'age', label: 'Age' },
  { key: 'climb', label: 'Climbing' },
  { key: 'sprint', label: 'Sprinting' },
  { key: 'flat', label: 'Flat' },
  { key: 'resistance', label: 'Resistance' },
  { key: 'positioning', label: 'Positioning' },
]

/** One rider the manager could buy (#154): a free agent to sign now, or
 * someone else's auction to bid on. Both sit in one list, filtered and
 * sorted together. `price` is the common key the sort reads — the signing
 * fee for a free agent, the minimum next bid for an auction, i.e. what it
 * would cost to act on the card right now. */
type BuyItem =
  | { kind: 'agent'; key: string; rider: FreeAgent; price: number; agent: FreeAgent }
  | { kind: 'auction'; key: string; rider: AuctionListing['rider']; price: number; auction: AuctionListing }

export function Transfers() {
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

  const { pool, loading: agentsLoading, error: agentsError, refresh: refreshAgents } = useFreeAgents()
  const { market, loading: marketLoading, error: marketError, refresh: refreshMarket } = useAuctions()
  const { bids: myBids, refresh: refreshMyBids } = useMyBids()
  const { now: gameNow } = useClock()
  const { hash } = useLocation()

  const [actionError, setActionError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [filter, setFilter] = useState<'All' | string>('All')
  const [sort, setSort] = useState<SortKey>('price')

  const myListings = useMemo(() => market?.auctions.filter((a) => a.is_own_listing) ?? [], [market])

  const buyItems = useMemo<BuyItem[]>(() => {
    const agents: BuyItem[] = (pool?.riders ?? []).map((agent) => ({
      kind: 'agent',
      key: `agent-${agent.id}`,
      rider: agent,
      price: agent.signing_fee,
      agent,
    }))
    const auctions: BuyItem[] = (market?.auctions ?? [])
      .filter((auction) => !auction.is_own_listing)
      .map((auction) => ({
        kind: 'auction',
        key: `auction-${auction.id}`,
        rider: auction.rider,
        price: auction.min_next_bid,
        auction,
      }))
    return [...agents, ...auctions]
  }, [pool, market])

  const specialities = useMemo(
    () => Array.from(new Set(buyItems.map((item) => item.rider.speciality))).sort(),
    [buyItems],
  )

  const visible = useMemo(() => {
    const list = buyItems.filter((item) => filter === 'All' || item.rider.speciality === filter)
    return [...list].sort((a, b) => {
      if (sort === 'price') return a.price - b.price
      if (sort === 'name') return a.rider.name.localeCompare(b.rider.name)
      if (sort === 'age') return a.rider.age - b.rider.age
      if (sort === 'weekly_salary') return a.rider.weekly_salary - b.rider.weekly_salary
      if (sort === 'market_value') return a.rider.market_value - b.rider.market_value
      return b.rider[sort] - a.rider[sort]
    })
  }, [buyItems, filter, sort])

  // The Roster's "View on Transfers" link (#152) lands on #auction-<id>:
  // bring that listing's card into view once the market has loaded, and
  // only once per hash. The market re-polls every 30 s and after each bid,
  // and the hash stays in the URL, so without the ref every refresh would
  // pull the manager back up from wherever they had scrolled to.
  const scrolledTo = useRef<string | null>(null)
  useEffect(() => {
    if (!hash || !market || scrolledTo.current === hash) return
    const card = document.getElementById(hash.slice(1))
    if (!card) return
    card.scrollIntoView?.({ block: 'center' })
    scrolledTo.current = hash
  }, [hash, market])

  const outbid = myBids.filter((bid) => !bid.is_high_bidder)

  if (authLoading) return null

  if (!hasTeam) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            You do not manage a team, so the transfer market is closed to you.
          </div>
        </Card>
      </PageBody>
    )
  }

  const handleSign = async (agent: FreeAgent) => {
    setPending(true)
    setActionError(null)
    try {
      await signFreeAgent(agent.id)
      refreshAgents()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not sign that rider.')
    } finally {
      setPending(false)
    }
  }

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

  // Both payloads carry the team's balance. Each card checks affordability
  // against its own payload's figure, and the header shows whichever arrived.
  const balance = pool?.balance ?? market?.balance ?? 0
  const signBalance = pool?.balance ?? 0
  const bidBalance = market?.balance ?? 0
  const marketReady = !marketLoading && !marketError && market !== null
  const buyLoading = agentsLoading || marketLoading

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="MARKET · TRANSFERS"
        title="Transfers"
        titleSize={29}
        subtitle="Sell: your riders on auction. Buy: free agents sign at once for a one-off fee, auctions go to the highest bid."
        aside={
          <>
            <StatTile label="BALANCE" value={formatMoney(balance)} minWidth={160} />
            <StatTile label="FOR SALE" value={String(myListings.length)} minWidth={96} />
            <StatTile label="AVAILABLE" value={String(buyItems.length)} minWidth={104} />
          </>
        }
      />

      {actionError ? (
        <Card style={{ padding: '12px 16px', borderColor: '#D9534F' }}>
          <div style={{ fontSize: 13, color: '#D9534F' }}>{actionError}</div>
        </Card>
      ) : null}

      <section aria-label="Sell" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <SectionHeading title="Sell" count={marketReady ? myListings.length : null} />
        {marketLoading ? null : !marketReady ? (
          <Card style={{ padding: '18px 20px' }}>
            <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load your listings.</div>
          </Card>
        ) : myListings.length === 0 ? (
          <Card style={{ padding: '18px 20px' }}>
            <div style={{ fontSize: 13.5, color: color.muted }}>
              Nothing for sale. Pick a rider on your{' '}
              <Link to="/roster" style={{ color: color.accentInk, fontWeight: 600, textDecoration: 'none' }}>
                Roster
              </Link>{' '}
              and list them for auction.
            </div>
          </Card>
        ) : (
          <CardGrid>
            {myListings.map((auction) => (
              <div key={auction.id} id={`auction-${auction.id}`}>
                <AuctionCard
                  auction={auction}
                  balance={bidBalance}
                  pending={pending}
                  gameNow={gameNow}
                  onBid={(amount) => handleBid(auction, amount)}
                />
              </div>
            ))}
          </CardGrid>
        )}
      </section>

      <section aria-label="Buy" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <SectionHeading title="Buy" count={buyLoading ? null : buyItems.length} />

        {outbid.length > 0 ? (
          <Card style={{ padding: '12px 16px', borderColor: color.accent }}>
            <div style={{ fontSize: 13, color: color.ink }}>
              {outbid.map((bid) => (
                <div key={bid.auction_id}>
                  You've been outbid on {bid.rider_name} — current price {formatMoney(bid.current_price)}.
                </div>
              ))}
            </div>
          </Card>
        ) : null}

        {buyLoading ? null : (
          <>
            {agentsError || !pool ? (
              <Card style={{ padding: '12px 16px' }}>
                <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load the free agent pool.</div>
              </Card>
            ) : null}
            {marketError || !market ? (
              <Card style={{ padding: '12px 16px' }}>
                <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load the auction market.</div>
              </Card>
            ) : null}

            <Card style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '14px 16px' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
                <ChipLabel>SPECIALITY</ChipLabel>
                {['All', ...specialities].map((f) => (
                  <Chip key={f} active={filter === f} onClick={() => setFilter(f)}>
                    {f}
                  </Chip>
                ))}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
                <ChipLabel>SORT</ChipLabel>
                {SORT_OPTIONS.map((o) => (
                  <Chip key={o.key} active={sort === o.key} onClick={() => setSort(o.key)}>
                    {o.label}
                  </Chip>
                ))}
                <span
                  style={{
                    marginLeft: 'auto',
                    fontSize: 12,
                    color: color.muted,
                    fontFamily: font.mono,
                  }}
                >
                  {visible.length} of {buyItems.length} riders
                </span>
              </div>
            </Card>

            {buyItems.length === 0 ? (
              <Card style={{ padding: '18px 20px' }}>
                <div style={{ fontSize: 13.5, color: color.muted }}>
                  Nobody is on the market right now. Riders released by other teams land in the free
                  agent pool, and other managers' auctions show up here.
                </div>
              </Card>
            ) : null}

            <CardGrid>
              {visible.map((item) =>
                item.kind === 'agent' ? (
                  <FreeAgentCard
                    key={item.key}
                    agent={item.agent}
                    note={
                      item.agent.signing_fee <= signBalance ? undefined : "You cannot afford this rider's signing fee."
                    }
                    action={
                      <Button
                        onClick={() => handleSign(item.agent)}
                        disabled={item.agent.signing_fee > signBalance || pending}
                        style={{ opacity: pending || item.agent.signing_fee > signBalance ? 0.6 : 1 }}
                      >
                        Sign
                      </Button>
                    }
                  />
                ) : (
                  <AuctionCard
                    key={item.key}
                    auction={item.auction}
                    balance={bidBalance}
                    pending={pending}
                    gameNow={gameNow}
                    onBid={(amount) => handleBid(item.auction, amount)}
                    tag={<MarketTag>AUCTION</MarketTag>}
                  />
                ),
              )}
            </CardGrid>
          </>
        )}
      </section>
    </PageBody>
  )
}

function SectionHeading({ title, count }: { title: string; count: number | null }) {
  return (
    <h2
      style={{
        margin: 0,
        display: 'flex',
        alignItems: 'baseline',
        gap: 8,
        fontSize: 17,
        fontWeight: 600,
        letterSpacing: '-0.3px',
        color: color.ink,
      }}
    >
      {title}
      {count !== null ? (
        <span style={{ fontSize: 12, fontWeight: 400, color: color.muted, fontFamily: font.mono }}>{count}</span>
      ) : null}
    </h2>
  )
}

function CardGrid({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(288px, 1fr))',
        gap: 12,
      }}
    >
      {children}
    </div>
  )
}

/** Tells the two kinds of Buy card apart at a glance (#154): a free agent
 * signs now at a fixed fee, an auction goes to the highest bid. */
function MarketTag({ children }: { children: ReactNode }) {
  return (
    <span
      style={{
        alignSelf: 'flex-start',
        marginTop: 4,
        fontSize: 10.5,
        letterSpacing: '1px',
        fontFamily: font.mono,
        color: color.mutedStrong,
        background: color.canvas,
        borderRadius: 6,
        padding: '2px 7px',
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </span>
  )
}

function FreeAgentCard({
  agent,
  action,
  note,
}: {
  agent: FreeAgent
  action: ReactNode
  note?: string
}) {
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
          {agent.speciality.slice(0, 2).toUpperCase()}
        </div>
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <Link
              to={riderPath(agent.id)}
              style={{
                display: 'block',
                fontSize: 14.5,
                fontWeight: 600,
                letterSpacing: '-0.2px',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                color: color.ink,
                textDecoration: 'none',
              }}
            >
              {agent.name}
            </Link>
            {agent.final_season ? <FinalSeasonTag /> : null}
          </div>
          <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
            {agent.speciality.toUpperCase()} · {agent.age} yrs
          </div>
          <MarketTag>FREE AGENT · SIGN NOW</MarketTag>
        </div>
        {action}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {ATTR_KEYS.map(({ key, label }) => (
          <LabelBar key={key} label={label} value={agent[key]} />
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
          Fee {formatMoney(agent.signing_fee)}
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
          <span style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
            {formatMoney(agent.weekly_salary)}/wk
          </span>
          <span style={{ fontSize: 10.5, color: color.muted, fontFamily: font.mono }}>
            <span style={{ letterSpacing: '0.4px' }}>VALUE </span>
            {formatMoney(agent.market_value)}
          </span>
        </span>
      </div>

      {note ? (
        <div style={{ fontSize: 12, color: color.negative }}>{note}</div>
      ) : null}
    </Card>
  )
}