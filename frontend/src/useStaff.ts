import { useEffect, useRef, useState } from 'react'

import { getStaff, type Staff } from './api'

interface StaffState {
  staff: Staff | null
  loading: boolean
  error: boolean
  refresh: () => void
}

/**
 * Polls the caller's own team's staff every 60s, same lifecycle as
 * useRoster. Renders nothing while loading or on error rather than a
 * fabricated staff state — a screen showing an invented pool mid-fetch is
 * indistinguishable from a real one with a bug in it, the same discipline
 * useRoster.ts established.
 *
 * Exposes refresh() so the screen can re-fetch right after a hire or fire
 * instead of waiting up to 60s for the next poll.
 */
export function useStaff(): StaffState {
  const [staff, setStaff] = useState<Staff | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const cancelledRef = useRef(false)

  const fetchStaff = () => {
    getStaff()
      .then((data) => {
        if (cancelledRef.current) return
        setStaff(data)
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
    fetchStaff()
    const pollInterval = setInterval(fetchStaff, 60_000)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  return { staff, loading, error, refresh: fetchStaff }
}
