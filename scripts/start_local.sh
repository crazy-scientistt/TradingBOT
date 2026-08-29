#!/bin/sh
# Build and start OpenCodex + Hermes + GoldGuard on localhost.
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$root"

if [ ! -f .env.autonomous ]; then
  sh scripts/bootstrap_local_env.sh
fi

docker compose -f docker-compose.local.yml --env-file .env.autonomous up --build -d

echo "GoldGuard  http://localhost:8000"
echo "OpenCodex  http://localhost:10100"
echo "Hermes     http://localhost:8642/health"
echo "Verify     python scripts/verify_local_stack.py"
