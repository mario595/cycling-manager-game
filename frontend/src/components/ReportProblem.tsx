import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

import { createReport, type ReportCategory } from '../api'
import { color, font, radius } from '../theme'
import { Button } from './primitives'

/** The four kinds of report, in the order the form offers them. */
export const REPORT_CATEGORIES: { value: ReportCategory; label: string }[] = [
  { value: 'bug', label: 'Bug' },
  { value: 'looks_wrong', label: 'Looks wrong' },
  { value: 'balance', label: 'Balance' },
  { value: 'suggestion', label: 'Suggestion' },
]

/** Must match the server's limit (api/serializers.py, ReportCreateSerializer). */
const MAX_TEXT = 4000

/** How long the "received" note stays by the button. */
const THANKS_MS = 4000

/**
 * The floating **Report a problem** button, on every logged-in screen (#131),
 * and the form it opens over the current screen.
 *
 * The location is captured when the button is pressed, so the report names
 * the screen underneath rather than anything the reporter does afterwards.
 */
export function ReportProblemButton() {
  const { pathname, search } = useLocation()
  const [openedOn, setOpenedOn] = useState<string | null>(null)
  const [thanks, setThanks] = useState(false)
  // The draft lives here, not in the dialog, so closing the form by a stray
  // click on the backdrop or Escape keeps what was typed. Only a successful
  // send clears it.
  const [draft, setDraft] = useState<ReportDraft>(EMPTY_DRAFT)

  useEffect(() => {
    if (!thanks) return
    const timer = window.setTimeout(() => setThanks(false), THANKS_MS)
    return () => window.clearTimeout(timer)
  }, [thanks])

  return (
    <>
      <div
        style={{
          position: 'fixed',
          right: 16,
          bottom: 16,
          zIndex: 60,
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}
      >
        {thanks ? (
          <span
            role="status"
            style={{
              background: color.surface,
              border: `1px solid ${color.border}`,
              borderRadius: radius.md,
              padding: '7px 11px',
              fontSize: 12,
              color: color.positive,
            }}
          >
            Report received — thank you
          </span>
        ) : null}
        <Button
          variant="secondary"
          onClick={() => {
            setThanks(false)
            setOpenedOn(pathname + search)
          }}
          style={{ background: color.surface, boxShadow: '0 2px 8px rgba(20,20,22,.12)' }}
        >
          Report a problem
        </Button>
      </div>
      {openedOn !== null ? (
        <ReportProblemDialog
          location={openedOn}
          draft={draft}
          onDraftChange={setDraft}
          onClose={() => setOpenedOn(null)}
          onSent={() => {
            setOpenedOn(null)
            setDraft(EMPTY_DRAFT)
            setThanks(true)
          }}
        />
      ) : null}
    </>
  )
}

/** What the reporter has typed so far. */
export interface ReportDraft {
  category: ReportCategory
  text: string
}

const EMPTY_DRAFT: ReportDraft = { category: 'bug', text: '' }

export function ReportProblemDialog({
  location,
  draft,
  onDraftChange,
  onClose,
  onSent,
}: {
  location: string
  draft: ReportDraft
  onDraftChange: (draft: ReportDraft) => void
  onClose: () => void
  onSent: () => void
}) {
  const { category, text } = draft
  const setCategory = (value: ReportCategory) => onDraftChange({ ...draft, category: value })
  const setText = (value: string) => onDraftChange({ ...draft, text: value })
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const send = async () => {
    setSending(true)
    setError(null)
    try {
      await createReport(category, text.trim(), location)
      onSent()
    } catch (err) {
      // The text stays where it is, so the reporter can try again.
      setError(err instanceof Error ? err.message : 'The report could not be sent.')
      setSending(false)
    }
  }

  const label = { fontSize: 11, fontFamily: font.mono, color: color.mutedStrong, letterSpacing: '0.5px' }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 70,
        background: 'rgba(20,20,22,.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="report-problem-title"
        onClick={(event) => event.stopPropagation()}
        style={{
          background: color.surface,
          borderRadius: radius.lg,
          border: `1px solid ${color.border}`,
          width: '100%',
          maxWidth: 460,
          padding: 20,
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
          color: color.ink,
        }}
      >
        <div>
          <div id="report-problem-title" style={{ fontSize: 16, fontWeight: 600 }}>
            Report a problem
          </div>
          <div style={{ fontSize: 12, color: color.muted, marginTop: 4 }}>
            Your team, the game week and this screen are attached for you.
          </div>
        </div>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={label}>KIND</span>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value as ReportCategory)}
            style={{ padding: 8, borderRadius: radius.md, border: `1px solid ${color.borderButton}`, fontSize: 13 }}
          >
            {REPORT_CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={label}>WHAT HAPPENED</span>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            maxLength={MAX_TEXT}
            rows={6}
            autoFocus
            style={{
              padding: 8,
              borderRadius: radius.md,
              border: `1px solid ${color.borderButton}`,
              fontSize: 13,
              fontFamily: font.sans,
              resize: 'vertical',
            }}
          />
        </label>

        {error ? (
          <div role="alert" style={{ fontSize: 12, color: color.negative }}>
            {error}
          </div>
        ) : null}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={send} disabled={sending || text.trim() === ''}>
            {sending ? 'Sending…' : 'Send'}
          </Button>
        </div>
      </div>
    </div>
  )
}
