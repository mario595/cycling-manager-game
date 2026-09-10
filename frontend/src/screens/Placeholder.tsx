import { useLocation } from 'react-router-dom'

import { Card, PageBody } from '../components/primitives'
import { titleForPath } from '../navigation'
import { color, font } from '../theme'

/**
 * Stands in for every nav destination that has no screen yet.
 *
 * Its job is to make navigation legible while the app is a shell: clicking any
 * sidebar item lands somewhere real, with the URL and the title proving the
 * route resolved rather than silently falling back to the dashboard.
 */
export function Placeholder() {
  const { pathname } = useLocation()
  const title = titleForPath(pathname)

  return (
    <PageBody gap={18} paddingTop={26}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div
          style={{
            fontSize: 11,
            letterSpacing: '1.6px',
            color: color.accentInk,
            fontWeight: 600,
            fontFamily: font.mono,
          }}
        >
          NOT BUILT YET
        </div>
        <h1 style={{ margin: 0, fontSize: 29, fontWeight: 600, letterSpacing: '-0.9px' }}>
          {title}
        </h1>
        <div style={{ fontSize: 13.5, color: color.muted }}>
          This screen is a placeholder. The route resolves and the sidebar keeps its state, so
          navigation can be checked before the screen exists.
        </div>
      </div>

      <Card
        style={{
          padding: '26px 24px',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          borderStyle: 'dashed',
          borderColor: '#D6DAE0',
          background: 'transparent',
        }}
      >
        <div style={{ fontSize: 12, color: color.mutedStrong, fontFamily: font.mono }}>ROUTE</div>
        <div style={{ fontSize: 15, fontWeight: 600, fontFamily: font.mono }}>{pathname}</div>
      </Card>
    </PageBody>
  )
}
