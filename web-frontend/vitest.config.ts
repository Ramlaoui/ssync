import { defineConfig, Plugin } from 'vitest/config';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import path from 'path';

// Custom plugin to force Svelte to use client build in tests
function svelteClientResolver(): Plugin {
  return {
    name: 'svelte-client-resolver',
    enforce: 'pre',
    resolveId(id) {
      // Only apply during tests
      if (!process.env.VITEST) return null;

      // Force main svelte export to use client build
      if (id === 'svelte') {
        return path.resolve(__dirname, './node_modules/svelte/src/index-client.js');
      }
      return null;
    },
  };
}

export default defineConfig({
  plugins: [
    svelteClientResolver(),
    svelte({ hot: !process.env.VITEST })
  ],
  test: {
    globals: true,
    // jsdom is required for Svelte 5 component testing
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{js,ts}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/test/',
        '**/*.d.ts',
        '**/*.config.*',
        '**/mockData',
        'dist/',
      ],
    },
    // Handle WebSocket mocking and async operations
    testTimeout: 15000,
    hookTimeout: 15000,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
