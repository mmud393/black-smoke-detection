import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The browser only talks to same-origin /api and /health; Vite proxies them to
// the API in development so no CORS or credentials leave the dev machine.
const target = process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': target, '/health': target } },
})
