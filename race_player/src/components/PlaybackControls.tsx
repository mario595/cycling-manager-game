import { Button, Segmented, Space } from 'antd'
import {
  CaretRightOutlined,
  PauseOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from '@ant-design/icons'
import type { Wind } from '../types/race'
import WindCompass from './WindCompass'

const SPEEDS = [
  { label: 'x1', value: 1 },
  { label: 'x2', value: 2 },
  { label: 'x5', value: 5 },
  { label: 'x10', value: 10 },
  { label: 'x25', value: 25 },
  { label: 'x50', value: 50 },
]

// Takes race seconds. Callers convert from ticks via the header's tickInterval:
// a tick is not a second (see the plan for #88).
export function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  return `${hours}h ${minutes}m ${secs}s`
}

interface PlaybackControlsProps {
  playing: boolean
  onTogglePlay: () => void
  tick: number
  maxTicks: number
  tickInterval: number
  speed: number
  onSpeedChange: (speed: number) => void
  onStep: (dir: -1 | 1) => void
  onSeek: (tick: number) => void
  wind?: Wind
}

export default function PlaybackControls({
  playing,
  onTogglePlay,
  tick,
  maxTicks,
  tickInterval,
  speed,
  onSpeedChange,
  onStep,
  onSeek,
  wind,
}: PlaybackControlsProps) {
  return (
    <div className="flex flex-col gap-2 p-3 bg-white rounded-lg border border-slate-200">
      <div className="flex items-center gap-3">
        <Space>
          <Button
            onClick={() => onStep(-1)}
            icon={<StepBackwardOutlined />}
            aria-label="Step back"
          />
          <Button
            type="primary"
            shape="circle"
            icon={playing ? <PauseOutlined /> : <CaretRightOutlined />}
            onClick={onTogglePlay}
            aria-label={playing ? 'Pause' : 'Play'}
          />
          <Button
            onClick={() => onStep(1)}
            icon={<StepForwardOutlined />}
            aria-label="Step forward"
          />
        </Space>

        <Segmented
          options={SPEEDS.map((s) => s.label)}
          value={`x${speed}`}
          onChange={(v) => onSpeedChange(Number(String(v).replace('x', '')))}
        />

        <div className="ml-auto flex items-center gap-3">
          <div className="flex flex-col items-end text-sm text-slate-500 tabular-nums">
            <span>{formatDuration(tick * tickInterval)} / {formatDuration(maxTicks * tickInterval)}</span>
            <span className="text-xs text-slate-400">tick {tick} / {maxTicks}</span>
          </div>
          <WindCompass wind={wind} />
        </div>
      </div>

      <input
        type="range"
        min={0}
        max={maxTicks}
        value={tick}
        onChange={(e) => onSeek(Number(e.target.value))}
        className="w-full accent-blue-600 cursor-pointer"
        aria-label="Seek"
      />
    </div>
  )
}
