import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import type { Me } from '../api'
import { useAuth } from '../useAuth'
import { Login } from './Login'

vi.mock('../useAuth', () => ({ useAuth: vi.fn() }))

const mockUseAuth = vi.mocked(useAuth)

function mockAuth(me: Me | null, loading: boolean) {
  mockUseAuth.mockReturnValue({
    me,
    loading,
    register: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    claim: vi.fn(),
  })
}

const manager: Me = {
  authenticated: true,
  display_name: 'Mario',
  team: { id: 1, name: 'Squad Team', code: 'SQD' },
}

function renderLogin(state?: { from?: string }) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/login', state }]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/league" element={<div data-testid="league">LEAGUE</div>} />
        <Route path="/" element={<div data-testid="home">HOME</div>} />
        <Route path="/claim" element={<div data-testid="claim">CLAIM</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Login redirect after authentication', () => {
  it('sends an authenticated manager to the page they attempted', () => {
    mockAuth(manager, false)

    renderLogin({ from: '/league' })

    expect(screen.getByTestId('league')).toBeInTheDocument()
    expect(screen.queryByTestId('home')).toBeNull()
  })

  it('sends them to / when there is no attempted page', () => {
    mockAuth(manager, false)

    renderLogin()

    expect(screen.getByTestId('home')).toBeInTheDocument()
  })

  it('sends a team-less manager to /claim even with an attempted page', () => {
    mockAuth({ ...manager, team: null }, false)

    renderLogin({ from: '/league' })

    expect(screen.getByTestId('claim')).toBeInTheDocument()
    expect(screen.queryByTestId('league')).toBeNull()
  })
})