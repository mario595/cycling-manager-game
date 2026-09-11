import type { CSSProperties, ReactNode } from 'react'

import { color, font } from '../theme'

/** The white rounded panel every block on both screens sits in. */
export function Card({
  children,
  style,
}: {
  children: ReactNode
  style?: CSSProperties
}) {
  return (
    <div
      style={{
        background: color.surface,
        border: `1px solid ${color.border}`,
        borderRadius: 14,
        minWidth: 0,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

/** A card header: a title, optionally with something aligned to the right. */
export function CardHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div
      style={{
        padding: '16px 20px 13px',
        borderBottom: `1px solid ${color.dividerStrong}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
      }}
    >
      <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.2px' }}>{title}</div>
      {action}
    </div>
  )
}

/**
 * The small labelled number tiles in both page headers. `dark` inverts it for
 * the "next deadline" emphasis tile.
 */
export function StatTile({
  label,
  value,
  suffix,
  dark = false,
  minWidth = 120,
}: {
  label: string
  value: string
  suffix?: string
  dark?: boolean
  minWidth?: number
}) {
  return (
    <div
      style={{
        background: dark ? color.ink : color.surface,
        border: `1px solid ${dark ? color.ink : color.border}`,
        borderRadius: 12,
        padding: '11px 15px',
        display: 'flex',
        flexDirection: 'column',
        gap: 3,
        minWidth,
      }}
    >
      <div
        style={{
          fontSize: 10,
          letterSpacing: '1.2px',
          color: dark ? '#B5B9C1' : color.mutedStrong,
          fontFamily: font.mono,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 19,
          fontWeight: 600,
          fontFamily: font.mono,
          color: dark ? color.accent : color.ink,
        }}
      >
        {value}
        {suffix ? <span style={{ fontSize: 12, color: color.muted }}>{suffix}</span> : null}
      </div>
    </div>
  )
}

/** A horizontal 0-100 bar. */
export function Bar({
  value,
  fill,
  height = 5,
}: {
  value: number
  fill: string
  height?: number
}) {
  return (
    <div
      style={{
        height,
        background: color.track,
        borderRadius: 3,
        overflow: 'hidden',
        flex: 1,
        minWidth: 0,
      }}
    >
      <div style={{ width: `${value}%`, height: '100%', background: fill, borderRadius: 3 }} />
    </div>
  )
}

/** The page's eyebrow + title + subtitle block. */
export function PageHeading({
  eyebrow,
  title,
  subtitle,
  aside,
  titleSize = 31,
}: {
  eyebrow?: string | null
  title: string
  subtitle: string
  aside?: ReactNode
  titleSize?: number
}) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'flex-end',
        justifyContent: 'space-between',
        gap: 16,
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {eyebrow ? (
          <div
            style={{
              fontSize: 11,
              letterSpacing: '1.6px',
              color: color.accentInk,
              fontWeight: 600,
              fontFamily: font.mono,
            }}
          >
            {eyebrow}
          </div>
        ) : null}
        <h1 style={{ margin: 0, fontSize: titleSize, fontWeight: 600, letterSpacing: '-1px' }}>
          {title}
        </h1>
        <div style={{ fontSize: 14, color: color.muted }}>{subtitle}</div>
      </div>
      {aside ? <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>{aside}</div> : null}
    </div>
  )
}

/** The dark primary button, and its light secondary counterpart. */
export function Button({
  children,
  variant = 'primary',
  onClick,
  style,
}: {
  children: ReactNode
  variant?: 'primary' | 'secondary'
  onClick?: () => void
  style?: CSSProperties
}) {
  const primary = variant === 'primary'
  return (
    <button
      type="button"
      onClick={onClick}
      className={primary ? 'hover-dark' : 'hover-light'}
      style={{
        background: primary ? color.ink : color.canvas,
        color: primary ? '#FFFFFF' : color.ink,
        border: primary ? 'none' : `1px solid ${color.borderButton}`,
        borderRadius: 9,
        padding: '9px 15px',
        fontSize: 13,
        fontWeight: 500,
        cursor: 'pointer',
        ...style,
      }}
    >
      {children}
    </button>
  )
}

/** The standard content wrapper: page padding and max width. */
export function PageBody({
  children,
  gap = 22,
  paddingTop = 28,
}: {
  children: ReactNode
  gap?: number
  paddingTop?: number
}) {
  return (
    <div
      style={{
        padding: `${paddingTop}px 30px 60px`,
        display: 'flex',
        flexDirection: 'column',
        gap,
        maxWidth: 1360,
        width: '100%',
      }}
    >
      {children}
    </div>
  )
}
