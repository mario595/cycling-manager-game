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

const OPENING_FEES = { 1: 30_000, 2: 75_000, 3: 150_000 }
const WEEKLY_COSTS = { 1: 1_500, 2: 3_500, 3: 6_000 }

/** Closed: every level is an opening, priced at its full fee. */
const closed: SquadPayload = {
  level: null,
  balance: 500_000,
  levels: [1, 2, 3].map((level) => ({
    level,
    name: { 1: 'Regional', 2: 'National', 3: 'Elite' }[level]!,
    opening_fee: OPENING_FEES[level as 1],
    weekly_cost: WEEKLY_COSTS[level as 1],
    season_cost: WEEKLY_COSTS[level as 1] * 12,
    change_fee: OPENING_FEES[level as 1],
    is_current: false,
  })),
}

/** Open at National: the current level has a null fee, the upgrade is priced
 * at the difference and the downgrade at zero — the server's figures, not the
 * client's arithmetic. */
const openAtNational: SquadPayload = {
  level: 2,
  balance: 500_000,
  levels: closed.levels.map((level) => {
    if (level.level === 2) return { ...level, change_fee: null, is_current: true }
    if (level.level === 3) {
      return { ...level, change_fee: OPENING_FEES[3] - OPENING_FEES[2], is_current: false }
    }
    return { ...level, change_fee: 0, is_current: false }
  }),
}

function renderScreen() {
  return render(
    <MemoryRouter>
      <DevelopmentSquad />
    </MemoryRouter>,
  )
}

/** The per-card footer that names what a move there costs. Queried by its
 * label rather than by the amount, because a figure can legitimately appear
 * on two cards — Elite's upgrade fee happens to equal National's opening fee. */
function moveCostRow(label: string): HTMLElement {
  const row = screen.getByText(label).parentElement
  if (!row) throw new Error(`no row for ${label}`)
  return row
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

  it('offers Open on every card and no Close button while closed', () => {
    renderScreen()

    expect(screen.getAllByRole('button', { name: 'Open' })).toHaveLength(3)
    expect(screen.queryByRole('button', { name: 'Close squad' })).not.toBeInTheDocument()
  })

  it('prices each Open on the card itself, with no second copy of the fee', () => {
    renderScreen()

    // While closed, every move is an opening, so the "Opening fee" row is the
    // price. A separate per-move figure would print the same number twice.
    expect(screen.queryByText('To move here')).not.toBeInTheDocument()
  })

  it('wordens the actions by state when open at National', () => {
    mockSquad(openAtNational)

    renderScreen()

    expect(screen.getByRole('button', { name: 'Upgrade' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Downgrade' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open' })).not.toBeInTheDocument()
    expect(screen.getByText('CURRENT')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close squad' })).toBeInTheDocument()
  })

  it('prices the upgrade at the difference and the downgrade as free', () => {
    mockSquad(openAtNational)

    renderScreen()

    // Straight from the payload: 150,000 - 75,000, not recomputed here.
    expect(moveCostRow('To move here')).toHaveTextContent('$75,000')
    expect(moveCostRow('Downgrading is free')).toHaveTextContent('Free')
  })

  it('gives the current level no button at all', () => {
    mockSquad(openAtNational)

    renderScreen()

    // One action per card, and the current card's is a badge rather than a
    // button — a no-op move is not something to offer.
    const buttons = screen
      .getAllByRole('button')
      .filter((b) => ['Open', 'Upgrade', 'Downgrade'].includes(b.textContent ?? ''))
    expect(buttons).toHaveLength(2)
  })

  it('disables an action costing more than the balance, with a reason', () => {
    mockSquad({ ...closed, balance: 40_000 })

    renderScreen()

    // Regional (30,000) is affordable; National and Elite are not.
    const openButtons = screen.getAllByRole('button', { name: 'Open' })
    expect(openButtons[0]).toBeEnabled()
    expect(openButtons[1]).toBeDisabled()
    expect(openButtons[2]).toBeDisabled()
    expect(screen.getAllByText(/cannot afford/i)).toHaveLength(2)
  })

  it('never disables a free downgrade, however low the balance', () => {
    mockSquad({ ...openAtNational, balance: 0 })

    renderScreen()

    expect(screen.getByRole('button', { name: 'Downgrade' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Upgrade' })).toBeDisabled()
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
