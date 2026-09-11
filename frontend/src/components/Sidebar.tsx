import { NavLink } from 'react-router-dom'

import { NAV_SECTIONS } from '../navigation'
import { TEAM } from '../placeholderData'
import { color, font } from '../theme'
import { useClock } from '../useClock'

// No per-user timezone setting exists yet, so every player sees the game
// clock in CET/CEST. When that setting lands, this becomes the fallback
// passed to formatGameDate instead of a hardcoded default.
const DEFAULT_TIMEZONE = 'Europe/Paris'

const gameDateFormatter = new Intl.DateTimeFormat(undefined, {
  timeZone: DEFAULT_TIMEZONE,
  year: 'numeric',
  month: 'short',
  day: 'numeric',
})

const gameTimeFormatter = new Intl.DateTimeFormat(undefined, {
  timeZone: DEFAULT_TIMEZONE,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

function formatGameDate(date: Date): string {
  return `${gameDateFormatter.format(date)} · ${gameTimeFormatter.format(date)}`
}

interface SidebarProps {
  /** True below the mobile breakpoint, where the rail becomes a drawer. */
  mobile: boolean
  /** Whether the drawer is showing. Ignored on desktop. */
  open: boolean
  /** Called after a nav item is picked, so the drawer can close itself. */
  onNavigate: () => void
}

export function Sidebar({ mobile, open, onNavigate }: SidebarProps) {
  const { now, error } = useClock()
  const dateLabel = now && !error ? formatGameDate(now) : TEAM.season

  const style: React.CSSProperties = mobile
    ? {
        position: 'fixed',
        top: 0,
        left: 0,
        bottom: 0,
        width: '268px',
        zIndex: 60,
        background: color.rail,
        borderRight: `1px solid ${color.railBorder}`,
        display: 'flex',
        flexDirection: 'column',
        transform: open ? 'translateX(0)' : 'translateX(-100%)',
        transition: 'transform .26s cubic-bezier(.2,.8,.2,1)',
        boxShadow: open ? '0 0 60px rgba(0,0,0,.35)' : 'none',
      }
    : {
        position: 'sticky',
        top: 0,
        alignSelf: 'flex-start',
        height: '100vh',
        width: '248px',
        flex: '0 0 248px',
        background: color.rail,
        borderRight: `1px solid ${color.railBorder}`,
        display: 'flex',
        flexDirection: 'column',
      }

  return (
    <aside style={style}>
      <div style={{ padding: '22px 20px 18px', display: 'flex', alignItems: 'center', gap: 11 }}>
        <div
          style={{
            width: 30,
            height: 30,
            background: color.accent,
            borderRadius: 7,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: color.ink,
            fontWeight: 700,
            fontSize: 14,
            letterSpacing: '-0.5px',
          }}
        >
          {TEAM.code}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 14.5, letterSpacing: '-0.2px' }}>{TEAM.name}</div>
          <div style={{ color: color.mutedStrong, fontSize: 11, fontFamily: font.mono }}>
            {TEAM.tier}
          </div>
        </div>
      </div>

      <nav
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '4px 12px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
        }}
      >
        {NAV_SECTIONS.map((section) => (
          <div key={section.label} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <div
              style={{
                padding: '6px 8px',
                color: color.mutedStrong,
                fontSize: 10,
                letterSpacing: '1.4px',
                fontWeight: 600,
                fontFamily: font.mono,
              }}
            >
              {section.label}
            </div>
            {section.items.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                onClick={onNavigate}
                className={({ isActive }) => (isActive ? undefined : 'hover-rail-item')}
                style={({ isActive }) => ({
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  width: '100%',
                  textAlign: 'left',
                  padding: '8px 10px',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontSize: 13.5,
                  letterSpacing: '-0.1px',
                  background: isActive ? color.surface : 'transparent',
                  color: isActive ? color.ink : '#565A61',
                  fontWeight: isActive ? 600 : 400,
                })}
              >
                {({ isActive }) => (
                  <>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span
                        style={{
                          width: 5,
                          height: 5,
                          borderRadius: 2,
                          background: isActive ? color.accent : '#C3C7CE',
                          flex: '0 0 5px',
                        }}
                      />
                      <span>{item.name}</span>
                    </span>
                    {item.badge ? (
                      <span
                        style={{
                          background: color.accent,
                          color: color.ink,
                          fontSize: 10,
                          fontWeight: 700,
                          minWidth: 18,
                          height: 18,
                          borderRadius: 9,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          padding: '0 5px',
                          fontFamily: font.mono,
                        }}
                      >
                        {item.badge}
                      </span>
                    ) : null}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div
        style={{
          borderTop: '1px solid #DFE2E6',
          padding: '14px 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <div style={{ fontSize: 13, fontWeight: 500 }}>{TEAM.manager}</div>
          <div style={{ color: color.mutedStrong, fontSize: 11, fontFamily: font.mono }}>
            {dateLabel}
          </div>
        </div>
        <button
          type="button"
          className="hover-accent-border"
          style={{
            background: 'transparent',
            border: '1px solid #D3D7DC',
            color: color.mutedStrong,
            borderRadius: 8,
            padding: '6px 10px',
            fontSize: 11.5,
            cursor: 'pointer',
          }}
        >
          Settings
        </button>
      </div>
    </aside>
  )
}
