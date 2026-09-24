import { useMemo, useState, type ReactNode } from 'react'

import { placeBid, signFreeAgent, type AuctionListing, type FreeAgent } from '../api'
import { Button, Card, Chip, ChipLabel, LabelBar, PageBody, PageHeading, StatTile } from '../components/primitives'
import { formatMoney } from '../format'
import { color, font } from '../theme'
import { useAuctions } from '../useAuctions'
import { useAuth } from '../useAuth'
import { useCountdown } from '../useCountdown'
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

type SortKey =
  | 'name'
  | 'age'
  | 'signing_fee'
  | 'weekly_salary'
  | 'market_value'
  | AttrKey

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: 'signing_fee', label: 'Signing fee' },
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

type MarketTab = 'agents' | 'auctions'

export function Transfers() {
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

  const [tab, setTab] = useState<MarketTab>('agents')

  const { pool, loading: agentsLoading, error: agentsError, refresh: refreshAgents } = useFreeAgents()
  const { market, loading: marketLoading, error: marketError, refresh: refreshMarket } = useAuctions()
  const { bids: myBids, refresh: refreshMyBids } = useMyBids()

  const [actionError, setActionError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [filter, setFilter] = useState<'All' | string>('All')
  const [sort, setSort] = useState<SortKey>('signing_fee')

  const specialities = useMemo(() => {
    if (!pool) return []
    return Array.from(new Set(pool.riders.map((r) => r.speciality))).sort()
  }, [pool])

  const visible = useMemo(() => {
    if (!pool) return []
    const list = pool.riders.filter((r) => filter === 'All' || r.speciality === filter)
    return [...list].sort((a, b) => {
      if (sort === 'name') return a.name.localeCompare(b.name)
      if (sort === 'age') return a.age - b.age
      if (sort === 'signing_fee') return a.signing_fee - b.signing_fee
      if (sort === 'weekly_salary') return a.weekly_salary - b.weekly_salary
      if (sort === 'market_value') return a.market_value - b.market_value
      return b[sort] - a[sort]
    })
  }, [pool, filter, sort])

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

  const balance = tab === 'agents' ? pool?.balance : market?.balance

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="MARKET · TRANSFERS"
        title="Transfers"
        titleSize={29}
        subtitle="Free agents sign with a one-off fee. Auction a rider from your roster, or bid on someone else's."
        aside={
          <>
            <StatTile label="BALANCE" value={formatMoney(balance ?? 0)} minWidth={160} />
            {tab === 'agents' ? (
              <StatTile label="FREE AGENTS" value={String(pool?.riders.length ?? 0)} minWidth={104} />
            ) : (
              <StatTile label="LIVE AUCTIONS" value={String(market?.auctions.length ?? 0)} minWidth={112} />
            )}
          </>
        }
      />

      {actionError ? (
        <Card style={{ padding: '12px 16px', borderColor: '#D9534F' }}>
          <div style={{ fontSize: 13, color: '#D9534F' }}>{actionError}</div>
        </Card>
      ) : null}

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

      <Card style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '14px 16px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <ChipLabel>MARKET</ChipLabel>
          <Chip active={tab === 'agents'} onClick={() => setTab('agents')}>
            Free agents
          </Chip>
          <Chip active={tab === 'auctions'} onClick={() => setTab('auctions')}>
            Auctions
          </Chip>
        </div>
      </Card>

      {tab === 'agents' ? (
        <FreeAgentsTab
          loading={agentsLoading}
          error={agentsError}
          pool={pool}
          filter={filter}
          setFilter={setFilter}
          sort={sort}
          setSort={setSort}
          specialities={specialities}
          visible={visible}
          pending={pending}
          onSign={handleSign}
        />
      ) : (
        <AuctionsTab
          loading={marketLoading}
          error={marketError}
          market={market}
          pending={pending}
          onBid={handleBid}
        />
      )}
    </PageBody>
  )
}

function FreeAgentsTab({
  loading,
  error,
  pool,
  filter,
  setFilter,
  sort,
  setSort,
  specialities,
  visible,
  pending,
  onSign,
}: {
  loading: boolean
  error: boolean
  pool: { riders: FreeAgent[]; balance: number } | null
  filter: string
  setFilter: (f: string) => void
  sort: SortKey
  setSort: (s: SortKey) => void
  specialities: string[]
  visible: FreeAgent[]
  pending: boolean
  onSign: (agent: FreeAgent) => void
}) {
  if (loading) return null

  if (error || !pool) {
    return (
      <Card style={{ padding: '18px 20px' }}>
        <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load the free agent pool.</div>
      </Card>
    )
  }

  return (
    <>
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
            {visible.length} of {pool.riders.length} free agents
          </span>
        </div>
      </Card>

      {pool.riders.length === 0 ? (
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            No free agents right now — riders released by claims and teams land here.
          </div>
        </Card>
      ) : null}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(288px, 1fr))',
          gap: 12,
        }}
      >
        {visible.map((agent) => {
          const affordable = agent.signing_fee <= pool.balance
          return (
            <FreeAgentCard
              key={agent.id}
              agent={agent}
              note={affordable ? undefined : "You cannot afford this rider's signing fee."}
              action={
                <Button
                  onClick={() => onSign(agent)}
                  disabled={!affordable || pending}
                  style={{ opacity: pending || !affordable ? 0.6 : 1 }}
                >
                  Sign
                </Button>
              }
            />
          )
        })}
      </div>
    </>
  )
}

function AuctionsTab({
  loading,
  error,
  market,
  pending,
  onBid,
}: {
  loading: boolean
  error: boolean
  market: { auctions: AuctionListing[]; balance: number } | null
  pending: boolean
  onBid: (auction: AuctionListing, amount: number) => void
}) {
  if (loading) return null

  if (error || !market) {
    return (
      <Card style={{ padding: '18px 20px' }}>
        <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load the auction market.</div>
      </Card>
    )
  }

  if (market.auctions.length === 0) {
    return (
      <Card style={{ padding: '18px 20px' }}>
        <div style={{ fontSize: 13.5, color: color.muted }}>
          No live auctions right now — list a rider from your roster to start one.
        </div>
      </Card>
    )
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(288px, 1fr))',
        gap: 12,
      }}
    >
      {market.auctions.map((auction) => (
        <AuctionCard
          key={auction.id}
          auction={auction}
          balance={market.balance}
          pending={pending}
          onBid={(amount) => onBid(auction, amount)}
        />
      ))}
    </div>
  )
}

function AuctionCard({
  auction,
  balance,
  pending,
  onBid,
}: {
  auction: AuctionListing
  balance: number
  pending: boolean
  onBid: (amount: number) => void
}) {
  const [amount, setAmount] = useState(auction.min_next_bid)
  const rider = auction.rider
  const affordable = amount <= balance
  const clearsIncrement = amount >= auction.min_next_bid
  const countdown = useCountdown(auction.deadline)

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
    </Card>
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
            {agent.name}
          </div>
          <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
            {agent.speciality.toUpperCase()} · {agent.age} yrs
          </div>
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