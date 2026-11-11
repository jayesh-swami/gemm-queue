import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  // The repo's .env, at the repo root.
  const env = loadEnv(mode, '../..', '')

  return {
    plugins: [react()],
    define: {
      // Baked into the bundle on purpose for now: anyone with the page can read it.
      'import.meta.env.VITE_API_KEY': JSON.stringify(env.API_KEY),
    },
    server: {
      // Dev only: forward API calls to uvicorn, so the page and API share an origin.
      // In the built app, FastAPI serves the page itself (see api/main.py).
      proxy: {
        '/jobs': 'http://localhost:8000',
      },
    },
  }
})
