import { useEffect, useState } from 'react'

import { getRiders, type Rider } from './api'

interface RosterState {
  riders: Rider[] | null
  loading: boolean
  error: boolean
}

/**
 * Polls the caller's own team's roster every 60s, same lifecycle as
 * useCalendar. Renders nothing while loading or on error rather than a
 * fabricated roster — a screen showing invented riders mid-fetch is
 * indistinguishable from a real roster with a bug in it, the same
 * discipline useSeason.ts established.
 */
export function useRoster(): RosterState {
  const [riders, setRiders] = useState<Rider[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false

    const fetchRiders = () => {
      getRiders()
        .then((data) => {
          if (cancelled) return
          setRiders(data)
          setError(false)
          setLoading(false)
        })
        .catch(() => {
          if (cancelled) return
          setError(true)
          setLoading(false)
        })
    }

    fetchRiders()
    const pollInterval = setInterval(fetchRiders, 60_000)

    return () => {
      cancelled = true
      clearInterval(pollInterval)
    }
  }, [])

  return { riders, loading, error }
}
