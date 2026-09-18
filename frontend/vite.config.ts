import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

import { djangoPort } from './worktree.ts'

// This config file lives at <checkout>/frontend/vite.config.ts, so its
// directory's parent is the checkout root — the same REPO_ROOT
// config/worktree.py computes from config/worktree.py's own location.
const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')

// The build lands in `dist/`, which Django picks up two ways at once
// (see config/settings/base.py):
//
//   TEMPLATES["DIRS"]  -> renders dist/index.html for the SPA catch-all
//   STATICFILES_DIRS   -> WhiteNoise serves dist/assets/* under /static/
//
// `base` therefore has to be '/static/' so the asset URLs Vite writes into
// index.html match where WhiteNoise actually serves them from. In `vite dev`
// there is no Django and no /static/ prefix, so it stays '/' there.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/static/' : '/',
  plugins: [react()],
  // The course profile is imported from race_player/src across packages; that
  // code resolves 'react' within race_player/node_modules unless we force it
  // back to the frontend's copy, and two Reacts in one tree break hooks.
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
  },
  server: {
    // race_player already owns 5173, so default elsewhere. PORT wins when set,
    // which is how the tooling assigns a free port.
    port: Number(process.env.PORT) || 5174,
    // Anything the SPA cannot answer goes to Django, so the dev server can
    // be used against the real backend once the API exists. djangoPort
    // mirrors config/worktree.py's runserver_port() — each worktree's
    // Django runs on its own port, and this proxy has to follow it there;
    // the main checkout still gets the default, :8000.
    proxy: {
      '/api': `http://127.0.0.1:${djangoPort(repoRoot)}`,
      '/admin': `http://127.0.0.1:${djangoPort(repoRoot)}`,
    },
  },
}))
