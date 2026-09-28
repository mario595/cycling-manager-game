import { useEffect, useRef, useState } from 'react'

import { getDevelopmentSquad, type DevelopmentSquad as DevelopmentSquadPayload } from './api'

interface DevelopmentSquadState {
  squad: DevelopmentSquadPayload | null
  loading: boolean
  error: boolean
  refresh: () => void
}

/**
 * Polls the caller's own team's development squad every 60s, same lifecycle
 * as useStaff. Renders nothing while loading or on error rather than a
 * fabricated squad state — a screen showing three invented levels mid-fetch
 * is indistinguishable from a real one with a bug in it.
 *
 * Exposes refresh() so the screen can re-fetch right after an open, change or
 * close instead of waiting up to 60s for the next poll.
 */
export function useDevelopmentSquad(): DevelopmentSquadState {
  const [squad, setSquad] = useState<DevelopmentSquadPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const cancelledRef = useRef(false)

  const fetchSquad = () => {
    getDevelopmentSquad()
      .then((data) => {
        if (cancelledRef.current) return
        setSquad(data)
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
    fetchSquad()
    const pollInterval = setInterval(fetchSquad, 60_000)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  return { squad, loading, error, refresh: fetchSquad }
}
