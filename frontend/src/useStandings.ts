import { useEffect, useState } from 'react'

import { getStandings, type Standings } from './api'

interface StandingsState {
  standings: Standings | null
  loading: boolean
  error: boolean
}

/**
 * Polls the standings every 60s, same lifecycle as useCalendar. No
 * client-side interpolation: nothing here changes between polls in a way
 * worth animating.
 */
export function useStandings(): StandingsState {
  const [standings, setStandings] = useState<Standings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false

    const fetchStandings = () => {
      getStandings()
        .then((data) => {
          if (cancelled) return
          setStandings(data)
          setError(false)
          setLoading(false)
        })
        .catch(() => {
          if (cancelled) return
          setError(true)
          setLoading(false)
        })
    }

    fetchStandings()
    const pollInterval = setInterval(fetchStandings, 60_000)

    return () => {
      cancelled = true
      clearInterval(pollInterval)
    }
  }, [])

  return { standings, loading, error }
}
