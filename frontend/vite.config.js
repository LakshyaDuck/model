import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import mkcert from 'vite-plugin-mkcert'
import { defineConfig } from 'vite'

// Backend dev ports (mirror backend/scripts/dev.py defaults).
const API_PORT = process.env.API_PORT || '8000'
const TUSD_PORT = process.env.TUSD_PORT || '1080'
const API_TARGET = `http://127.0.0.1:${API_PORT}`
const TUSD_TARGET = `http://127.0.0.1:${TUSD_PORT}`

// HTTPS is opt-in: it needs sudo to trust a local CA, and getUserMedia only needs
// it for the in-page camera. The default (HTTP) works everywhere; capture on the
// phone goes through a file input instead. Enable with `HTTPS=1 npm run dev`.
const useHttps = process.env.HTTPS === '1'

// tusd must mint upload URLs (Location) on the origin the phone actually sees, not
// on 127.0.0.1:1080. It honours these only when started with -behind-proxy (dev.py
// does that), and it keeps the original Host because changeOrigin stays false.
function forwardProxyHeaders(proxy) {
  proxy.on('proxyReq', (proxyReq, req) => {
    const proto = req.socket && req.socket.encrypted ? 'https' : 'http'
    proxyReq.setHeader('X-Forwarded-Proto', proto)
    if (req.headers.host) proxyReq.setHeader('X-Forwarded-Host', req.headers.host)
  })
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), ...(useHttps ? [mkcert()] : [])],
  server: {
    host: true,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: false },
      '/files': { target: TUSD_TARGET, changeOrigin: false, configure: forwardProxyHeaders },
    },
  },
})
