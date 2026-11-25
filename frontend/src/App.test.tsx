import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import type { Me } from './api'
import { App, SCREENS } from './App'
import { NAV_ITEMS } from './navigation'
import { useAuth } from './useAuth'

vi.mock('./useAuth', () => ({
  AuthProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  useAuth: vi.fn(),
}))

// Every screen is a stub: this test only proves routing and the guard order,
// not what individual screens render. The screens' own tests cover them.
vi.mock('./screens/Dashboard', () => ({ Dashboard: () => <div data-testid="dashboard" /> }))
vi.mock('./screens/Roster', () => ({ Roster: () => <div data-testid="roster" /> }))
vi.mock('./screens/Training', () => ({ Training: () => <div data-testid="training" /> }))
vi.mock('./screens/Staff', () => ({ Staff: () => <div data-testid="staff" /> }))
vi.mock('./screens/Calendar', () => ({ Calendar: () => <div data-testid="calendar" /> }))
vi.mock('./screens/Transfers', () => ({ Transfers: () => <div data-testid="transfers" /> }))
vi.mock('./screens/League', () => ({ League: () => <div data-testid="league" /> }))
vi.mock('./screens/Race', () => ({ Race: () => <div data-testid="race" /> }))
vi.mock('./screens/Login', () => ({ Login: () => <div data-testid="login" /> }))
vi.mock('./screens/Register', () => ({ Register: () => <div data-testid="register" /> }))
vi.mock('./screens/ClaimTeam', () => ({ ClaimTeam: () => <div data-testid="claim" /> }))

const mockUseAuth = vi.mocked(useAuth)

const anonymous: Me = { authenticated: false, display_name: null, team: null, lost_team: null }
const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD', sponsor_missing: false, guaranteed_weekly: null },
  lost_team: null,
}

function mockAuth(me: Me | null, loading: boolean) {
  mockUseAuth.mockReturnValue({
    me,
    loading,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    claim: vi.fn(),
    acknowledgeLostTeam: vi.fn(),
    refresh: vi.fn(),
  })
}

function renderAppAt(path: string) {
  window.history.pushState({}, '', path)
  return render(<App />)
}

beforeEach(() => {
  window.history.pushState({}, '', '/')
})

describe('App routing', () => {
  it('an unknown path sends a logged-in manager to the dashboard', () => {
    mockAuth(manager, false)

    renderAppAt('/typo')

    expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    expect(screen.queryByTestId('login')).toBeNull()
  })

  it('an unknown path sends an anonymous visitor to /login', () => {
    mockAuth(anonymous, false)

    renderAppAt('/typo')

    expect(screen.getByTestId('login')).toBeInTheDocument()
    expect(screen.queryByTestId('dashboard')).toBeNull()
  })

  it('routes a logged-in manager to the Transfers screen', () => {
    mockAuth(manager, false)

    renderAppAt('/transfers')

    expect(screen.getByTestId('transfers')).toBeInTheDocument()
  })

  it('routes a logged-in manager to the Training screen (#155)', () => {
    mockAuth(manager, false)

    renderAppAt('/training')

    expect(screen.getByTestId('training')).toBeInTheDocument()
    expect(screen.queryByTestId('dashboard')).toBeNull()
  })

  // A screen in SCREENS with no nav item registers no route at all, and a nav
  // item with no screen renders undefined. Either way a built screen silently
  // drops off the router, which is how Training went missing (#155).
  it('every built screen has a nav item, and every nav item a screen', () => {
    expect(Object.keys(SCREENS).sort()).toEqual(NAV_ITEMS.map((item) => item.path).sort())
  })
})
