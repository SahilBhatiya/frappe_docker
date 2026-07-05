# Vercel Deployment

This repo deploys the Vue frontend to Vercel. The Python/Frappe app still needs
to run on a Frappe/ERPNext server; Vercel proxies browser API requests to that
server.

## Project Settings

- Framework Preset: Vite
- Root Directory: repository root
- Install Command: `cd frontend && yarn install --frozen-lockfile`
- Build Command: `cd frontend && yarn build:vercel`
- Output Directory: `frontend/dist`

These values are already defined in `vercel.ts`, so Vercel should pick them up
automatically when the GitHub repo is imported.

## Environment Variables

Set this Vercel environment variable for Production and Preview:

```text
FRAPPE_BACKEND_URL=https://your-frappe-site.example.com
```

Do not include a trailing slash, and do not use `localhost` here. The URL must
be a publicly reachable Frappe/ERPNext site where the POS Prime app is
installed. The proxy also accepts `FRAPPE_TARGET` or `VITE_FRAPPE_BACKEND_URL`
as fallbacks, but `FRAPPE_BACKEND_URL` is preferred.

For authenticated ERPNext/POS calls, also set either:

```text
FRAPPE_TOKEN=api_key:api_secret
```

or:

```text
FRAPPE_API_KEY=your_api_key
FRAPPE_API_SECRET=your_api_secret
```

Without token auth, the backend sees Vercel requests as `Guest` and protected
methods such as `frappe.auth.get_logged_user` return 403.

The frontend calls `/api/method/*` on the Vercel domain. Vercel rewrites those
requests to the static function `api/frappe-proxy.js`, which proxies them to
`FRAPPE_BACKEND_URL`. Other Frappe-owned paths such as `/files`,
`/private`, `/login`, and `/logout` are rewritten by `vercel.ts` when
`FRAPPE_BACKEND_URL` is available at build time.

## Routes

- `/` redirects to `/pos-prime`
- `/pos-prime` and `/pos-prime/*` serve the SPA
- `/api/method/*` is rewritten to `/api/frappe-proxy` and proxied by a Vercel
  function using `FRAPPE_BACKEND_URL`
- `/files`, `/private`, `/login`, and `/logout` are proxied by Vercel rewrites
  when `FRAPPE_BACKEND_URL` is set during deployment
