import { useEffect, useRef, useState } from 'react'

import { getFinances, type Finances } from './api'

interface FinancesState {
  finances: Finances | null
  loading: boolean
  error: boolean
  refresh: () => void
}

/**
 * Polls the caller's own team's finances every 60s, same lifecycle and
 * discipline as useStaff and useRoster: renders nothing while loading, and
 * a screen with a fabricated balance mid-fetch is indistinguishable from a
 * real one with a bug in it.
 */
export function useFinances(): FinancesState {
  const [finances, setFinances] = useState<Finances | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const cancelledRef = useRef(false)

  const fetchFinances = () => {
    getFinances()
      .then((data) => {
        if (cancelledRef.current) return
        setFinances(data)
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
    fetchFinances()
    const pollInterval = setInterval(fetchFinances, 60_000)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  return { finances, loading, error, refresh: fetchFinances }
}