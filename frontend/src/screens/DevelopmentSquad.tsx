import { useState } from 'react'
import { Link } from 'react-router-dom'

import {
  changeDevelopmentSquadLevel,
  closeDevelopmentSquad,
  discardSquadRider,
  listForAuction,
  openDevelopmentSquad,
  promoteSquadRider,
  type DevelopmentSquadGraduate,
  type DevelopmentSquadRider,
} from '../api'
import { Button, Card, CardHeader, LabelBar, PageBody, PageHeading } from '../components/primitives'
import { formatMoney } from '../format'
import { riderPath } from '../navigation'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useDevelopmentSquad } from '../useDevelopmentSquad'

type AttrKey = 'climb' | 'sprint' | 'flat' | 'resistance' | 'positioning'

const ATTR_KEYS: { key: AttrKey; label: string }[] = [
  { key: 'climb', label: 'CLM' },
  { key: 'sprint', label: 'SPR' },
  { key: 'flat', label: 'FLT' },
  { key: 'resistance', label: 'RES' },
  { key: 'positioning', label: 'POS' },
]

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
  const intake = squad.intake
  // Promote writes to the team roster, so a full roster is what stops it —
  // reported from the payload's own roster_count/roster_cap rather than
  // discovered by pressing the button and eating a 409 (#34).
  const rosterFull = squad.roster_count >= squad.roster_cap
  const atRisk = intake?.next?.arrivals_at_risk ?? 0

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

  /** Discard is the one action on this screen with no undo at all: the rider
   *  is deleted, not released. `window.confirm` rather than a bespoke modal
   *  because it is a single yes/no with nothing to render, and the copy has to
   *  name the rider — "are you sure" about an unnamed row is how the wrong
   *  prospect gets deleted. */
  const confirmDiscard = (rider: { id: number; name: string }) => {
    if (!window.confirm(`Discard ${rider.name}? This is permanent and cannot be undone.`)) return
    void run(
      () => discardSquadRider(rider.id),
      `Could not discard ${rider.name}.`,
    )
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading
        eyebrow="TEAM · DEVELOPMENT SQUAD"
        title="Development squad"
        titleSize={29}
        subtitle={
          // #33 is built: the open subtitle now states the cadence and
          // that a higher level improves the odds — but stays qualitative,
          // never a percentage and never a promise about a single batch
          // (riders/README.md, *Youth intake*). Closed keeps its money-only
          // wording, since a closed squad produces nothing.
          isOpen && intake
            ? `Running at ${currentName}. ${intake.batch_size} young riders arrive every ${intake.every_weeks} weeks; a higher level improves the odds of a promising one.`
            : 'Closed. A squad starts at Regional, and each level above costs more to reach and to run.'
        }
      />

      {actionError ? (
        <Card style={{ padding: '12px 16px', borderColor: '#D9534F' }}>
          <div style={{ fontSize: 13, color: '#D9534F' }}>{actionError}</div>
        </Card>
      ) : null}

      {isOpen && intake ? (
        <Card style={{ padding: '12px 16px' }}>
          <div style={{ fontSize: 13, color: color.ink }}>
            {intake.next
              ? `Next intake: Season ${intake.next.season}, Week ${intake.next.week}`
              : 'No intake scheduled'}
          </div>
          {/* The warning has to arrive *before* the week does: a projection
              saying what the batch would cost if nothing changes, so the
              player can promote or discard in advance rather than discover
              the arrivals were turned away (#34). Shown only when there is
              something at risk — a warning that is always there is not one. */}
          {atRisk > 0 && intake.next ? (
            <div style={{ fontSize: 12.5, color: color.negative, marginTop: 6 }}>
              Squad full — {atRisk} arrival{atRisk === 1 ? '' : 's'} in Season{' '}
              {intake.next.season}, Week {intake.next.week} will be turned away unless you make
              room.
            </div>
          ) : null}
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
                {/* Capacity beside cost: a level that costs more to run is
                    only worth it if it holds more riders (#34). */}
                <Figure label="Places" value={`${level.places} prospects`} />
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
        <Card style={{ padding: '15px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <CardHeader
            title="Squad riders"
            action={
              // The held level's places against how many are used — the two
              // numbers that make "make room" mean something concrete.
              <span style={{ fontSize: 12, fontFamily: font.mono, color: color.mutedStrong }}>
                {squad.in_squad} / {squad.places}
              </span>
            }
          />
          {squad.riders.length === 0 ? (
            <div style={{ fontSize: 12.5, color: color.muted }}>
              No riders yet — the first intake arrives
              {intake?.next
                ? ` Season ${intake.next.season}, Week ${intake.next.week}.`
                : ' once one is scheduled.'}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {squad.riders.map((rider: DevelopmentSquadRider) => (
                <div
                  key={rider.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    paddingBottom: 10,
                    borderBottom: `1px solid ${color.divider}`,
                  }}
                >
                  <div style={{ flex: '0 0 160px', minWidth: 0 }}>
                    <Link
                      to={riderPath(rider.id)}
                      style={{
                        fontSize: 13.5,
                        fontWeight: 600,
                        letterSpacing: '-0.2px',
                        color: color.ink,
                        textDecoration: 'none',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        display: 'block',
                      }}
                    >
                      {rider.name}
                    </Link>
                    <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
                      {rider.speciality.toUpperCase()} · {rider.age} yrs
                    </div>
                  </div>
                  <div style={{ flex: '1 1 auto', display: 'flex', gap: 10, minWidth: 0 }}>
                    {ATTR_KEYS.map(({ key, label }) => (
                      <div key={key} style={{ flex: 1, minWidth: 0 }}>
                        <LabelBar label={label} value={rider[key]} />
                        <ChangeReadout change={rider.change ? rider.change[key] : null} />
                      </div>
                    ))}
                  </div>
                  <div
                    style={{
                      flex: '0 0 auto',
                      fontSize: 11,
                      color: color.mutedStrong,
                      fontFamily: font.mono,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    Arrived S{rider.arrived.season} W{rider.arrived.week}
                    {rider.is_new ? (
                      // Same treatment as the CURRENT badge above — a span,
                      // not the Chip primitive, since there's nothing to
                      // toggle here either.
                      <span
                        style={{
                          padding: '4px 8px',
                          borderRadius: 8,
                          fontSize: 10,
                          fontFamily: font.mono,
                          letterSpacing: '0.6px',
                          border: `1px solid ${color.borderButton}`,
                          color: color.mutedStrong,
                        }}
                      >
                        NEW
                      </span>
                    ) : null}
                  </div>
                  <div
                    style={{
                      flex: '0 0 auto',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'flex-end',
                      gap: 5,
                    }}
                  >
                    <span style={{ fontSize: 11, color: color.muted }}>
                      Graduates in {rider.weeks_left} week{rider.weeks_left === 1 ? '' : 's'}
                    </span>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <Button
                        variant="secondary"
                        onClick={() =>
                          run(
                            () => promoteSquadRider(rider.id),
                            `Could not promote ${rider.name}.`,
                          )
                        }
                        disabled={rosterFull || pending}
                        style={{ opacity: rosterFull || pending ? 0.6 : 1, padding: '6px 12px' }}
                      >
                        Promote
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => confirmDiscard(rider)}
                        disabled={pending}
                        style={{ opacity: pending ? 0.6 : 1, padding: '6px 12px' }}
                      >
                        Discard
                      </Button>
                    </div>
                    {rosterFull ? (
                      <span style={{ fontSize: 11, color: color.negative }}>
                        Your roster is full
                      </span>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      ) : null}

      {/* Graduates are a different decision from prospects, so they get their
          own card rather than a second section in the one above: their spell
          is over, they no longer hold a place, and the questions are what to
          pay them, what the market would give, or whether to keep them at
          all (#34). Hidden entirely when there are none. */}
      {isOpen && squad.graduates.length > 0 ? (
        <Card style={{ padding: '15px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <CardHeader
            title="Graduates"
            action={
              <span style={{ fontSize: 12, fontFamily: font.mono, color: color.mutedStrong }}>
                {squad.graduates.length}
              </span>
            }
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {squad.graduates.map((rider: DevelopmentSquadGraduate) => (
              <div
                key={rider.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  paddingBottom: 10,
                  borderBottom: `1px solid ${color.divider}`,
                }}
              >
                <div style={{ flex: '0 0 160px', minWidth: 0 }}>
                  <Link
                    to={riderPath(rider.id)}
                    style={{
                      fontSize: 13.5,
                      fontWeight: 600,
                      letterSpacing: '-0.2px',
                      color: color.ink,
                      textDecoration: 'none',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      display: 'block',
                    }}
                  >
                    {rider.name}
                  </Link>
                  <div style={{ fontSize: 11, color: color.mutedStrong, fontFamily: font.mono }}>
                    {rider.speciality.toUpperCase()} · {rider.age} yrs
                  </div>
                </div>
                <div style={{ flex: '1 1 auto', display: 'flex', gap: 10, minWidth: 0 }}>
                  {ATTR_KEYS.map(({ key, label }) => (
                    <div key={key} style={{ flex: 1, minWidth: 0 }}>
                      <LabelBar label={label} value={rider[key]} />
                      <ChangeReadout change={rider.change ? rider.change[key] : null} />
                    </div>
                  ))}
                </div>
                <div
                  style={{
                    flex: '0 0 auto',
                    fontSize: 11,
                    color: color.mutedStrong,
                    fontFamily: font.mono,
                    textAlign: 'right',
                  }}
                >
                  <div>Decide within {rider.weeks_left} week{rider.weeks_left === 1 ? '' : 's'}</div>
                  <div style={{ marginTop: 3 }}>
                    Salary {formatMoney(rider.promotion_salary)} · Value{' '}
                    {formatMoney(rider.market_value)}
                  </div>
                </div>
                <div style={{ flex: '0 0 auto', display: 'flex', alignItems: 'center', gap: 6 }}>
                  {/* A listed graduate's sale is the auction's to resolve, so
                      List and Discard are replaced by a note rather than
                      offered: the server refuses both while a listing is
                      open, and a control that cannot do what it says is worse
                      than none. Promote stays — keeping the rider over the
                      bids is exactly the decision a manager is here to make,
                      and the server ends the sale when they take it. */}
                  {rider.listed ? (
                    <span style={{ fontSize: 11.5, color: color.muted }}>
                      Listed on the transfer market
                    </span>
                  ) : (
                    <>
                      <Button
                        variant="secondary"
                        onClick={() =>
                          run(
                            () => listForAuction(rider.id),
                            `Could not list ${rider.name} for sale.`,
                          )
                        }
                        disabled={pending}
                        style={{ opacity: pending ? 0.6 : 1, padding: '6px 12px' }}
                      >
                        List for sale
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => confirmDiscard(rider)}
                        disabled={pending}
                        style={{ opacity: pending ? 0.6 : 1, padding: '6px 12px' }}
                      >
                        Discard
                      </Button>
                    </>
                  )}
                  <Button
                    variant="secondary"
                    onClick={() =>
                      run(
                        () => promoteSquadRider(rider.id),
                        `Could not promote ${rider.name}.`,
                      )
                    }
                    disabled={rosterFull || pending}
                    style={{ opacity: rosterFull || pending ? 0.6 : 1, padding: '6px 12px' }}
                  >
                    Promote
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

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

/** The movement on one attribute since the rider arrived, signed and on the
 *  same 0-10 scale as the bar above it (#34).
 *
 *  Three states, all deliberate: `null` (no baseline to compare against)
 *  prints nothing at all rather than a zero, a real `0` prints muted so the
 *  row reads as "not moved" instead of shouting at every unmoved attribute,
 *  and a gain prints in the positive colour. A negative is printed too — an
 *  attribute can fall, and hiding that would be the dishonest option — in the
 *  muted tone rather than the alarming one, since a youth rider losing a
 *  point of flat over a fortnight is not news. */
function ChangeReadout({ change }: { change: number | null | undefined }) {
  if (change === null || change === undefined) return null
  const moved = change !== 0
  return (
    <div
      style={{
        fontSize: 10.5,
        fontFamily: font.mono,
        marginTop: 3,
        color: moved ? (change > 0 ? color.positive : color.mutedStrong) : color.muted,
      }}
    >
      {change > 0 ? `+${change}` : change}
    </div>
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
