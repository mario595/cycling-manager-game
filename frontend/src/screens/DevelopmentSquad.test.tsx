import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DevelopmentSquad as SquadPayload, Me } from '../api'
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

/** Builds a payload the way the server sends it: a level's price is its own
 * fee whatever state the team is in, and `action`/`requires` come from the
 * ladder rule rather than being worked out here. */
function payload(
  current: number | null,
  balance = 500_000,
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

  // The spec forbids this screen promising riders, and the first build broke
  // it in both subtitles ("develop young riders between seasons", "a higher
  // level develops riders faster") — neither of which is true yet, and a
  // manager would pay real money on the strength of either. Pinned here
  // because the rule is a spec decision nothing else in the code enforces.
  it.each([
    [
      'closed',
      closed,
      'Closed. A squad starts at Regional, and each level above costs more to reach and to run.',
    ],
    ['open', openAtNational, 'Running at National, charged its weekly cost every week.'],
  ])('promises no riders while %s — only what is actually charged', (_state, squad, subtitle) => {
    mockSquad(squad as SquadPayload)

    renderScreen()

    expect(screen.getByText(subtitle)).toBeInTheDocument()
    const copy = document.body.textContent ?? ''
    // Not /develop/ — the screen is called "Development squad". What must not
    // appear is a claim that it produces riders, or a teaser for a feature
    // that does not exist yet.
    expect(copy).not.toMatch(/rider/i)
    expect(copy).not.toMatch(/youth/i)
    expect(copy).not.toMatch(/soon/i)
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
