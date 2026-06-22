docker compose `
  -f compose.yaml `
  -f overrides/compose.mariadb.yaml `
  -f overrides/compose.redis.yaml `
  -f overrides/compose.noproxy.yaml `
  --project-name erpnext `
  up -d

Write-Host ""
Write-Host "ERPNext started. Open http://localhost:8080"
