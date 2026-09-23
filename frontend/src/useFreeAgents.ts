import { useEffect, useRef, useState } from 'react'

import { getFreeAgents, type FreeAgentPool } from './api'

interface FreeAgentsState {
  pool: FreeAgentPool | null
  loading: boolean
  error: boolean
  refresh: () => void
}

/**
 * Polls the transfer market's free agent pool every 60s, same lifecycle as
 * useRoster. Renders nothing while loading or on error rather than a
 * fabricated pool — a screen showing invented riders mid-fetch is
 * indistinguishable from a real one with a bug in it, the same discipline
 * useRoster.ts established.
 *
 * Exposes refresh() so the screen can re-fetch right after a sign instead
 * of waiting up to 60s for the next poll.
 */
export function useFreeAgents(): FreeAgentsState {
  const [pool, setPool] = useState<FreeAgentPool | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const cancelledRef = useRef(false)

  const fetchPool = () => {
    getFreeAgents()
      .then((data) => {
        if (cancelledRef.current) return
        setPool(data)
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
    fetchPool()
    const pollInterval = setInterval(fetchPool, 60_000)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  return { pool, loading, error, refresh: fetchPool }
}