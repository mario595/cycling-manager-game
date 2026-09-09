import { Button, Segmented, Space } from 'antd'
import {
  CaretRightOutlined,
  PauseOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from '@ant-design/icons'

const SPEEDS = [
  { label: 'x1', value: 1 },
  { label: 'x2', value: 2 },
  { label: 'x5', value: 5 },
  { label: 'x10', value: 10 },
  { label: 'x25', value: 25 },
  { label: 'x50', value: 50 },
]

// 1 tick = 1 second of race time.
function formatDuration(ticks: number): string {
  const hours = Math.floor(ticks / 3600)
  const minutes = Math.floor((ticks % 3600) / 60)
  const seconds = ticks % 60
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}

interface PlaybackControlsProps {
  playing: boolean
  onTogglePlay: () => void
  tick: number
  maxTicks: number
  speed: number
  onSpeedChange: (speed: number) => void
  onStep: (dir: -1 | 1) => void
  onSeek: (tick: number) => void
}

export default function PlaybackControls({
  playing,
  onTogglePlay,
  tick,
  maxTicks,
  speed,
  onSpeedChange,
  onStep,
  onSeek,
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

        <div className="ml-auto flex flex-col items-end text-sm text-slate-500 tabular-nums">
          <span>{formatDuration(tick)} / {formatDuration(maxTicks)}</span>
          <span className="text-xs text-slate-400">tick {tick} / {maxTicks}</span>
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
