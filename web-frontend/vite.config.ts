import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [svelte()],
  resolve: {
    alias: {
      '$lib': path.resolve('./src/lib')
    }
  },
  build: {
    // Disable compressed size reporting for faster builds
    reportCompressedSize: false,
    // Use esbuild for faster minification (default in Vite)
    minify: 'esbuild',
    // Increase chunk size warning limit (informational only, doesn't affect functionality)
    chunkSizeWarningLimit: 2000
  }
})