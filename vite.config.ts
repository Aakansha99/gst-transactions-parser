/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Forward /api/* to the FastAPI backend in dev. The frontend can use
      // relative URLs (`/api/parse`) and stay environment-agnostic.
      // Use 127.0.0.1 (not localhost) because Node 17+ resolves `localhost`
      // to ::1 (IPv6) first, but uvicorn binds to 127.0.0.1 (IPv4) by
      // default — leading to ECONNREFUSED on the IPv6 address.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
  },
})
