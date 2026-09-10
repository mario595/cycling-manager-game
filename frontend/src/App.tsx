import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { Layout } from './components/Layout'
import { NAV_ITEMS } from './navigation'
import { Dashboard } from './screens/Dashboard'
import { Placeholder } from './screens/Placeholder'
import { Roster } from './screens/Roster'

/**
 * Screens that are actually built. Every other nav item gets the placeholder,
 * which is what keeps the sidebar honest: adding a screen here is the only
 * step needed to replace its placeholder.
 */
const SCREENS: Record<string, React.ComponentType> = {
  '/': Dashboard,
  '/roster': Roster,
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          {NAV_ITEMS.map((item) => {
            const Screen = SCREENS[item.path] ?? Placeholder
            // '/' is the layout's index route; the rest are plain paths.
            return item.path === '/' ? (
              <Route key={item.path} index element={<Screen />} />
            ) : (
              <Route key={item.path} path={item.path} element={<Screen />} />
            )
          })}
          {/* Anything outside the nav — a stale bookmark, a typo — still gets
              the chrome rather than a blank page. */}
          <Route path="*" element={<Placeholder />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
