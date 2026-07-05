import path from 'path'
import { defineConfig, loadEnv, Plugin, ProxyOptions } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import Icons from 'unplugin-icons/vite'

// Dev-only proxy: forward Frappe paths to the running backend and authenticate
// every request with an API token (token auth skips CSRF, so writes work even
// though Vite serves a raw index.html with no {{ csrf_token }}). Reads FRAPPE_*
// from .env.development — Node side only, never exposed to the client bundle.
function buildProxy(target: string, token?: string): Record<string, ProxyOptions> {
  const opts: ProxyOptions = {
    target,
    changeOrigin: true,
    ws: true,
    xfwd: true,
    autoRewrite: true,
    configure: (proxy) => {
      proxy.on('proxyReq', (proxyReq, req) => {
        proxyReq.setHeader('X-Forwarded-Host', req.headers.host || '')
        if (token) {
          proxyReq.setHeader('Authorization', `token ${token}`)
          // Force token authentication and prevent Frappe from evaluating CSRF against a valid session cookie
          proxyReq.removeHeader('cookie')
        }
        console.log(`[Vite Proxy] ${req.method} ${req.url} | Token exists: ${!!token}`)
      })
      proxy.on('proxyRes', (proxyRes, req) => {
        const location = proxyRes.headers['location']
        if (location && typeof location === 'string') {
          try {
            const url = new URL(location)
            if (url.hostname === 'localhost' && url.port === '') {
              url.host = req.headers.host || ''
              proxyRes.headers['location'] = url.toString()
            }
          } catch (e) {
            // Ignore parse errors (relative paths)
          }
        }
      })
    },
  }
  // Frappe-owned paths. Everything else (/, /pos-prime, /src, /@vite, /node_modules)
  // is served by Vite itself.
  return ['/api', '/app', '/files', '/private', '/assets', '/method', '/login', '/logout'].reduce(
    (acc, p) => ((acc[p] = opts), acc),
    {} as Record<string, ProxyOptions>
  )
}

// Inject Frappe context into built HTML.
// Frappe processes www/*.html through Jinja, so {{ }} syntax
// gets replaced with actual values at serve time.
function injectFrappeContext(): Plugin {
  return {
    name: 'inject-frappe-context',
    apply: 'build',
    transformIndexHtml(html) {
      // Fetch user theme + Website Settings via Jinja (www pages don't have desk_theme in context)
      const jinjaBlock = [
        '{%- set _user_theme = (frappe.db.get_value("User", frappe.session.user, "desk_theme") or "Light").lower() -%}',
        '{%- set ws = frappe.get_doc("Website Settings") -%}',
      ].join('\n')

      // Add theme attributes to <html> tag
      html = html.replace(
        '<html lang="en">',
        jinjaBlock + '\n<html lang="en" data-theme-mode="{{ _user_theme }}" data-theme="{{ _user_theme }}">'
      )

      // Inject title + favicon from Website Settings
      html = html.replace(
        '<title>POS Prime</title>',
        [
          '<title>{{ ws.app_name or "POS Prime" }}</title>',
          '  {% if ws.favicon %}<link rel="icon" href="{{ ws.favicon }}">{% endif %}',
        ].join('\n  ')
      )

      // Inject CSRF token + theme auto-detection script
      html = html.replace(
        '</head>',
        [
          '  <script>window.csrf_token = "{{ frappe.session.csrf_token }}";</script>',
          '  <script>',
          '    (function() {',
          '      var m = document.documentElement.getAttribute("data-theme-mode");',
          '      if (m === "automatic") {',
          '        var q = window.matchMedia("(prefers-color-scheme: dark)");',
          '        document.documentElement.setAttribute("data-theme", q.matches ? "dark" : "light");',
          '        q.addEventListener("change", function(e) {',
          '          document.documentElement.setAttribute("data-theme", e.matches ? "dark" : "light");',
          '        });',
          '      }',
          '    })();',
          '  </script>',
          '  </head>',
        ].join('\n')
      )

      // Redirect core POS routes to desk page; keep standalone for display/kiosk/customers
      // Uses desk_prefix from www/pos_prime.py context (v16+ = /desk, v14-v15 = /app)
      html = html.replace(
        '<div id="app">',
        [
          '<script>',
          '  (function() {',
          '    var p = window.location.pathname.replace(/\\/$/, "");',
          '    var standalone = ["/pos-prime/display", "/pos-prime/kiosk", "/pos-prime/customers"];',
          '    var isStandalone = standalone.some(function(s) { return p.startsWith(s); });',
          '    if (!isStandalone && p.startsWith("/pos-prime")) {',
          '      window.location.replace("{{ desk_prefix }}/pos-terminal");',
          '      return;',
          '    }',
          '  })();',
          '</script>',
          '<div id="app">',
        ].join('\n  ')
      )

      return html
    },
  }
}

