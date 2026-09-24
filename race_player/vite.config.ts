import { readdirSync, statSync } from 'node:fs'
import { resolve, join } from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, type Plugin } from 'vite'

// Local dev-only endpoint listing the .jsonl.br race files in public/ so the
// file-explorer sidebar can discover them. Excluded from the built app.
function raceListing(): Plugin {
  return {
    name: 'race-file-listing',
    configureServer(server) {
      server.middlewares.use('/api/races', (_req, res) => {
        const dir = resolve(process.cwd(), 'public')
        let files: { name: string; mtime: string }[] = []
        try {
          files = readdirSync(dir)
            .filter((f) => f.endsWith('.jsonl.br'))
            .sort()
            .map((name) => ({
              name,
              mtime: statSync(join(dir, name)).mtime.toISOString(),
            }))
        } catch {
          // public dir missing -> empty list
        }
        res.setHeader('Content-Type', 'application/json')
        res.end(JSON.stringify({ files }))
      })
      // Load-bearing: the fetch for a .jsonl.br log must come down decoded.
      // Sirv stamps Content-Encoding: br when serving such a file, but the
      // header is set on every response path so the browser never hands the
      // player raw compressed bytes.
      server.middlewares.use((req, res, next) => {
        if (req.url?.endsWith('.jsonl.br')) res.setHeader('Content-Encoding', 'br')
        next()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), raceListing()],
})
