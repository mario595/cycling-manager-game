import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  DevelopmentSquad as SquadPayload,
  DevelopmentSquadGraduate,
  DevelopmentSquadRider,
  Me,
} from '../api'
import { discardSquadRider, listForAuction } from '../api'
import { useAuth } from '../useAuth'
import { useDepartures } from '../useDepartures'
import { useDevelopmentSquad } from '../useDevelopmentSquad'
import { useSeason } from '../useSeason'
import { DevelopmentSquad } from './DevelopmentSquad'

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  discardSquadRider: vi.fn(),
  listForAuction: vi.fn(),
}))
vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useDevelopmentSquad', () => ({ useDevelopmentSquad: vi.fn() }))
vi.mock('../useDepartures', () => ({ useDepartures: vi.fn() }))
vi.mock('../useSeason', () => ({ useSeason: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseDevelopmentSquad = vi.mocked(useDevelopmentSquad)
const mockUseDepartures = vi.mocked(useDepartures)
const mockUseSeason = vi.mocked(useSeason)

const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Youth Team', code: 'YTH' },
  lost_team: null,
}

const NAMES = { 1: 'Regional', 2: 'National', 3: 'Elite' }
const FEES = { 1: 30_000, 2: 75_000, 3: 150_000 }
const WEEKLY_COSTS = { 1: 1_500, 2: 3_500, 3: 6_000 }
const PLACES = { 1: 6, 2: 8, 3: 10 }

function developmentSquadRider(overrides: Partial<DevelopmentSquadRider> = {}): DevelopmentSquadRider {
  return {
    id: 1,
    name: 'Youth Rider',
    speciality: 'climber',
    nationality: 'ES',
    age: 18,
    climb: 3,
    sprint: 2,
    flat: 2,
    resistance: 3,
    positioning: 2,
    arrived: { season: 1, week: 4 },
    is_new: false,
    // #34: the whole spell ahead, and movement only on one attribute, so a
    // test that cares about a sign has something to assert against.
    weeks_left: 14,
    change: { climb: 2, sprint: 0, flat: 0, resistance: 1, positioning: 0 },
    promotion_salary: 4_000,
    ...overrides,
  }
}

/** A graduate is a rider whose spell is done: the same identity and
 * attributes, but counting down the decision window rather than a spell, and
 * carrying the two figures that only make sense for a sale or a signing. */
function developmentSquadGraduate(
  overrides: Partial<DevelopmentSquadGraduate> = {},
): DevelopmentSquadGraduate {
  return {
    ...developmentSquadRider({ id: 2, name: 'Graduated Rider', weeks_left: 2 }),
    market_value: 52_000,
    listed: false,
    decision_due: null,
    ...overrides,
  }
}

/** Builds a payload the way the server sends it: a level's price is its own
 * fee whatever state the team is in, `action`/`requires` come from the
 * ladder rule rather than being worked out here, and `riders`/`intake` are
 * only meaningful while open — the default is a closed squad with neither. */
function payload(
  current: number | null,
  balance = 500_000,
  overrides: Partial<Pick<SquadPayload, 'riders' | 'graduates' | 'intake'>> = {},
): SquadPayload {
  return {
    level: current,
    balance,
    levels: ([1, 2, 3] as const).map((level) => {
      const lockedNote =
        current === null
          ? 'Open Regional first.'
          : level < current
            ? 'Climbed past. Close the squad to start over.'
            : `Upgrade to ${NAMES[level - 1]} first.`
      const action =
        current === null
          ? level === 1
            ? 'open'
            : 'locked'
          : level === current
            ? 'current'
            : level === current + 1
              ? 'upgrade'
              : 'locked'
      return {
        level,
        name: NAMES[level],
        weekly_cost: WEEKLY_COSTS[level],
        season_cost: WEEKLY_COSTS[level] * 12,
        fee: FEES[level],
        // Capacity rises with the rung: 6 / 8 / 10 (riders/README.md,
        // *Development squad*).
        places: PLACES[level],
        action,
        requires: action === 'locked' ? lockedNote : null,
      }
    }),
    places: current === null ? null : PLACES[current],
    in_squad: overrides.riders?.length ?? 0,
    roster_count: 4,
    roster_cap: 30,
    riders: [],
    graduates: [],
    intake:
      current === null
        ? null
        : { every_weeks: 4, batch_size: 2, next: { season: 1, week: 8, arrivals_at_risk: 0 } },
    ...overrides,
  }
}

const closed = payload(null)
const openAtNational = payload(2)

function renderScreen() {
  return render(
    <MemoryRouter>
      <DevelopmentSquad />
    </MemoryRouter>,
  )
}

function mockSquad(squad: SquadPayload) {
  mockUseDevelopmentSquad.mockReturnValue({
    squad,
    loading: false,
    error: false,
    refresh: vi.fn(),
  })
}

beforeEach(() => {
  mockUseDepartures.mockReturnValue({ departures: [], loading: false, error: false })
  mockUseSeason.mockReturnValue({
    position: { state: 'in_season', season: 4, week: 5, week_ends_at: null, weeks_in_season: 12 },
    loading: false,
    error: false,
  })
  vi.mocked(discardSquadRider).mockReset()
  vi.mocked(listForAuction).mockReset()
  mockUseAuth.mockReturnValue({
    me: manager,
    loading: false,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    claim: vi.fn(),
    acknowledgeLostTeam: vi.fn(),
  })
  mockSquad(closed)
})

describe('DevelopmentSquad', () => {
  it('renders all three levels with fee, weekly and per-season cost', () => {
    renderScreen()

    for (const name of ['Regional', 'National', 'Elite']) {
      expect(screen.getByText(name)).toBeInTheDocument()
    }
    for (const fee of ['$30,000', '$75,000', '$150,000']) {
      expect(screen.getByText(fee)).toBeInTheDocument()
    }
    expect(screen.getByText('$1,500/week')).toBeInTheDocument()
    // Twelve weeks at the Regional weekly cost.
    expect(screen.getByText('$18,000')).toBeInTheDocument()
  })

  it('offers Open only on the entry level, and no Close button, while closed', () => {
    renderScreen()

    // The two levels above are reached by upgrading, so there is no button to
    // open them at.
    expect(screen.getAllByRole('button', { name: 'Open' })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Upgrade' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Close squad' })).not.toBeInTheDocument()
  })

  // #33 shipped: the screen now names the cadence and says a higher level
  // improves the odds. What it must still never do is put a number on that
  // claim or promise an outcome for the next batch specifically — the rule
  // this test pins now that "promises no riders" is obsolete by design.
  it('describes intake without promising an outcome', () => {
    mockSquad(openAtNational)

    renderScreen()

    expect(
      screen.getByText(
        'Running at National. 2 young riders arrive every 4 weeks; a higher level improves the odds of a promising one.',
      ),
    ).toBeInTheDocument()
    const copy = document.body.textContent ?? ''
    expect(copy).not.toMatch(/guarantee/i)
    expect(copy).not.toMatch(/\d+\s*%/)

    mockSquad(closed)
    renderScreen()
    expect(document.body.textContent ?? '').not.toMatch(/soon/i)
  })

  it('lists squad riders with arrival and a NEW badge on the latest batch', () => {
    mockSquad(
      payload(2, 500_000, {
        riders: [
          developmentSquadRider({ id: 1, name: 'Old Batch', arrived: { season: 1, week: 4 }, is_new: false }),
          developmentSquadRider({ id: 2, name: 'New Batch', arrived: { season: 1, week: 8 }, is_new: true }),
        ],
      }),
    )

    renderScreen()

    expect(screen.getByText('Old Batch')).toBeInTheDocument()
    expect(screen.getByText('New Batch')).toBeInTheDocument()
    expect(screen.getByText('Arrived S1 W4')).toBeInTheDocument()
    expect(screen.getByText('Arrived S1 W8')).toBeInTheDocument()
    expect(screen.getByText('NEW')).toBeInTheDocument()
  })

  it('shows the next intake week, and the empty state when no riders have arrived', () => {
    mockSquad(
      payload(1, 500_000, {
        riders: [],
        intake: { every_weeks: 4, batch_size: 2, next: { season: 1, week: 4, arrivals_at_risk: 0 } },
      }),
    )

    renderScreen()

    expect(screen.getByText('Next intake: Season 1, Week 4')).toBeInTheDocument()
    expect(screen.getByText(/No riders yet/)).toBeInTheDocument()
  })

  it('shows no riders or intake card while closed', () => {
    renderScreen()

    expect(screen.queryByText(/Next intake/)).not.toBeInTheDocument()
    expect(screen.queryByText('Squad riders')).not.toBeInTheDocument()
  })

  it('labels the fee by the rung it buys, not by what the team can do', () => {
    mockSquad(openAtNational)

    renderScreen()

    // Level 1 is the one that opens a squad; every level above is bought by
    // upgrading into it, and each pays its own fee in full.
    expect(screen.getByText('Open fee')).toBeInTheDocument()
    expect(screen.getAllByText('Upgrade fee')).toHaveLength(2)
  })

  it('offers exactly one upgrade and no downgrade when open at National', () => {
    mockSquad(openAtNational)

    renderScreen()

    expect(screen.getByRole('button', { name: 'Upgrade' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Downgrade' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open' })).not.toBeInTheDocument()
    expect(screen.getByText('CURRENT')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close squad' })).toBeInTheDocument()
  })

  it('shows a locked card the server’s reason, with a padlock', () => {
    // At Regional, Elite is the level not yet reached, so the note says which
    // rung unlocks it. The words come from the server — only it knows whether a
    // lock is "not yet" or "climbed past".
    mockSquad(payload(1))

    renderScreen()

    expect(screen.getByText('Upgrade to National first.')).toBeInTheDocument()
    // The padlock is an aria-hidden SVG: the note beside it is the accessible
    // part, so the shape is decoration on top of real text.
    expect(document.querySelectorAll('svg').length).toBeGreaterThanOrEqual(1)
  })

  it('tells a team that has climbed past a level that closing is the only way back', () => {
    mockSquad(openAtNational)

    renderScreen()

    // Regional is locked, but not because something above it is missing. It is
    // behind the team, and there is no rung pointing down — so the advice is
    // the drastic one, and it is the only path back.
    expect(
      screen.getByText('Climbed past. Close the squad to start over.'),
    ).toBeInTheDocument()
  })

  it('tells a closed team which level to open first', () => {
    renderScreen()

    // Both locked cards say the same thing while there is no squad at all: the
    // way in is the bottom rung, and there is no other door.
    expect(screen.getAllByText('Open Regional first.')).toHaveLength(2)
  })

  it('has no button at all on a locked or current card', () => {
    mockSquad(openAtNational)

    renderScreen()

    // One action per card at most, and the other two cards are not offering
    // anything: a lock is not a disabled button, it is no button.
    const buttons = screen
      .getAllByRole('button')
      .filter((b) => ['Open', 'Upgrade', 'Downgrade'].includes(b.textContent ?? ''))
    expect(buttons).toHaveLength(1)
  })

  it('disables an action costing more than the balance, with a reason', () => {
    mockSquad({ ...closed, balance: 40_000 })

    renderScreen()

    // Regional (30,000) is affordable. The two above are locked, so they have
    // no button to disable and nothing to warn about.
    expect(screen.getByRole('button', { name: 'Open' })).toBeEnabled()
    expect(screen.queryByText(/cannot afford/i)).not.toBeInTheDocument()
  })

  it('warns about an unaffordable upgrade without disabling the locked cards', () => {
    mockSquad({ ...openAtNational, balance: 100_000 })

    renderScreen()

    // Elite's fee is 150,000 against 100,000 in the bank; Regional's lock is
    // not a cost and must not be reported as one.
    expect(screen.getByRole('button', { name: 'Upgrade' })).toBeDisabled()
    expect(screen.getAllByText(/cannot afford/i)).toHaveLength(1)
  })

  it('says closing is a one-way door, since it is the only way to spend less', () => {
    mockSquad(openAtNational)

    renderScreen()

    // With no downgrade to fall back on, the cost of closing is the thing a
    // manager has to weigh: nothing back, and the whole climb again.
    expect(screen.getByText(/reopening starts at\s+Regional again/i)).toBeInTheDocument()
  })

  // --- #34: the triage half of the screen -------------------------------------------------

  it('shows each level\'s places, and how much of them is used', () => {
    mockSquad(
      payload(2, 500_000, {
        riders: [developmentSquadRider({ id: 1 }), developmentSquadRider({ id: 2 })],
      }),
    )

    renderScreen()

    // Capacity sits with the cost on the same card: a rung that costs more is
    // only worth it if it holds more.
    expect(screen.getAllByText('Places')).toHaveLength(3)
    expect(screen.getByText('6 prospects')).toBeInTheDocument()
    expect(screen.getByText('8 prospects')).toBeInTheDocument()
    expect(screen.getByText('10 prospects')).toBeInTheDocument()
    // And the card header says how much of the held level is in use.
    expect(screen.getByText('2 / 8')).toBeInTheDocument()
  })

  it('warns about arrivals at risk, and stays quiet when there is room', () => {
    mockSquad(
      payload(1, 500_000, {
        riders: [developmentSquadRider({ id: 1 })],
        intake: {
          every_weeks: 4,
          batch_size: 2,
          next: { season: 1, week: 8, arrivals_at_risk: 1 },
        },
      }),
    )

    const first = renderScreen()

    // The warning has to land before the week does, so the player can free a
    // place in advance rather than finding out the arrival was turned away.
    expect(
      screen.getByText(
        'Squad full — 1 arrival in Season 1, Week 8 will be turned away unless you make room.',
      ),
    ).toBeInTheDocument()

    // Unmounted between the two states: testing-library cleans up between
    // tests, not between renders, so the first tree's warning would otherwise
    // still be on the page for the "stays quiet" half to find.
    first.unmount()

    mockSquad(
      payload(1, 500_000, {
        riders: [developmentSquadRider({ id: 1 })],
        intake: {
          every_weeks: 4,
          batch_size: 2,
          next: { season: 1, week: 8, arrivals_at_risk: 0 },
        },
      }),
    )
    renderScreen()

    expect(screen.queryByText(/will be turned away/)).not.toBeInTheDocument()
  })

  it('pluralises the warning for a whole batch at risk', () => {
    mockSquad(
      payload(1, 500_000, {
        riders: [developmentSquadRider({ id: 1 })],
        intake: {
          every_weeks: 4,
          batch_size: 2,
          next: { season: 1, week: 8, arrivals_at_risk: 2 },
        },
      }),
    )

    renderScreen()

    expect(screen.getByText(/2 arrivals in Season 1, Week 8/)).toBeInTheDocument()
  })

  it('renders movement since arrival signed, and nothing at all without a baseline', () => {
    mockSquad(
      payload(1, 500_000, {
        riders: [
          developmentSquadRider({
            id: 1,
            change: { climb: 2, sprint: -1, flat: 0, resistance: 0, positioning: 0 },
          }),
        ],
      }),
    )

    const moved = renderScreen()

    expect(screen.getByText('+2')).toBeInTheDocument()
    // A fall is printed rather than hidden: an attribute can drop, and
    // showing only gains would be the dishonest option.
    expect(screen.getByText('-1')).toBeInTheDocument()
    // The unmoved attributes print their own muted zero rather than nothing,
    // so the row still reads as five bars with five readouts.
    expect(screen.getAllByText('0')).toHaveLength(3)

    // No baseline is not a claim that nothing moved, so it prints nothing.
    moved.unmount()
    mockSquad(
      payload(1, 500_000, {
        riders: [developmentSquadRider({ id: 1, change: null })],
      }),
    )
    renderScreen()

    expect(screen.queryByText('+2')).not.toBeInTheDocument()
  })

  it('gives every prospect a countdown and both actions', () => {
    mockSquad(
      payload(1, 500_000, {
        riders: [developmentSquadRider({ id: 1, weeks_left: 14 })],
      }),
    )

    renderScreen()

    expect(screen.getByText('Graduates in 14 weeks')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Promote' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Discard' })).toBeEnabled()
  })

  it('disables Promote at the roster cap and says why', () => {
    mockSquad({
      ...payload(1, 500_000, { riders: [developmentSquadRider({ id: 1 })] }),
      roster_count: 30,
      roster_cap: 30,
    })

    renderScreen()

    // A full roster is what stops a promotion, so the button says so rather
    // than offering an action the server would refuse with a 409. Discard is
    // unaffected — making room is the other half of this row.
    expect(screen.getByRole('button', { name: 'Promote' })).toBeDisabled()
    expect(screen.getByText(/your roster is full/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Discard' })).toBeEnabled()
  })

  it('asks before discarding, and does nothing when the answer is no', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const discard = vi.mocked(discardSquadRider)
    mockSquad(
      payload(1, 500_000, {
        riders: [developmentSquadRider({ id: 7, name: 'Old Batch' })],
      }),
    )

    renderScreen()

    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))

    // Naming the rider is the point: "are you sure" against an unnamed row is
    // how the wrong prospect gets deleted.
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('Old Batch'))
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringMatching(/permanent/i))
    expect(discard).not.toHaveBeenCalled()

    confirmSpy.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))

    expect(discard).toHaveBeenCalledWith(7)

    confirmSpy.mockRestore()
  })

  it('lists graduates with their window, salary and value', () => {
    mockSquad(
      payload(1, 500_000, {
        graduates: [developmentSquadGraduate({ id: 5, name: 'Graduate', weeks_left: 1 })],
      }),
    )

    renderScreen()

    expect(screen.getByText('Graduate')).toBeInTheDocument()
    expect(screen.getByText('Decide within 1 week')).toBeInTheDocument()
    // Both figures are money, so both carry the $ (AGENTS.md).
    expect(screen.getByText(/Salary \$4,000/)).toBeInTheDocument()
    expect(screen.getByText(/Value \$52,000/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'List for sale' })).toBeEnabled()
  })

  it('pluralises the remaining window, so a single week does not read "1 weeks"',
    () => {
      mockSquad(
        payload(1, 500_000, {
          graduates: [developmentSquadGraduate({ id: 5, name: 'Graduate', weeks_left: 2 })],
        }),
      )

      renderScreen()

      expect(screen.getByText('Decide within 2 weeks')).toBeInTheDocument()
    })

  it('names the release week and says what happens if nothing is done (#162)', () => {
    mockSquad(
      payload(1, 500_000, {
        graduates: [
          developmentSquadGraduate({
            id: 5, name: 'Graduate', weeks_left: 2, decision_due: { season: 4, week: 6 },
          }),
        ],
      }),
    )

    renderScreen()

    expect(screen.getByText('Decide before Season 4, Week 6 (2 weeks left)')).toBeInTheDocument()
    expect(
      screen.getByText("If you do nothing, they're released to the free agents."),
    ).toBeInTheDocument()
  })

  it('shows no deadline for a listed graduate: the auction decides (#162)', () => {
    mockSquad(
      payload(1, 500_000, {
        graduates: [
          developmentSquadGraduate({
            id: 5, name: 'Graduate', weeks_left: 1, listed: true,
            decision_due: { season: 4, week: 6 },
          }),
        ],
      }),
    )

    renderScreen()

    expect(screen.getByText('On auction: the auction decides')).toBeInTheDocument()
    expect(screen.queryByText(/Decide before/)).not.toBeInTheDocument()
    expect(screen.queryByText(/If you do nothing/)).not.toBeInTheDocument()
  })

  it("lists this season's graduate releases, and only those (#162)", () => {
    mockSquad(payload(1, 500_000))
    const departure = (id: number, name: string, kind: 'released' | 'retired', season: number) => ({
      id, kind, at: '2027-08-16T00:00:00Z', season, week: 6,
      rider: { id, name, speciality: 'sprinter', age: 19 }, buyer: null, fee: null,
    })
    mockUseDepartures.mockReturnValue({
      departures: [
        departure(1, 'Luis Garcia', 'released', 4),
        departure(2, 'Old Release', 'released', 3),
        departure(3, 'A Retiree', 'retired', 4),
      ],
      loading: false,
      error: false,
    })

    renderScreen()

    expect(screen.getByText('Released this season')).toBeInTheDocument()
    expect(screen.getByText('Luis Garcia')).toBeInTheDocument()
    expect(screen.getByText('was released to the free agents in Season 4, Week 6')).toBeInTheDocument()
    expect(screen.queryByText('Old Release')).not.toBeInTheDocument()
    expect(screen.queryByText('A Retiree')).not.toBeInTheDocument()
  })

  it('hides the graduates card when there are none', () => {
    mockSquad(payload(1, 500_000, { graduates: [] }))

    renderScreen()

    expect(screen.queryByText('Graduates')).not.toBeInTheDocument()
  })

  it('gives a listed graduate no List or Discard, because the auction is the buyer\'s business now', () => {
    mockSquad(
      payload(1, 500_000, {
        graduates: [developmentSquadGraduate({ id: 5, listed: true })],
      }),
    )

    renderScreen()

    expect(screen.getByText('Listed on the transfer market')).toBeInTheDocument()
    // Offering either would be a control that cannot do what it says: the
    // server refuses both while a listing is open.
    expect(screen.queryByRole('button', { name: 'List for sale' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Discard' })).not.toBeInTheDocument()
    // Promote stays, and is the manager choosing the rider over the bids —
    // the server cancels the auction when they press it.
    expect(screen.getByRole('button', { name: 'Promote' })).toBeEnabled()
  })

  it('lists a graduate for sale through the existing auction call', async () => {
    const listForAuctionMock = vi.mocked(listForAuction)
    listForAuctionMock.mockResolvedValue(undefined)
    mockSquad(
      payload(1, 500_000, { graduates: [developmentSquadGraduate({ id: 9 })] }),
    )

    renderScreen()

    fireEvent.click(screen.getByRole('button', { name: 'List for sale' }))

    // The same list-for-auction call the roster and transfers screens use —
    // a graduate is sellable by the same route as any other rider.
    expect(listForAuctionMock).toHaveBeenCalledWith(9)
  })

  it('never states an odds figure or a potential', () => {
    mockSquad(
      payload(1, 500_000, {
        riders: [developmentSquadRider({ id: 1 })],
        graduates: [developmentSquadGraduate({ id: 2 })],
      }),
    )

    renderScreen()

    const copy = document.body.textContent ?? ''
    expect(copy).not.toMatch(/\d+\s*%/)
    expect(copy).not.toMatch(/potential/i)
    expect(copy).not.toMatch(/odds of \d/i)
  })

  it('says so plainly when the manager has no team', () => {
    mockUseAuth.mockReturnValue({
      me: { ...manager, team: null },
      loading: false,
      register: vi.fn(),
      login: vi.fn(),
      logout: vi.fn(),
      claim: vi.fn(),
      acknowledgeLostTeam: vi.fn(),
    })

    renderScreen()

    expect(screen.getByText(/do not manage a team/i)).toBeInTheDocument()
  })
})
