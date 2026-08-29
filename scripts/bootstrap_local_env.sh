#!/bin/sh
# Create .env.autonomous once. Refuses to overwrite.
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
target="$root/.env.autonomous"
if [ -f "$target" ]; then
  echo "Refusing to overwrite existing .env.autonomous." >&2
  exit 1
fi

token() {
  python - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
}

cat > "$target" <<EOF
GOLDGUARD_ENVIRONMENT=development
GOLDGUARD_MODE=paper
GOLDGUARD_DATA_DIR=/data
GOLDGUARD_LIVE_CAPABILITY_ENABLED=false
GOLDGUARD_PAPER_STARTING_BALANCE=100
GOLDGUARD_SESSION_SECRET=$(token)
OPENCODEX_API_AUTH_TOKEN=$(token)
OPENCODEX_ADMIN_AUTH_TOKEN=$(token)
HERMES_BRIDGE_TOKEN=$(token)
GEMINI_API_KEY=
GOOGLE_API_KEY=
BINANCE_API_KEY=
BINANCE_API_SECRET=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOF

echo "created .env.autonomous"
