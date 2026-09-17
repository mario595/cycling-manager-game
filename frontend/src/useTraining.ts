import { useEffect, useRef, useState } from 'react'

import { getTraining, type TrainingState } from './api'

interface TrainingStateShape {
  training: TrainingState | null
  loading: boolean
  error: boolean
  refresh: () => void
}

/**
 * Polls the caller's team's training every 60s, same lifecycle as useStaff
 * (including rendering nothing while loading or on error rather than a
 * fabricated payload) — and so a week rollover appears on this screen without
 * a manual refresh.
 *
 * Exposes refresh() so the screen can re-fetch right after the manager sets a
 * focus instead of waiting up to 60s for the next poll.
 */
export function useTraining(): TrainingStateShape {
  const [training, setTraining] = useState<TrainingState | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const cancelledRef = useRef(false)

  const fetchTraining = () => {
    getTraining()
      .then((data) => {
        if (cancelledRef.current) return
        setTraining(data)
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
    fetchTraining()
    const pollInterval = setInterval(fetchTraining, 60_000)

    return () => {
      cancelledRef.current = true
      clearInterval(pollInterval)
    }
  }, [])

  return { training, loading, error, refresh: fetchTraining }
}