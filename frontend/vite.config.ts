import { loadEnv, type Plugin } from 'vite'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

/** Social-media crawlers and search engines need absolute addresses for the canonical link and the share image.
 *  When PUBLIC_URL is set (in the environment or in the repository's .env) at build time it fills them in; otherwise those
 *  tags are left out, because a wrong or relative address is worse than none. PUBLIC_URL is only read here; it is not added to the bundle. */
function siteUrl(mode: string): Plugin {
  // loadEnv reads the repository's .env (one level up; Vite runs from frontend/) and any PUBLIC_URL already in the environment
  const fromEnv = loadEnv(mode, '..', ['PUBLIC_URL']).PUBLIC_URL ?? ''
  const base = /^https?:\/\/[^\s"'<>]+$/.test(fromEnv) ? fromEnv.replace(/\/+$/, '') : ''
  return {
    name: 'swara-site-url',
    transformIndexHtml(html) {
      if (base) return html.replaceAll('__SITE_URL__', base)
      return html.replace(/[ \t]*<!-- site-url:start[\s\S]*?<!-- site-url:end -->\r?\n?/, '')
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), siteUrl(mode)],
  server: {
    port: 5173,
    // Tests (mode 'test') may read the repository's eval/results file to check the page against the real data; the dev server never gets this.
    fs: mode === 'test' ? { allow: ['..'] } : undefined,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      // the API reference page (served by the backend, not part of the React app)
      '/docs': 'http://127.0.0.1:8000',
      '/openapi.json': 'http://127.0.0.1:8000',
      '/api-reference.js': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  build: { chunkSizeWarningLimit: 1000 },
  test: { environment: 'jsdom', globals: true, setupFiles: './src/test/setup.ts', css: false },
}))
