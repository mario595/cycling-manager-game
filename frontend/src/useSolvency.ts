import { useEffect, useRef, useState } from 'react'

import { getSolvency, type Solvency } from './api'

interface SolvencyState {
  solvency: Solvency | null
  loading: boolean
  error: boolean
  refresh: () => void
}

/**
 * Polls the caller's insolvency standing every 60s, same lifecycle and
 * discipline as useFinances: nothing is rendered from it while loading, since
 * a banner telling a solvent manager their team is in trouble — or the
 * reverse — is worse than none.
 */
export function useSolvency(): SolvencyState {
  const [solvency, setSolvency] = useState<Solvency | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const cancelledRef = useRef(false)

  const fetchSolvency = () => {
    getSolvency()
      .then((data) => {
        if (cancelledRef.current) return
        setSolvency(data)
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
    fetchSolvency()
    const pollInterval = setInterval(fetchSolvency, 60_000)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  return { solvency, loading, error, refresh: fetchSolvency }
}
