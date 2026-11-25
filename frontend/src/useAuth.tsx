import { createContext, useContext, useEffect, useRef, useState } from 'react'
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
  /** Re-read `me` now, e.g. right after signing a sponsor (#161). */
  refresh: () => void
}

/** How often `me` is re-read, the same cadence as useSponsors and useSolvency. */
const POLL_MS = 60_000

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

  // The last answer, as JSON: a poll that brings back the same `me` must not
  // hand every consumer a new object and re-render the whole app.
  const lastRef = useRef<string | null>(null)
  const cancelledRef = useRef(false)

  const accept = (data: Me) => {
    const json = JSON.stringify(data)
    if (json === lastRef.current) return
    lastRef.current = json
    setMe(data)
  }

  const refresh = () => {
    getMe()
      .then((data) => {
        if (cancelledRef.current) return
        accept(data)
        setLoading(false)
      })
      .catch(() => {
        if (cancelledRef.current) return
        setLoading(false)
      })
  }

  // `me` is polled, not read once, because part of it moves with the game:
  // `team.sponsor_missing` turns true when a season opens (#161), and an
  // open tab should show that without a reload.
  useEffect(() => {
    cancelledRef.current = false
    refresh()
    const pollInterval = setInterval(refresh, POLL_MS)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  const register = async (email: string, password: string, displayName: string) => {
    await apiRegister(email, password, displayName)
    accept(await getMe())
  }

  const login = async (email: string, password: string) => {
    await apiLogin(email, password)
    accept(await getMe())
  }

  const logout = async () => {
    await apiLogout()
    accept({ authenticated: false, display_name: null, team: null, lost_team: null })
  }

  const claim = async (name: string, code: string) => {
    await apiClaimTeam(name, code)
    accept(await getMe())
  }

  const acknowledgeLostTeam = async (spellId: number) => {
    await apiAcknowledgeSpell(spellId)
    setMe((current) => (current ? { ...current, lost_team: null } : current))
  }

  return (
    <AuthContext.Provider
      value={{ me, loading, register, login, logout, claim, acknowledgeLostTeam, refresh }}
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
