#!/bin/sh
# Build and start OpenCodex + Hermes + GoldGuard on localhost.
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$root"

if [ ! -f .env.autonomous ]; then
  sh scripts/bootstrap_local_env.sh
fi

export UI_REVISION="$(git rev-parse --short HEAD 2>/dev/null || echo local)"

docker compose -f docker-compose.local.yml --env-file .env.autonomous up --build --force-recreate -d

echo ""
echo "Local development is paper-only. Live stays disarmed."
echo "  GoldGuard   http://localhost:8000"
echo "  OpenCodex   http://localhost:10100   (add Antigravity / Gemini here)"
echo "  Hermes      http://localhost:8642/health"
echo "  UI revision $UI_REVISION  (hard-refresh the browser; gold chrome means a stale image)"
echo ""
echo "If the desk is still gold: docker compose -f docker-compose.local.yml --env-file .env.autonomous build --no-cache goldguard && docker compose -f docker-compose.local.yml --env-file .env.autonomous up -d"
echo "Then:  python scripts/verify_local_stack.py"
echo "Book:  100 USDT paper · 15m entries · 1h regime · ETH entries off · futures ≤2x"
echo "Do not set GOLDGUARD_MODE=live."
