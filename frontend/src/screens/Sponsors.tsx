import { useState } from 'react'

import { signOffer, type SponsorContract, type SponsorOffer } from '../api'
import { Button, Card, PageBody, PageHeading } from '../components/primitives'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useSponsors } from '../useSponsors'

/** The game's abstract currency — see AGENTS.md, *Displaying game money*.
 * Thousands-separated, never decimals, prefixed "$" — matching
 * Finances.tsx's formatMoney. The range's two ends are both money, so both
 * get the prefix. */
function formatMoney(amount: number): string {
  return `$${amount.toLocaleString('en-US')}`
}

export function Sponsors() {
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

  const { sponsors, loading, error, refresh } = useSponsors()
  const [actionError, setActionError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  if (authLoading || loading) return null

  if (!hasTeam) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            You do not manage a team, so there is no sponsorship to show here.
          </div>
        </Card>
      </PageBody>
    )
  }

  if (error || !sponsors) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>Couldn't load sponsors.</div>
        </Card>
      </PageBody>
    )
  }

  const handleSign = async (offerId: number) => {
    setPending(true)
    setActionError(null)
    try {
      await signOffer(offerId)
      refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not sign that offer.')
    } finally {
      setPending(false)
    }
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="TEAM · SPONSORS"
        title="Sponsors"
        titleSize={29}
        subtitle={
          sponsors.contract
            ? 'Your sponsor pays every week, more when you race well.'
            : 'Three companies want to sponsor your team this season — sign one, or none.'
        }
      />

      {actionError ? (
        <Card style={{ padding: '12px 16px', borderColor: '#D9534F' }}>
          <div style={{ fontSize: 13, color: '#D9534F' }}>{actionError}</div>
        </Card>
      ) : null}

      {sponsors.contract ? (
        <ContractCard contract={sponsors.contract} />
      ) : sponsors.offers.length === 0 ? (
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            No sponsor offers right now — check back once the season is underway.
          </div>
        </Card>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(288px, 1fr))',
            gap: 12,
          }}
        >
          {sponsors.offers.map((offer) => (
            <OfferCard
              key={offer.id}
              offer={offer}
              action={
                <Button onClick={() => handleSign(offer.id)} style={{ opacity: pending ? 0.6 : 1 }}>
                  Sign
                </Button>
              }
            />
          ))}
        </div>
      )}
    </PageBody>
  )
}

function OfferCard({ offer, action }: { offer: SponsorOffer; action: React.ReactNode }) {
  return (
    <Card style={{ padding: '15px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
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
            {offer.sponsor_name}
          </div>
          <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
            {offer.label.toUpperCase()}
          </div>
        </div>
        {action}
      </div>

      <div style={{ fontSize: 12.5, color: '#565A61' }}>{offer.blurb}</div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ fontSize: 20, fontWeight: 700, fontFamily: font.mono }}>
          {formatMoney(offer.weekly_base)}
          <span style={{ fontSize: 12, fontWeight: 500, color: color.muted }}> / week</span>
        </div>
        <div style={{ fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>
          {formatMoney(offer.floor_amount)} – {formatMoney(offer.ceiling_amount)}
        </div>
      </div>
    </Card>
  )
}

function ContractCard({ contract }: { contract: SponsorContract }) {
  return (
    <Card style={{ padding: '15px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <div style={{ fontSize: 14.5, fontWeight: 600, letterSpacing: '-0.2px' }}>
          {contract.sponsor_name}
        </div>
        <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
          {contract.label.toUpperCase()} · SIGNED
        </div>
      </div>

      <div style={{ fontSize: 12.5, color: '#565A61' }}>{contract.blurb}</div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ fontSize: 20, fontWeight: 700, fontFamily: font.mono }}>
          {formatMoney(contract.weekly_base)}
          <span style={{ fontSize: 12, fontWeight: 500, color: color.muted }}> / week baseline</span>
        </div>
        <div style={{ fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>
          {formatMoney(contract.floor_amount)} – {formatMoney(contract.ceiling_amount)} range
        </div>
      </div>
    </Card>
  )
}
