#!/bin/bash
docker compose --project-name erpnext down
echo "ERPNext stopped. Data is preserved in Docker volumes."
