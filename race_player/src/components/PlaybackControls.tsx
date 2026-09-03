import { Button, Segmented, Slider, Space } from 'antd'
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

interface PlaybackControlsProps {
  playing: boolean
  onTogglePlay: () => void
  tick: number
  maxTicks: number
  speed: number
  onSpeedChange: (speed: number) => void
  onTickChange: (tick: number) => void
  onStep: (dir: -1 | 1) => void
}

export default function PlaybackControls({
  playing,
  onTogglePlay,
  tick,
  maxTicks,
  speed,
  onSpeedChange,
  onTickChange,
  onStep,
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

        <div className="ml-auto text-sm text-slate-500">
          tick {tick} / {maxTicks}
        </div>
      </div>

      <Slider
        min={0}
        max={maxTicks}
        value={tick}
        onChange={(v) => onTickChange(v as number)}
        tooltip={{ formatter: (v) => `tick ${v}` }}
      />
    </div>
  )
}
