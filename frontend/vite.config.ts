import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

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
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    // race_player already owns 5173, so default elsewhere. PORT wins when set,
    // which is how the tooling assigns a free port.
    port: Number(process.env.PORT) || 5174,
    // Anything the SPA cannot answer goes to Django on :8000, so the dev
    // server can be used against the real backend once the API exists.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/admin': 'http://127.0.0.1:8000',
    },
  },
}))
