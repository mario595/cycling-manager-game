/**
 * The Django dev-server port this checkout should proxy to.
 *
 * Mirrors `config/worktree.py`'s `runserver_port()` exactly — same worktree
 * detection (a checkout is a worktree when its parent directory is named
 * `worktrees`), same slug rule, same sha256-derived port. Kept here rather
 * than shelling out to the Python script so `vite` starts with no
 * dependency on a venv being on PATH; the two must be kept in sync by hand,
 * but the derivation is small and not expected to change.
 *
 * The main checkout (not a worktree) gets `null`, meaning "use the default
 * port, 8000" — see `config/worktree.py`, which does the same.
 */

import { createHash } from 'node:crypto'
import { basename, dirname } from 'node:path'

const PORT_BASE = 8000
const PORT_SPAN = 1000

function worktreeSlug(repoRoot: string): string | null {
  if (basename(dirname(repoRoot)) !== 'worktrees') return null
  const slug = basename(repoRoot)
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return slug || null
}

export function djangoPort(repoRoot: string): number {
  const slug = worktreeSlug(repoRoot)
  if (slug === null) return PORT_BASE
  const digest = createHash('sha256').update(slug).digest()
  return PORT_BASE + (digest.readUInt16BE(0) % PORT_SPAN)
}
