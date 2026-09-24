import { useEffect, useRef, useState } from 'react'

import { getRiders, type Rider, type SalaryReview } from './api'

interface RosterState {
  riders: Rider[] | null
  squadValue: number | null
  salaryReview: SalaryReview | null
  loading: boolean
  error: boolean
  refresh: () => void
}

/**
 * Polls the caller's own team's roster every 60s, same lifecycle as
 * useCalendar. Renders nothing while loading or on error rather than a
 * fabricated roster — a screen showing invented riders mid-fetch is
 * indistinguishable from a real roster with a bug in it, the same
 * discipline useSeason.ts established. `squadValue` stays null while
 * loading rather than defaulting to 0, for the same reason.
 *
 * Exposes refresh() so the screen can re-fetch right after a release
 * instead of waiting up to 60s for the next poll.
 */
export function useRoster(): RosterState {
  const [riders, setRiders] = useState<Rider[] | null>(null)
  const [squadValue, setSquadValue] = useState<number | null>(null)
  const [salaryReview, setSalaryReview] = useState<SalaryReview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const cancelledRef = useRef(false)

  const fetchRiders = () => {
    getRiders()
      .then((data) => {
        if (cancelledRef.current) return
        setRiders(data.riders)
        setSquadValue(data.squad_value)
        setSalaryReview(data.salary_review)
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
    fetchRiders()
    const pollInterval = setInterval(fetchRiders, 60_000)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  return { riders, squadValue, salaryReview, loading, error, refresh: fetchRiders }
}