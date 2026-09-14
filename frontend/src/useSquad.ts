import { useEffect, useState } from 'react'

import { getSquad, putSquad, type Squad } from './api'

interface SquadState {
  squad: Squad | null
  loading: boolean
  error: boolean
  save: (riderIds: number[], leaderId: number) => Promise<void>
  saving: boolean
  saveError: string | null
}

/**
 * Fetches once on mount (and when raceId changes) — no polling, unlike
 * useCalendar/useSeason. This screen holds unsaved local edits, and a
 * 60-second refetch would silently overwrite whatever the manager is in the
 * middle of picking. `save` refreshes state from the PUT response, which
 * carries the same shape as the GET.
 *
 * The team is always the caller's own — the API derives it from the
 * session, so there is no team id to pass in here any more. See
 * specs/player-accounts-plan.md, D8.
 */
export function useSquad(raceId: number): SquadState {
  const [squad, setSquad] = useState<Squad | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)

    getSquad(raceId)
      .then((data) => {
        if (cancelled) return
        setSquad(data)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setError(true)
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [raceId])

  const save = async (riderIds: number[], leaderId: number) => {
    setSaving(true)
    setSaveError(null)
    try {
      const data = await putSquad(raceId, riderIds, leaderId)
      setSquad(data)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Could not save the squad.')
    } finally {
      setSaving(false)
    }
  }

  return { squad, loading, error, save, saving, saveError }
}
