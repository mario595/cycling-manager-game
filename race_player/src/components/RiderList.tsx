import { useMemo } from 'react'
import {
  FlagOutlined,
  TeamOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import type { Rider } from '../types/race'

interface RiderListProps {
  riders: Rider[]
  onSelectRider?: (id: string) => void
}

const MEDALS = ['🥇', '🥈', '🥉']

function EnergyBar({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-slate-400 w-4">{label}</span>
      <div className="flex-1 h-1.5 rounded bg-slate-100 overflow-hidden">
        <div
          className="h-full rounded transition-all"
          style={{ width: `${value}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs tabular-nums text-slate-600 w-8 text-right">
        {Math.round(value)}
      </span>
    </div>
  )
}

function RiderStateIcons({ rider }: { rider: Rider }) {
  return (
    <span className="inline-flex items-center gap-1 ml-1.5 align-middle">
      {rider.pulling && (
        <FlagOutlined style={{ color: '#3b82f6' }} aria-label="pulling" />
      )}
      {rider.surging && (
        <ThunderboltOutlined style={{ color: '#f59e0b' }} aria-label="surging" />
      )}
      {rider.drafting && (
        <TeamOutlined style={{ color: '#22c55e' }} aria-label="drafting" />
      )}
    </span>
  )
}

export default function RiderList({ riders, onSelectRider }: RiderListProps) {
  const sorted = useMemo(
    () => [...riders].sort((a, b) => b.pos - a.pos),
    [riders],
  )

  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-slate-50 text-left text-xs text-slate-500 border-b border-slate-200">
            <th className="px-3 py-2">#</th>
            <th className="px-3 py-2">Rider</th>
            <th className="px-3 py-2 text-right">Meters</th>
            <th className="px-3 py-2 text-right">Speed</th>
            <th className="px-3 py-2">Stamina</th>
            <th className="px-3 py-2">Energy</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((rider, i) => (
            <tr
              key={rider.id}
              className="border-b border-slate-100 last:border-0 hover:bg-slate-50 cursor-pointer"
              onClick={() => onSelectRider?.(rider.id)}
            >
              <td className="px-3 py-2 text-slate-500">
                {i < 3 ? MEDALS[i] : i + 1}
              </td>
              <td className="px-3 py-2 font-medium text-slate-800">
                {rider.name}
                <RiderStateIcons rider={rider} />
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-slate-600">
                {Math.round(rider.pos).toLocaleString()}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-slate-600">
                {rider.finished ? '✓' : `${(rider.speed * 3.6).toFixed(0)} km/h`}
              </td>
              <td className="px-3 py-2 w-40">
                <EnergyBar value={rider.stamina} label="S" color="#3b82f6" />
              </td>
              <td className="px-3 py-2 w-40">
                <EnergyBar value={rider.energy} label="E" color="#ef4444" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex items-center gap-4 px-3 py-2 text-xs text-slate-500 border-t border-slate-200 bg-slate-50">
        <span className="inline-flex items-center gap-1">
          <FlagOutlined style={{ color: '#3b82f6' }} /> pulling (on the front)
        </span>
        <span className="inline-flex items-center gap-1">
          <ThunderboltOutlined style={{ color: '#f59e0b' }} /> surging (attacking)
        </span>
        <span className="inline-flex items-center gap-1">
          <TeamOutlined style={{ color: '#22c55e' }} /> drafting (saving energy)
        </span>
      </div>
    </div>
  )
}
