import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development Vite serves the UI and proxies the API and the event stream to the Hallwise server.
// In production the server serves the built files itself (apps/web/dist).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5188,
    proxy: {
      '/api': 'http://127.0.0.1:8790',
      '/events': { target: 'ws://127.0.0.1:8790', ws: true },
    },
  },
})
