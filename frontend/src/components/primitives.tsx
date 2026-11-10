import type { CSSProperties, ReactNode } from 'react'

import { barColor, color, font } from '../theme'

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
 * the "next deadline" emphasis tile. `suffixColor` overrides the suffix's
 * muted colour — the Finances tiles use it to show this week's change in
 * green or red.
 */
export function StatTile({
  label,
  value,
  suffix,
  suffixColor,
  dark = false,
  minWidth = 120,
}: {
  label: string
  value: string
  suffix?: string
  suffixColor?: string
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
        {suffix ? <span style={{ fontSize: 12, color: suffixColor ?? color.muted }}>{suffix}</span> : null}
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

/**
 * One rider attribute on the 0-10 display scale as a labelled coloured bar
 * with its value printed beside it — the shared readout on the roster cards
 * and the squad-selection rows, so a rider reads the same everywhere.
 */
export function LabelBar({ label, value }: { label: string; value: number }) {
  const scaled = value * 10
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 90 }}>
      <span style={{ fontSize: 9.5, color: color.muted, fontFamily: font.mono, width: 26 }}>
        {label}
      </span>
      <Bar value={scaled} fill={barColor(scaled)} />
      <span
        style={{
          fontSize: 11,
          fontWeight: 600,
          fontFamily: font.mono,
          width: 14,
          textAlign: 'right',
        }}
      >
        {value}
      </span>
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
  disabled = false,
  ariaLabel,
  style,
}: {
  children: ReactNode
  variant?: 'primary' | 'secondary'
  onClick?: () => void
  disabled?: boolean
  /** For a button whose text is a glyph, where the glyph alone is not a
   * name a screen reader can use. */
  ariaLabel?: string
  style?: CSSProperties
}) {
  const primary = variant === 'primary'
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className={disabled ? undefined : primary ? 'hover-dark' : 'hover-light'}
      style={{
        background: primary ? color.ink : color.canvas,
        color: primary ? '#FFFFFF' : color.ink,
        border: primary ? 'none' : `1px solid ${color.borderButton}`,
        borderRadius: 9,
        padding: '9px 15px',
        fontSize: 13,
        fontWeight: 500,
        cursor: disabled ? 'not-allowed' : 'pointer',
        ...style,
      }}
    >
      {children}
    </button>
  )
}

/** The tiny mono label that sits before a row of filter/sort chips. */
export function ChipLabel({ children }: { children: ReactNode }) {
  return (
    <span
      style={{
        fontSize: 10.5,
        letterSpacing: '1.2px',
        color: color.mutedStrong,
        fontFamily: font.mono,
        marginRight: 2,
      }}
    >
      {children}
    </span>
  )
}

/** A toggle button for the filter and sort rows on list screens. */
export function Chip({
  children,
  active,
  onClick,
}: {
  children: ReactNode
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      style={{
        padding: '6px 12px',
        borderRadius: 8,
        fontSize: 12.5,
        cursor: 'pointer',
        border: `1px solid ${active ? color.ink : color.borderButton}`,
        background: active ? color.ink : color.surface,
        color: active ? '#FFFFFF' : '#565A61',
        fontWeight: active ? 600 : 400,
      }}
    >
      {children}
    </button>
  )
}

/** The pill that marks a rider who retires when the running season closes
 * (#42). Deliberately carries no reason and no date: the player is told
 * *that* it is coming and nothing about *why* this rider and not another —
 * the retirement age is a hidden trait's consequence, not a number. */
export function FinalSeasonTag() {
  return (
    <span
      title="Retires when this season ends"
      style={{
        fontSize: 10.5,
        letterSpacing: '1px',
        fontFamily: font.mono,
        color: color.accentInk,
        background: color.accentWash,
        borderRadius: 6,
        padding: '2px 7px',
        whiteSpace: 'nowrap',
      }}
    >
      LAST SEASON
    </span>
  )
}

/** The pill that marks an auction a team is running under insolvency (#27):
 * the seller's rider is gone whether or not anyone bids, which a bidder is
 * owed knowing — it explains an unusually keen reserve. */
export function ForcedSaleTag() {
  return (
    <span
      title="Sold under insolvency: the rider has already left their team"
      style={{
        alignSelf: 'flex-start',
        marginTop: 4,
        fontSize: 10.5,
        letterSpacing: '1px',
        fontFamily: font.mono,
        color: color.negative,
        background: color.accentWash,
        borderRadius: 6,
        padding: '2px 7px',
        whiteSpace: 'nowrap',
      }}
    >
      FORCED SALE
    </span>
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
