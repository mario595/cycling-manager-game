import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { titleForPath } from '../navigation'
import { TEAM } from '../placeholderData'
import { seasonLabel } from '../seasonLabel'
import { MOBILE_BREAKPOINT, color, font } from '../theme'
import { useSeason } from '../useSeason'
import { Sidebar } from './Sidebar'

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

  // Growing the window past the breakpoint while the drawer is open would
  // otherwise leave `drawer` stuck true behind the now-static sidebar.
  useEffect(() => {
    if (!mobile) setDrawer(false)
  }, [mobile])

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: color.canvas }}>
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

      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
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
              {TEAM.name.toUpperCase()}
              {label ? ` · ${label}` : ''}
            </div>
          </div>
          <div
            style={{
              marginLeft: 'auto',
              background: color.surface,
              border: `1px solid ${color.border}`,
              borderRadius: 9,
              padding: '7px 11px',
              fontSize: 12,
              fontFamily: font.mono,
            }}
          >
            {TEAM.budget}
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
    </div>
  )
}
