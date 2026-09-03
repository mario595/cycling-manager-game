import { useEffect, useState } from 'react'
import RaceViz from './components/RaceViz'
import type { ParsedRace } from './types/race'
import { parseRaceLog } from './utils/parseRaceLog'

export default function App() {
  const [raceData, setRaceData] = useState<ParsedRace | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/race.jsonl')
        if (!res.ok) throw new Error(`Failed to fetch race.jsonl: ${res.status}`)
        const text = await res.text()
        if (!cancelled) setRaceData(parseRaceLog(text))
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        Loading race data…
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center text-red-500 p-6">
        <p>
          Error loading race data. Place a <code className="bg-slate-100 px-1 rounded">race.jsonl</code>{' '}
          file in <code className="bg-slate-100 px-1 rounded">public/</code> or serve it at{' '}
          <code className="bg-slate-100 px-1 rounded">/race.jsonl</code>.
          <br />
          <span className="text-slate-400 text-sm">{error}</span>
        </p>
      </div>
    )
  }

  if (!raceData) return null

  return <RaceViz raceData={raceData} />
}
