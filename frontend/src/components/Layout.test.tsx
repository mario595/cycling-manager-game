import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Me } from '../api'
import { useAuth } from '../useAuth'
import { useClock } from '../useClock'
import { useSeason } from '../useSeason'
import { Layout } from './Layout'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../useSeason', () => ({ useSeason: vi.fn() }))
vi.mock('../useClock', () => ({ useClock: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)
const mockUseSeason = vi.mocked(useSeason)
const mockUseClock = vi.mocked(useClock)

const anonymous: Me = { authenticated: false, display_name: null, team: null, lost_team: null }
const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD', sponsor_missing: false, guaranteed_weekly: null },
  lost_team: null,
}

/** Renders what the router would render, with Layout as the pathless shell
 * and stubs for the screens the guards redirect to, so navigation lands on
 * a visible marker rather than a match that renders nothing. */
function renderLayout(path: string) {
  function LoginProbe() {
    const location = useLocation()
    return <div data-testid="login-state">{JSON.stringify(location.state ?? null)}</div>
  }
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="*" element={<div data-testid="page">PAGE</div>} />
          <Route path="/login" element={<LoginProbe />} />
          <Route path="/register" element={<div data-testid="register">REGISTER</div>} />
          <Route path="/claim" element={<div data-testid="claim">CLAIM</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
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

beforeEach(() => {
  mockUseClock.mockReturnValue({ now: null, loading: true, error: false })
  mockUseSeason.mockReturnValue({ position: null, loading: true, error: false })
})

describe('Layout', () => {
  it('renders nothing while auth is loading', () => {
    mockAuth(null, true)

    renderLayout('/league')

    expect(screen.queryByTestId('page')).toBeNull()
    expect(screen.queryByTestId('login-state')).toBeNull()
  })

  it('redirects an anonymous visitor to /login', () => {
    mockAuth(anonymous, false)

    renderLayout('/league')

    expect(screen.getByTestId('login-state')).toBeInTheDocument()
    expect(screen.queryByTestId('page')).toBeNull()
  })

  it('does not redirect an anonymous visitor already on /login', () => {
    mockAuth(anonymous, false)

    renderLayout('/login')

    expect(screen.getByTestId('login-state')).toBeInTheDocument()
  })

  it('allows /register anonymously', () => {
    mockAuth(anonymous, false)

    renderLayout('/register')

    expect(screen.getByTestId('register')).toBeInTheDocument()
  })

  it('marks the Sponsors entry while the team has no sponsor this season', () => {
    mockAuth({ ...manager, team: { ...manager.team!, sponsor_missing: true, guaranteed_weekly: 9_640 } }, false)

    renderLayout('/roster')

    expect(screen.getAllByLabelText('No sponsor this season').length).toBeGreaterThan(0)
  })

  it('does not mark the Sponsors entry once a sponsor is signed', () => {
    mockAuth(manager, false)

    renderLayout('/roster')

    expect(screen.queryByLabelText('No sponsor this season')).toBeNull()
  })

  it('redirects a team-less manager to /claim', () => {
    mockAuth({ ...manager, team: null }, false)

    renderLayout('/roster')

    expect(screen.getByTestId('claim')).toBeInTheDocument()
    expect(screen.queryByTestId('page')).toBeNull()
  })

  it('does not bounce a logged-in manager mid-load', () => {
    mockAuth(null, true)

    renderLayout('/roster')

    expect(screen.queryByTestId('login-state')).toBeNull()
    expect(screen.queryByTestId('page')).toBeNull()
  })

  it('passes the attempted path in location state', () => {
    mockAuth(anonymous, false)

    renderLayout('/league')

    expect(screen.getByTestId('login-state')).toHaveTextContent('{"from":"/league"}')
  })

  it('shows the report button to a manager', () => {
    mockAuth(manager, false)

    renderLayout('/roster')

    expect(screen.getByRole('button', { name: 'Report a problem' })).toBeInTheDocument()
  })

  it('shows the report button to a team-less user on /claim', () => {
    mockAuth({ ...manager, team: null }, false)

    renderLayout('/claim')

    expect(screen.getByTestId('claim')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Report a problem' })).toBeInTheDocument()
  })

  it('does not show the report button on the login page', () => {
    mockAuth(anonymous, false)

    renderLayout('/login')

    expect(screen.queryByRole('button', { name: 'Report a problem' })).toBeNull()
  })
})
