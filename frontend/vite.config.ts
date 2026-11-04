import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The voice backend (uv run python -m shant.voice.pipeline -t webrtc) listens on 7860.
// In development the app forwards its API calls there, so everything is one origin.
const backend = 'http://localhost:7860'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/scenarios': backend,
      '/start': backend,
      '/sessions': backend,
      '/reports': backend,
      '/health': backend,
    },
  },
})
