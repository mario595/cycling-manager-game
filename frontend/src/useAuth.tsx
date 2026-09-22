import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import {
  acknowledgeSpell as apiAcknowledgeSpell,
  claimTeam as apiClaimTeam,
  getMe,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  type Me,
} from './api'

interface AuthState {
  me: Me | null
  loading: boolean
  register: (email: string, password: string, displayName: string) => Promise<void>
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  claim: (name: string, code: string) => Promise<void>
  acknowledgeLostTeam: (spellId: number) => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

/**
 * One shared fetch of "who is logged in", not one per component — the
 * sidebar, the race screen and the login/register screens all need the same
 * answer, and three independent getMe() calls on mount would be three round
 * trips for one fact.
 *
 * register/login only confirm the display name (accounts/ cannot know about
 * teams — see specs/player-accounts-plan.md, D9), so both refresh `me` via
 * getMe() afterwards rather than trusting their own response.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    getMe()
      .then((data) => {
        if (cancelled) return
        setMe(data)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const register = async (email: string, password: string, displayName: string) => {
    await apiRegister(email, password, displayName)
    setMe(await getMe())
  }

  const login = async (email: string, password: string) => {
    await apiLogin(email, password)
    setMe(await getMe())
  }

  const logout = async () => {
    await apiLogout()
    setMe({ authenticated: false, display_name: null, team: null, lost_team: null })
  }

  const claim = async (name: string, code: string) => {
    await apiClaimTeam(name, code)
    setMe(await getMe())
  }

  const acknowledgeLostTeam = async (spellId: number) => {
    await apiAcknowledgeSpell(spellId)
    setMe((current) => (current ? { ...current, lost_team: null } : current))
  }

  return (
    <AuthContext.Provider
      value={{ me, loading, register, login, logout, claim, acknowledgeLostTeam }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (context === null) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
