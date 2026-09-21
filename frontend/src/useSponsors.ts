import { useEffect, useRef, useState } from 'react'

import { getSponsors, type Sponsors } from './api'

interface SponsorsState {
  sponsors: Sponsors | null
  loading: boolean
  error: boolean
  refresh: () => void
}

/**
 * Polls the caller's own team's sponsorship every 60s, same lifecycle as
 * useStaff. Renders nothing while loading or on error rather than a
 * fabricated state — a screen showing an invented round mid-fetch is
 * indistinguishable from a real one with a bug in it.
 *
 * Exposes refresh() so the screen can re-fetch right after signing instead
 * of waiting up to 60s for the next poll.
 */
export function useSponsors(): SponsorsState {
  const [sponsors, setSponsors] = useState<Sponsors | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const cancelledRef = useRef(false)

  const fetchSponsors = () => {
    getSponsors()
      .then((data) => {
        if (cancelledRef.current) return
        setSponsors(data)
        setError(false)
        setLoading(false)
      })
      .catch(() => {
        if (cancelledRef.current) return
        setError(true)
        setLoading(false)
      })
  }

  useEffect(() => {
    cancelledRef.current = false
    fetchSponsors()
    const pollInterval = setInterval(fetchSponsors, 60_000)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  return { sponsors, loading, error, refresh: fetchSponsors }
}
