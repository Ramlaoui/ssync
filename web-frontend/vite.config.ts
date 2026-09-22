import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import path from 'path'

// Match the ssync CLI's local server. Its generated development certificate is self-signed.
const backendURL = process.env.SSYNC_BACKEND_URL || 'https://localhost:8042'
const localBackend = ['localhost', '127.0.0.1', '[::1]'].includes(new URL(backendURL).hostname)
const backendProxy = { target: backendURL, changeOrigin: true, secure: !localBackend }

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [svelte()],
  resolve: {
    alias: {
      '$lib': path.resolve('./src/lib')
    }
  },
  server: {
    proxy: {
      '/api': { ...backendProxy },
      '/ws': { ...backendProxy, ws: true },
    },
  },
  build: {
    // Enable source maps for production debugging ('hidden' keeps them separate from bundle)
    sourcemap: 'hidden',
    // Disable compressed size reporting for faster builds
    reportCompressedSize: false,
    // Use esbuild for faster minification (default in Vite)
    minify: 'esbuild',
    // Increase chunk size warning limit (informational only, doesn't affect functionality)
    chunkSizeWarningLimit: 2000
  }
})