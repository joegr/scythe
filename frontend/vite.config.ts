import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Relative asset paths + hash routing: the build works at any Pages path (/scythe/ or a root domain).
  base: './',
  // Topics are bundled from backend/scythe/data/nsda_topics.json (one source of truth).
  server: { port: 5173, fs: { allow: ['..'] } },
  preview: { port: 4173 },
})
