const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'content-encoding',
  'content-length',
  'host',
  'transfer-encoding',
])

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    req.on('data', (chunk) => chunks.push(chunk))
    req.on('end', () => resolve(Buffer.concat(chunks)))
    req.on('error', reject)
  })
}

function getBackendUrl() {
  return (
    process.env.FRAPPE_BACKEND_URL ||
    process.env.FRAPPE_TARGET ||
    process.env.VITE_FRAPPE_BACKEND_URL ||
    ''
  ).replace(/\/$/, '')
}

function getFrappeToken() {
  if (process.env.FRAPPE_TOKEN) return process.env.FRAPPE_TOKEN
  if (process.env.FRAPPE_API_KEY && process.env.FRAPPE_API_SECRET) {
    return `${process.env.FRAPPE_API_KEY}:${process.env.FRAPPE_API_SECRET}`
  }
  return ''
}

export default async function handler(req, res) {
  const backendUrl = getBackendUrl()
  if (!backendUrl) {
    res.status(500).json({
      error: 'FRAPPE_BACKEND_URL is not configured on Vercel',
    })
    return
  }

  let backendHost
  try {
    backendHost = new URL(backendUrl).host
  } catch {
    res.status(500).json({
      error: 'FRAPPE_BACKEND_URL must be an absolute URL, for example https://erp.example.com',
      value: backendUrl,
    })
    return
  }

  const rawPath = req.query?.path || ''
  const methodPath = Array.isArray(rawPath) ? rawPath.join('/') : rawPath
  const passthroughQuery = new URLSearchParams()
  for (const [key, value] of Object.entries(req.query || {})) {
    if (key === 'path') continue
    const values = Array.isArray(value) ? value : [value]
    for (const entry of values) passthroughQuery.append(key, entry)
  }
  const query = passthroughQuery.toString() ? `?${passthroughQuery}` : ''
  const upstreamUrl = `${backendUrl}/api/method/${methodPath}${query}`
  const headers = { ...req.headers, host: backendHost }
  for (const header of HOP_BY_HOP_HEADERS) {
    delete headers[header]
  }
  const frappeToken = getFrappeToken()
  if (frappeToken) {
    headers.authorization = `token ${frappeToken}`
    delete headers.cookie
  }
  headers['x-frappe-site-name'] = backendHost

  let upstream
  try {
    upstream = await fetch(upstreamUrl, {
      method: req.method,
      headers,
      body: req.method === 'GET' || req.method === 'HEAD' ? undefined : await readBody(req),
      redirect: 'manual',
    })
  } catch (error) {
    res.status(502).json({
      error: 'Could not reach the Frappe backend from Vercel',
      backendUrl,
      detail: error instanceof Error ? error.message : String(error),
    })
    return
  }

  res.status(upstream.status)
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key)) {
      res.setHeader(key, value)
    }
  })

  const setCookies = upstream.headers.getSetCookie?.()
  if (setCookies?.length) {
    res.setHeader('set-cookie', setCookies)
  }

  res.send(Buffer.from(await upstream.arrayBuffer()))
}
