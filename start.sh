#!/bin/bash
# Start ERPNext stack (run once to boot all services)
set -e

echo "==> Starting ERPNext stack..."
docker compose \
  -f compose.yaml \
  -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml \
  -f overrides/compose.noproxy.yaml \
  --project-name erpnext \
  up -d

echo ""
echo "==> Waiting for services to be healthy (may take 1-2 min on first run)..."
docker compose --project-name erpnext wait configurator 2>/dev/null || true
sleep 10

echo ""
echo "==> Services running:"
docker compose --project-name erpnext ps
echo ""
echo "ERPNext is reachable at: http://localhost:8080"
echo "Next step: run ./create-site.sh to create your first site."
