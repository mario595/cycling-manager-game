import { useState } from 'react'

import {
  changeDevelopmentSquadLevel,
  closeDevelopmentSquad,
  openDevelopmentSquad,
  type DevelopmentSquadLevel,
} from '../api'
import { Button, Card, PageBody, PageHeading } from '../components/primitives'
import { formatMoney } from '../format'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useDevelopmentSquad } from '../useDevelopmentSquad'

/** What the one action on a level card does, from the card's own data rather
 * than from comparing levels in the client. The server sends `is_current` and
 * a null `change_fee` only for the level already held, and prices every other
 * move exactly as it would charge it — so this decides the *wording*, never
 * the figure. */
type ActionKind = 'open' | 'upgrade' | 'downgrade' | 'current'

function actionFor(level: DevelopmentSquadLevel, squadIsOpen: boolean): ActionKind {
  if (level.is_current) return 'current'
  if (!squadIsOpen) return 'open'
  return level.change_fee !== null && level.change_fee > 0 ? 'upgrade' : 'downgrade'
}

const ACTION_LABELS: Record<ActionKind, string> = {
  open: 'Open',
  upgrade: 'Upgrade',
  downgrade: 'Downgrade',
  current: 'Current',
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
  const currentName = squad.levels.find((l) => l.is_current)?.name

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
            : 'Closed. Opening a level pays its opening fee, then a weekly cost.'
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
          const kind = actionFor(level, isOpen)
          // A downgrade is priced at zero, so it is never unaffordable; the
          // server would refuse it as a no-op anyway, which is why the current
          // level has no button at all.
          const fee = level.change_fee ?? 0
          const affordable = fee <= squad.balance
          const dimmed = kind === 'current'

          return (
            <Card
              key={level.level}
              style={{
                padding: '15px 16px',
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
                opacity: dimmed ? 0.75 : 1,
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
                ) : (
                  <Button
                    onClick={() =>
                      run(
                        () =>
                          kind === 'open'
                            ? openDevelopmentSquad(level.level)
                            : changeDevelopmentSquadLevel(level.level),
                        kind === 'open'
                          ? 'Could not open your development squad.'
                          : 'Could not change your development squad level.',
                      )
                    }
                    disabled={!affordable || pending}
                    style={{ opacity: pending || !affordable ? 0.6 : 1 }}
                  >
                    {ACTION_LABELS[kind]}
                  </Button>
                )}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                <Figure label="Opening fee" value={formatMoney(level.opening_fee)} />
                <Figure label="Weekly cost" value={`${formatMoney(level.weekly_cost)}/week`} />
                <Figure label="Per season" value={formatMoney(level.season_cost)} />
              </div>

              {/* Neither while closed, where the move is an opening already
                  priced in the "Opening fee" row above and printing it twice
                  on one card is noise, nor for the level already held, where
                  there is no move to price at all. */}
              {isOpen && kind !== 'current' ? (
                <div
                  style={{
                    borderTop: `1px solid ${color.dividerStrong}`,
                    paddingTop: 10,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 10,
                  }}
                >
                  <span style={{ fontSize: 12, color: color.mutedStrong }}>
                    {kind === 'downgrade' ? 'Downgrading is free' : 'To move here'}
                  </span>
                  <span style={{ fontSize: 12, fontFamily: font.mono, fontWeight: 600 }}>
                    {fee === 0 ? 'Free' : formatMoney(fee)}
                  </span>
                </div>
              ) : null}

              {kind !== 'current' && !affordable ? (
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
            Closing stops the weekly cost. Nothing is refunded, and the opening fee stays in your
            finances.
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
