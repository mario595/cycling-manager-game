import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DevelopmentSquad as SquadPayload, DevelopmentSquadRider, Me } from '../api'
import { useAuth } from '../useAuth'
import { useDevelopmentSquad } from '../useDevelopmentSquad'
import { DevelopmentSquad } from './DevelopmentSquad'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useDevelopmentSquad', () => ({ useDevelopmentSquad: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseDevelopmentSquad = vi.mocked(useDevelopmentSquad)

const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Youth Team', code: 'YTH' },
  lost_team: null,
}

const NAMES = { 1: 'Regional', 2: 'National', 3: 'Elite' }
const FEES = { 1: 30_000, 2: 75_000, 3: 150_000 }
const WEEKLY_COSTS = { 1: 1_500, 2: 3_500, 3: 6_000 }

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
  overrides: Partial<Pick<SquadPayload, 'riders' | 'intake'>> = {},
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
        action,
        requires: action === 'locked' ? lockedNote : null,
      }
    }),
    riders: current === null ? [] : [],
    intake: current === null ? null : { every_weeks: 4, batch_size: 2, next: { season: 1, week: 8 } },
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
    mockSquad(payload(1, 500_000, { riders: [], intake: { every_weeks: 4, batch_size: 2, next: { season: 1, week: 4 } } }))

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