import fs from 'fs'

export default defineConfig(({ mode }) => {
  // Load FRAPPE_* (no VITE_ prefix => stays server-side, never bundled).
  const env = loadEnv(mode, path.resolve(__dirname), '')
  const isVercelBuild = mode === 'vercel' || env.VERCEL === '1' || env.VITE_DEPLOY_TARGET === 'vercel'
  const envPath = path.resolve(__dirname, '.env.development')
  
  let customToken = ''
  let customTarget = ''
  if (fs.existsSync(envPath)) {
    const content = fs.readFileSync(envPath, 'utf-8')
    const tokenMatch = content.match(/^FRAPPE_TOKEN=(.*)$/m)
    if (tokenMatch) customToken = tokenMatch[1].trim()
    const targetMatch = content.match(/^FRAPPE_TARGET=(.*)$/m)
    if (targetMatch) customTarget = targetMatch[1].trim()
  }

  const target = customTarget || env.FRAPPE_TARGET || 'http://localhost:8080'
  const token = customToken || env.FRAPPE_TOKEN

  return {
    plugins: [
      ...(!isVercelBuild
        ? [
            frappeui({
              // The custom proxy below handles Frappe routes and token authentication.
              frappeProxy: false,
              buildConfig: {
                indexHtmlPath: path.resolve(
                  __dirname,
                  '../pos_prime/www/pos_prime.html'
                ),
              },
            }),
          ]
        : []),
      vue(),
      Icons({
        autoInstall: false,
        compiler: 'vue3',
      }),
      ...(!isVercelBuild ? [injectFrappeContext()] : []),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    build: {
      manifest: !isVercelBuild,
      outDir: isVercelBuild ? 'dist' : undefined,
      emptyOutDir: true,
    },
    optimizeDeps: {
      // frappe-ui contains virtual ~icons imports that must be handled by its
      // Vite plugins instead of esbuild's dependency pre-bundler.
      exclude: ['frappe-ui'],
      include: [
        'feather-icons',
        'engine.io-client',
        'debug',
        // grid-layout-plus (used by frappe-ui) and its CJS/UMD dep interactjs must be
        // pre-bundled as ONE optimized graph, otherwise grid-layout-plus is served as
        // raw .mjs and its interactjs import (a UMD bundle with no ESM `default`) breaks,
        // plus its dep-hashes go stale across re-optimizations. Including the package
        // bundles grid-item + interactjs + @vexip-ui/utils together, consistently.
        'grid-layout-plus',
        'grid-layout-plus > interactjs',
        'interactjs',
        // reka-ui (shadcn-vue's headless primitives) MUST be pre-bundled as a
        // single instance. Otherwise Vite serves it via two module graphs and
        // the Dialog's provide/inject context breaks: DialogContent can't read
        // DialogRoot's `open`, so `open=true` renders nothing. Including it (and
        // its @vueuse/core dep) forces one consistent copy.
        'reka-ui',
        '@vueuse/core',
      ],
    },
    // Dev server only — open http://localhost:8081/pos-prime (the /pos-prime base
    // is required for the SPA to mount in standalone mode, see src/main.ts).
    server: {
      port: 8081,
      strictPort: false,
      proxy: buildProxy(target, env.FRAPPE_TOKEN),
    },
  }
})
