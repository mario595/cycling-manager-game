import { useEffect, useState } from 'react'
import FileExplorer from './components/FileExplorer'
import RaceViz from './components/RaceViz'
import type { ParsedRace } from './types/race'
import { parseRaceLog } from './utils/parseRaceLog'

export default function App() {
  const [selectedFile, setSelectedFile] = useState<string>('race.jsonl')
  const [raceData, setRaceData] = useState<ParsedRace | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        const res = await fetch(`/${selectedFile}`)
        if (!res.ok) throw new Error(`Failed to fetch ${selectedFile}: ${res.status}`)
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
  }, [selectedFile])

  return (
    <div className="flex gap-4 p-4 max-w-6xl mx-auto">
      <aside className="w-52 shrink-0">
        <FileExplorer selected={selectedFile} onSelect={setSelectedFile} />
      </aside>

      <main className="flex-1 min-w-0">
        {loading && (
          <div className="min-h-screen flex items-center justify-center text-slate-500">
            Loading race data…
          </div>
        )}

        {!loading && error && (
          <div className="min-h-screen flex items-center justify-center text-red-500 p-6">
            <p>
              Error loading race data. Place a{' '}
              <code className="bg-slate-100 px-1 rounded">.jsonl</code> file in{' '}
              <code className="bg-slate-100 px-1 rounded">public/</code> or serve it.
              <br />
              <span className="text-slate-400 text-sm">{error}</span>
            </p>
          </div>
        )}

        {!loading && !error && raceData && <RaceViz raceData={raceData} />}
      </main>
    </div>
  )
}
