const backendUrl = (process.env.FRAPPE_BACKEND_URL || '').replace(/\/$/, '')

const backendRewrites = backendUrl
  ? [
      { source: '/method/:path*', destination: `${backendUrl}/method/:path*` },
      { source: '/files/:path*', destination: `${backendUrl}/files/:path*` },
      { source: '/private/:path*', destination: `${backendUrl}/private/:path*` },
      { source: '/login', destination: `${backendUrl}/login` },
      { source: '/logout', destination: `${backendUrl}/logout` },
    ]
  : []

export const config = {
  framework: 'vite',
  installCommand: 'cd frontend && yarn install --frozen-lockfile',
  buildCommand: 'cd frontend && yarn build:vercel',
  outputDirectory: 'frontend/dist',
  redirects: [{ source: '/', destination: '/pos-prime', permanent: false }],
  rewrites: [
    { source: '/api/method/:path*', destination: '/api/frappe-proxy?path=:path*' },
    ...backendRewrites,
    { source: '/pos-prime/:path*', destination: '/index.html' },
  ],
}
