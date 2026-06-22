#!/bin/bash
# Run once after `start.sh` to create the ERPNext site and install apps.
# Usage: ./create-site.sh [site-name]   (default: erpnext.localhost)
set -e

SITE=${1:-erpnext.localhost}
DB_PASS=$(grep DB_PASSWORD .env | cut -d= -f2)

echo "==> Creating site: $SITE"
docker compose --project-name erpnext exec backend \
  bench new-site "$SITE" \
    --mariadb-root-password "$DB_PASS" \
    --admin-password admin@123 \
    --no-mariadb-socket

echo ""
echo "==> Installing ERPNext on $SITE ..."
docker compose --project-name erpnext exec backend \
  bench --site "$SITE" install-app erpnext

echo ""
echo "==> Setting site as default..."
docker compose --project-name erpnext exec backend \
  bench --site "$SITE" set-config host_name "http://$SITE"

echo ""
echo "Done! Open http://localhost:8080 (login: Administrator / admin@123)"
