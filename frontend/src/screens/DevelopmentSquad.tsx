import { useState } from 'react'

import {
  changeDevelopmentSquadLevel,
  closeDevelopmentSquad,
  openDevelopmentSquad,
} from '../api'
import { Button, Card, PageBody, PageHeading } from '../components/primitives'
import { formatMoney } from '../format'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useDevelopmentSquad } from '../useDevelopmentSquad'

/** Inline SVG, as `AttributeRadar` and `AttributeHistoryChart` do — there is
 * no icon library to reach for, and one padlock does not justify one. Takes
 * `currentColor` from the surrounding text, so a locked card dims with
 * everything else on it. */
function Padlock({ size = 12 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
      style={{ flex: '0 0 auto' }}
    >
      <path
        d="M4.75 7V5.25a3.25 3.25 0 0 1 6.5 0V7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <rect x="3.25" y="7" width="9.5" height="6.75" rx="1.5" fill="currentColor" />
    </svg>
  )
}

export function DevelopmentSquad() {
  const { me, loading: authLoading } = useAuth()
  const hasTeam = me?.team != null

  const { squad, loading, error, refresh } = useDevelopmentSquad()
  const [actionError, setActionError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  if (authLoading || loading) return null

  if (!hasTeam) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            You do not manage a team, so there is no development squad to show here.
          </div>
        </Card>
      </PageBody>
    )
  }

  if (error || !squad) {
    return (
      <PageBody gap={18} paddingTop={26}>
        <Card style={{ padding: '18px 20px' }}>
          <div style={{ fontSize: 13.5, color: color.muted }}>
            Couldn't load your development squad.
          </div>
        </Card>
      </PageBody>
    )
  }

  const isOpen = squad.level !== null
  const currentName = squad.levels.find((l) => l.action === 'current')?.name

  const run = async (action: () => Promise<void>, failureMessage: string) => {
    setPending(true)
    setActionError(null)
    try {
      await action()
      refresh()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : failureMessage)
    } finally {
      setPending(false)
    }
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="TEAM · DEVELOPMENT SQUAD"
        title="Development squad"
        titleSize={29}
        subtitle={
          // Money, and nothing else. The spec is explicit that this screen
          // must not promise riders or say "coming soon" (#33 owns youth
          // intake, and a higher level's effect on it is #33's decision, not
          // this one's). A subtitle that told a manager a squad develops
          // riders faster would be a promise about behaviour that does not
          // exist yet — and one they would pay real money for.
          isOpen
            ? `Running at ${currentName}, charged its weekly cost every week.`
            : 'Closed. A squad starts at Regional, and each level above costs more to reach and to run.'
        }
      />

      {actionError ? (
        <Card style={{ padding: '12px 16px', borderColor: '#D9534F' }}>
          <div style={{ fontSize: 13, color: '#D9534F' }}>{actionError}</div>
        </Card>
      ) : null}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(288px, 1fr))',
          gap: 12,
        }}
      >
        {squad.levels.map((level) => {
          const kind = level.action
          // Only the two levels with a move can cost more than the balance.
          // A locked level has no button at all, and the level already held
          // has already been paid for.
          const actionable = kind === 'open' || kind === 'upgrade'
          const affordable = level.fee <= squad.balance

          return (
            <Card
              key={level.level}
              style={{
                padding: '15px 16px',
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
                opacity: kind === 'current' || kind === 'locked' ? 0.7 : 1,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 11,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 15,
                    fontWeight: 700,
                    fontFamily: font.mono,
                    background: color.canvas,
                    color: color.ink,
                    flex: '0 0 40px',
                  }}
                >
                  {level.level}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14.5, fontWeight: 600, letterSpacing: '-0.2px' }}>
                    {level.name}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: color.mutedStrong,
                      fontFamily: font.mono,
                      marginTop: 3,
                    }}
                  >
                    LEVEL {level.level}
                  </div>
                </div>
                {kind === 'current' ? (
                  // A span, not the Chip primitive: that one is a filter
                  // toggle, and this is a label with nothing to toggle.
                  <span
                    style={{
                      padding: '5px 10px',
                      borderRadius: 8,
                      fontSize: 11,
                      fontFamily: font.mono,
                      letterSpacing: '0.6px',
                      border: `1px solid ${color.borderButton}`,
                      color: color.mutedStrong,
                    }}
                  >
                    CURRENT
                  </span>
                ) : actionable ? (
                  <Button
                    onClick={() =>
                      run(
                        () =>
                          kind === 'open'
                            ? openDevelopmentSquad(level.level)
                            : changeDevelopmentSquadLevel(level.level),
                        kind === 'open'
                          ? 'Could not open your development squad.'
                          : 'Could not upgrade your development squad.',
                      )
                    }
                    disabled={!affordable || pending}
                    style={{ opacity: pending || !affordable ? 0.6 : 1 }}
                  >
                    {kind === 'open' ? 'Open' : 'Upgrade'}
                  </Button>
                ) : null}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                {/* The increment onto this level, which is also what the move
                    would charge: level 1's fee opens the squad, and every
                    level above is reached by paying its own in full. Labelled
                    by the rung's place in the ladder rather than by what the
                    team can do about it, so the three cards read as one price
                    list and the climb is legible at a glance. */}
                <Figure
                  label={level.level === 1 ? 'Open fee' : 'Upgrade fee'}
                  value={formatMoney(level.fee)}
                />
                <Figure label="Weekly cost" value={`${formatMoney(level.weekly_cost)}/week`} />
                <Figure label="Per season" value={formatMoney(level.season_cost)} />
              </div>

              {kind === 'locked' ? (
                // The server's own words for why, because there are two
                // different reasons and only it knows which applies.
                <div
                  style={{
                    borderTop: `1px solid ${color.dividerStrong}`,
                    paddingTop: 10,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 7,
                    color: color.mutedStrong,
                    fontSize: 12,
                  }}
                >
                  <Padlock />
                  <span>{level.requires}</span>
                </div>
              ) : null}

              {actionable && !affordable ? (
                <div style={{ fontSize: 12, color: color.negative }}>
                  You cannot afford this.
                </div>
              ) : null}
            </Card>
          )
        })}
      </div>

      {isOpen ? (
        <Card style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ flex: 1, fontSize: 12.5, color: color.muted }}>
            {/* Closing is the only way to spend less — there is no cheaper
                level to step down to — and it is the reason a manager reaches
                for it under pressure, so the cost of that has to be on the
                card: nothing is refunded, and reopening starts at Regional
                again. */}
            Closing stops the weekly cost. Nothing is refunded, and reopening starts at
            Regional again.
          </div>
          <Button
            onClick={() =>
              run(closeDevelopmentSquad, 'Could not close your development squad.')
            }
            disabled={pending}
            style={{ opacity: pending ? 0.6 : 1 }}
          >
            Close squad
          </Button>
        </Card>
      ) : null}
    </PageBody>
  )
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
      <span style={{ fontSize: 12.5, color: '#565A61' }}>{label}</span>
      <span style={{ fontSize: 12, fontFamily: font.mono, fontWeight: 600 }}>{value}</span>
    </div>
  )
}
