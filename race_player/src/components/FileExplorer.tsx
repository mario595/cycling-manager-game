import { useCallback, useEffect, useState } from 'react'
import { Button } from 'antd'
import { ReloadOutlined, FileTextOutlined } from '@ant-design/icons'
import type { RaceFile } from '../types/race'

interface FileExplorerProps {
  selected: string | null
  onSelect: (file: string) => void
}

function formatMtime(mtime: string): string {
  const d = new Date(mtime)
  const date = d.toLocaleDateString('en-GB') // dd/mm/yyyy
  const time = d.toLocaleTimeString()
  return `${date} ${time}`
}

/**
 * Local dev tool: lists the .jsonl race files available from the server so
 * the user can switch between races. Standalone — no knowledge of the player.
 */
export default function FileExplorer({
  selected,
  onSelect,
}: FileExplorerProps) {
  const [files, setFiles] = useState<RaceFile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/races')
      if (!res.ok) throw new Error(`Failed to list races: ${res.status}`)
      const data = (await res.json()) as { files: RaceFile[] }
      setFiles(data.files)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="flex flex-col h-full p-3 bg-white rounded-lg border border-slate-200">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
          Races
        </h2>
        <Button
          size="small"
          type="text"
          icon={<ReloadOutlined />}
          onClick={() => void load()}
          disabled={loading}
          aria-label="Refresh race list"
        />
      </div>

      {error && <p className="text-xs text-red-500 mb-2">{error}</p>}

      <nav className="flex-1 overflow-y-auto flex flex-col gap-1">
        {loading && !error && (
          <span className="text-xs text-slate-400">Loading…</span>
        )}
        {!loading && files.length === 0 && (
          <span className="text-xs text-slate-400">
            No .jsonl files found in public/
          </span>
        )}
        {files.map((file) => (
          <button
            key={file.name}
            type="button"
            onClick={() => onSelect(file.name)}
            className={[
              'flex items-start gap-2 px-2 py-1.5 rounded text-left text-xs',
              'hover:bg-slate-100 transition-colors',
              selected === file.name
                ? 'bg-blue-50 text-blue-700 font-medium'
                : 'text-slate-700',
            ].join(' ')}
          >
            <FileTextOutlined className="text-slate-400 mt-0.5" />
            <span className="flex flex-col min-w-0">
              <span className="truncate">{file.name}</span>
              <span className="text-[11px] text-slate-400 font-normal">
                {formatMtime(file.mtime)}
              </span>
            </span>
          </button>
        ))}
      </nav>
    </div>
  )
}
