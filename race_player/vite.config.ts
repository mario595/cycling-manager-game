import { readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, type Plugin } from 'vite'

// Local dev-only endpoint listing the .jsonl race files in public/ so the
// file-explorer sidebar can discover them. Excluded from the built app.
function raceListing(): Plugin {
  return {
    name: 'race-file-listing',
    configureServer(server) {
      server.middlewares.use('/api/races', (_req, res) => {
        const dir = resolve(process.cwd(), 'public')
        let files: string[] = []
        try {
          files = readdirSync(dir)
            .filter((f) => f.endsWith('.jsonl'))
            .sort()
        } catch {
          // public dir missing -> empty list
        }
        res.setHeader('Content-Type', 'application/json')
        res.end(JSON.stringify({ files }))
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), raceListing()],
})
