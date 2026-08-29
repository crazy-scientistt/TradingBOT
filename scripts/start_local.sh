#!/bin/sh
# Build and start OpenCodex + Hermes + GoldGuard on localhost.
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$root"

if [ ! -f .env.autonomous ]; then
  sh scripts/bootstrap_local_env.sh
fi

docker compose -f docker-compose.local.yml --env-file .env.autonomous up --build -d

echo ""
echo "Local development is paper-only. Live stays disarmed."
echo "  GoldGuard   http://localhost:8000"
echo "  OpenCodex   http://localhost:10100   (add Antigravity / Gemini here)"
echo "  Hermes      http://localhost:8642/health"
echo ""
echo "Then:  python scripts/verify_local_stack.py"
echo "Book:  100 USDT paper · 15m entries · 1h regime · ETH entries off · futures ≤2x"
echo "Do not set GOLDGUARD_MODE=live."
