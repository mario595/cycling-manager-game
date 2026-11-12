import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { titleForPath } from '../navigation'
import { seasonLabel } from '../seasonLabel'
import { MOBILE_BREAKPOINT, color, font } from '../theme'
import { useAuth } from '../useAuth'
import { useSeason } from '../useSeason'
import { ReportProblemButton } from './ReportProblem'
import { Sidebar } from './Sidebar'

/** Routes that a logged-in, team-less user must still be able to reach —
 * the auth flow itself, and /claim, the destination of the redirect below.
 * Without this list a team-less user landing on /claim would be bounced
 * straight back to itself. */
const TEAM_LESS_ALLOWED_PATHS = new Set(['/login', '/register', '/claim'])

/** The only routes a visitor with no session may reach. Registration must be
 * here or a new player could never get an account. */
const ANON_ALLOWED_PATHS = new Set(['/login', '/register'])

/** True while the viewport is narrow enough to want the drawer layout. */
function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < MOBILE_BREAKPOINT,
  )

  useEffect(() => {
    const query = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    const update = () => setMobile(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  return mobile
}

export function Layout() {
  const mobile = useIsMobile()
  const [drawer, setDrawer] = useState(false)
  const { pathname } = useLocation()
  const { position } = useSeason()
  const label = seasonLabel(position)
  const { me, loading } = useAuth()
  const teamName = me?.team?.name ?? 'No team'

  // Growing the window past the breakpoint while the drawer is open would
  // otherwise leave `drawer` stuck true behind the now-static sidebar.
  useEffect(() => {
    if (!mobile) setDrawer(false)
  }, [mobile])

  // `loading` gates both guards and is checked first: useAuth starts with
  // me === null, loading === true, so without it every visitor — including a
  // logged-in manager refreshing the page — would bounce to /login before
  // getMe() answers. A failed getMe() leaves me === null and loading ===
  // false, so it falls through to the login redirect rather than hanging.
  if (loading) return null
  if (!me?.authenticated && !ANON_ALLOWED_PATHS.has(pathname)) {
    return <Navigate to="/login" replace state={{ from: pathname }} />
  }
  // A logged-in user with no team cannot use /roster or a squad screen —
  // both 403 and render an error. Redirect to /claim instead of letting
  // each screen handle the 403 individually.
  if (me?.authenticated && !me.team && !TEAM_LESS_ALLOWED_PATHS.has(pathname)) {
    return <Navigate to="/claim" replace />
  }

  return (
    <div style={{ display: 'flex', height: '100vh', background: color.canvas }}>
      <div
        onClick={() => setDrawer(false)}
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 55,
          background: 'rgba(20,20,22,.45)',
          opacity: mobile && drawer ? 1 : 0,
          pointerEvents: mobile && drawer ? 'auto' : 'none',
          transition: 'opacity .26s',
        }}
      />

      <Sidebar mobile={mobile} open={drawer} onNavigate={() => setDrawer(false)} />

      <main
        style={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          overflowY: 'auto',
        }}
      >
        <header
          style={{
            display: mobile ? 'flex' : 'none',
            alignItems: 'center',
            gap: 12,
            padding: '12px 16px',
            borderBottom: `1px solid ${color.border}`,
            background: '#FAFBFC',
            position: 'sticky',
            top: 0,
            zIndex: 40,
          }}
        >
          <button
            type="button"
            aria-label="Open navigation"
            onClick={() => setDrawer(true)}
            style={{
              background: color.ink,
              border: 'none',
              borderRadius: 9,
              width: 38,
              height: 38,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
            }}
          >
            <span style={{ width: 16, height: 2, background: '#FDFDFD', borderRadius: 2 }} />
            <span style={{ width: 16, height: 2, background: '#FDFDFD', borderRadius: 2 }} />
            <span style={{ width: 16, height: 2, background: '#FDFDFD', borderRadius: 2 }} />
          </button>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600, letterSpacing: '-0.2px' }}>
              {titleForPath(pathname)}
            </div>
            <div style={{ fontSize: 11, color: color.muted, fontFamily: font.mono }}>
              {teamName.toUpperCase()}
              {label ? ` · ${label}` : ''}
            </div>
          </div>
        </header>

        {!mobile && label ? (
          <div
            style={{
              padding: '10px 24px',
              borderBottom: `1px solid ${color.border}`,
              background: '#FAFBFC',
              fontSize: 11,
              letterSpacing: '1px',
              color: color.mutedStrong,
              fontFamily: font.mono,
            }}
          >
            {label.toUpperCase()}
          </div>
        ) : null}

        <Outlet />
      </main>

      {/* Every logged-in screen, /claim included; never the login or
          register pages, which also render inside this frame (#131). */}
      {me?.authenticated ? <ReportProblemButton /> : null}
    </div>
  )
}
