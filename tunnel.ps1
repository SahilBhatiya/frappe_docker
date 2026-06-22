# Named Cloudflare Tunnel → erp.adarshtyre.in
# Tunnel ID: 2ac80675-2556-4158-bab2-6225725f7d1d
#
# To get your tunnel TOKEN:
#   1. Go to Cloudflare Zero Trust → Networks → Tunnels
#   2. Click the tunnel → Configure → copy the Docker run command token

$TOKEN = ""   # ← paste your tunnel token here

if (-not $TOKEN) {
    Write-Host "ERROR: Paste your Cloudflare tunnel token into TOKEN variable in tunnel.ps1" -ForegroundColor Red
    Write-Host ""
    Write-Host "Get it from: Cloudflare Zero Trust → Networks → Tunnels → your tunnel → Configure"
    exit 1
}

Write-Host "Starting Cloudflare Tunnel → https://erp.adarshtyre.in ..."
Write-Host "Press Ctrl+C to stop."
Write-Host ""

docker run --rm -it `
  --network erpnext_default `
  cloudflare/cloudflared:latest `
  tunnel --no-autoupdate run --token $TOKEN
