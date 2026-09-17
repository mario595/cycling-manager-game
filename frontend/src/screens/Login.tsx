import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'

import { Button, Card, PageBody, PageHeading } from '../components/primitives'
import { color, font } from '../theme'
import { useAuth } from '../useAuth'

export function Login() {
  const { me, loading, login } = useAuth()
  const location = useLocation()
  // The route guard's `<Navigate state={{ from: pathname }} />` lands here
  // when a visitor tried to reach a guarded page before logging in. Location
  // state is in-memory, so no validation is needed — only the guard can have
  // set it. Someone who asks for /login directly has no `from` and goes home.
  const from = (location.state as { from?: string } | null)?.from
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (loading) return null
  if (me?.authenticated) {
    // A manager with no team still goes to /claim regardless of `from` — the
    // layout's team guard would bounce them there anyway.
    return <Navigate to={me.team ? (from ?? '/') : '/claim'} replace />
  }

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not log in.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PageBody gap={18} paddingTop={26}>
      <PageHeading eyebrow="WELCOME BACK" title="Log in" subtitle="Manage your team." titleSize={29} />

      <Card style={{ padding: '20px 22px', maxWidth: 380, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Field label="Email">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={inputStyle}
          />
        </Field>
        <Field label="Password">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void submit()}
            style={inputStyle}
          />
        </Field>

        {error ? <div style={{ fontSize: 12.5, color: color.negative }}>{error}</div> : null}

        <Button
          variant="primary"
          onClick={() => void submit()}
          style={{
            width: '100%',
            opacity: submitting ? 0.6 : 1,
            cursor: submitting ? 'not-allowed' : 'pointer',
          }}
        >
          {submitting ? 'Logging in…' : 'Log in'}
        </Button>

        <div style={{ fontSize: 12.5, color: color.muted }}>
          No account yet? <Link to="/register" style={{ color: color.accentInk }}>Register</Link>
        </div>
      </Card>
    </PageBody>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <span style={{ fontSize: 10, letterSpacing: '1px', color: color.mutedStrong, fontFamily: font.mono }}>
        {label.toUpperCase()}
      </span>
      {children}
    </label>
  )
}

const inputStyle: CSSProperties = {
  fontSize: 13.5,
  padding: '9px 11px',
  borderRadius: 8,
  border: `1px solid ${color.borderButton}`,
  background: color.surface,
  fontFamily: font.sans,
}
