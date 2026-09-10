import { useMemo } from 'react'
import {
  FlagOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import type { Pack, Rider } from '../types/race'
import { isLeader, teamCode, teamColor, teamName } from '../utils/teamColors'
import { formatFinishTime, formatGapTime } from '../utils/formatTime'
import type { RiderResult } from '../utils/raceResults'

const COLUMN_COUNT = 8

interface RiderListProps {
  packs: Pack[]
  teamCodes: Record<string, string>
  teamNames: Record<string, string>
  results: Map<string, RiderResult>
  onSelectRider?: (id: string) => void
}

const MEDALS = ['🥇', '🥈', '🥉']

const STAMINA_YELLOW = 60 // fatigue starts degrading cruise pace below this
const STAMINA_RED = 30 // a rider this low is genuinely cracked

function EnergyBar({ value, label, color, surging = false }: { value: number; label: string; color?: string; surging?: boolean }) {
  let barColor = color ?? '#3b82f6'
  if (!color) {
    // Stamina: green/blue -> yellow when degraded -> red when cracked.
    barColor = value >= STAMINA_YELLOW ? '#3b82f6' : value >= STAMINA_RED ? '#f59e0b' : '#ef4444'
  }
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-slate-400 w-4">{label}</span>
      <div className={`flex-1 h-1.5 rounded overflow-hidden bg-slate-100 ${surging ? 'border border-amber-400' : ''}`}>
        <div
          className={`h-full transition-all ${surging ? 'surge-beat' : ''}`}
          style={{ width: `${value}%`, backgroundColor: barColor }}
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
    </span>
  )
}

function ResultCell({ rider, result }: { rider: Rider; result?: RiderResult }) {
  // `result` is precomputed over the whole race, so it holds a finish time
  // even at ticks before this rider actually crosses the line. Gate on the
  // rider's own live `finished` flag for the currently displayed tick.
  if (!rider.finished || !result) return <>—</>
  if (result.finishTime !== null) return <>{formatFinishTime(result.finishTime)}</>
  if (result.gapSeconds !== null) {
    return <>{result.gapSeconds === 0 ? '+0' : `+${formatGapTime(result.gapSeconds)}`}</>
  }
  return <>—</>
}

function RiderRow({
  rider,
  rank,
  teamCodes,
  teamNames,
  result,
  onSelect,
}: {
  rider: Rider
  rank: number
  teamCodes: Record<string, string>
  teamNames: Record<string, string>
  result?: RiderResult
  onSelect?: (id: string) => void
}) {
  return (
    <tr
      className="border-b border-slate-100 last:border-0 hover:bg-slate-50 cursor-pointer"
      style={{ borderLeft: `3px solid ${teamColor(rider.team)}` }}
      onClick={() => onSelect?.(rider.id)}
    >
      <td className="px-3 py-2 text-slate-500">
        {rank < 3 ? MEDALS[rank] : rank + 1}
      </td>
      <td
        className="px-3 py-2 text-xs font-semibold"
        style={{ color: teamColor(rider.team) }}
        title={teamName(teamNames, rider.team)}
      >
        {teamCode(teamCodes, rider.team)}
      </td>
      <td className="px-3 py-2 font-medium text-slate-800">
        {rider.finished && '✅ '}
        {isLeader(rider) && '👑 '}
        {rider.name}
        <RiderStateIcons rider={rider} />
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-slate-600">
        {(rider.pos / 1000).toFixed(2)} km
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-slate-600">
        {rider.finished ? '✓' : `${(rider.speed * 3.6).toFixed(0)} km/h`}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-slate-600">
        <ResultCell rider={rider} result={result} />
      </td>
      <td className="px-3 py-2 w-40">
        <EnergyBar value={rider.stamina} label="S" />
      </td>
      <td className="px-3 py-2 w-40">
        <EnergyBar value={rider.energy} label="E" color="#ef4444" surging={rider.surging} />
      </td>
    </tr>
  )
}

export default function RiderList({ packs, teamCodes, teamNames, results, onSelectRider }: RiderListProps) {
  const gaps = useMemo(() => {
    const list: (string | null)[] = []
    for (let i = 0; i < packs.length; i++) {
      if (i === 0) {
        list.push(null)
        continue
      }
      const prev = packs[i - 1]
      const cur = packs[i]
      const prevBack = prev.riders[prev.riders.length - 1].pos
      const gapM = Math.max(0, prevBack - cur.frontPos)
      const gapT = cur.speed > 0 ? gapM / cur.speed : 0
      list.push(`+${formatGapTime(gapT)} (${gapM.toFixed(0)}m)`)
    }
    return list
  }, [packs])

  let rank = 0

  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-slate-50 text-left text-xs text-slate-500 border-b border-slate-200">
            <th className="px-3 py-2">#</th>
            <th className="px-3 py-2">Team</th>
            <th className="px-3 py-2">Rider</th>
            <th className="px-3 py-2 text-right">Km</th>
            <th className="px-3 py-2 text-right">Speed</th>
            <th className="px-3 py-2 text-right">Result</th>
            <th className="px-3 py-2">Stamina</th>
            <th className="px-3 py-2">Energy</th>
          </tr>
        </thead>
        {packs.map((pack, pi) => (
          <tbody key={pi} className="align-top">
            {gaps[pi] !== null && (
              <tr>
                <td colSpan={COLUMN_COUNT} className="px-3 py-1.5 bg-slate-100/80 text-center text-xs font-semibold text-slate-600 border-y border-slate-300/60">
                  {gaps[pi]}
                </td>
              </tr>
            )}
            <tr
              aria-hidden
              className="h-0"
            >
              <td colSpan={COLUMN_COUNT} className="border-b-2 border-slate-300" />
            </tr>
            {pack.riders.map((rider) => {
              const r = rank
              rank += 1
              return (
                <RiderRow
                  key={rider.id}
                  rider={rider}
                  rank={r}
                  teamCodes={teamCodes}
                  teamNames={teamNames}
                  result={results.get(rider.id)}
                  onSelect={onSelectRider}
                />
              )
            })}
            <tr aria-hidden className="h-0">
              <td colSpan={COLUMN_COUNT} className="border-b border-slate-200" />
            </tr>
          </tbody>
        ))}
      </table>
      <div className="flex flex-wrap items-center gap-4 px-3 py-2 text-xs text-slate-500 border-t border-slate-200 bg-slate-50">
        <span className="inline-flex items-center gap-1">
          <FlagOutlined style={{ color: '#3b82f6' }} /> pulling (on the front)
        </span>
        <span className="inline-flex items-center gap-1">
          <ThunderboltOutlined style={{ color: '#f59e0b' }} /> surging (attacking)
        </span>
        <span className="inline-flex items-center gap-1">👑 team leader</span>
      </div>
    </div>
  )
}
