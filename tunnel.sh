#!/bin/bash
# Expose ERPNext to the internet via Cloudflare Quick Tunnel (no account needed).
# For a permanent URL, sign up at dash.cloudflare.com and use a named tunnel instead.
echo "==> Starting Cloudflare Quick Tunnel on port 8080..."
echo "    You will get a temporary public URL like: https://xxxx.trycloudflare.com"
echo "    Press Ctrl+C to stop."
echo ""
docker run --rm -it --network erpnext_default cloudflare/cloudflared:latest \
  tunnel --url http://frontend:8080
