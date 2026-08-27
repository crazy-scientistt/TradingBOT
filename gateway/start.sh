#!/bin/sh
# Railway/OpenCodex entrypoint. Binds 0.0.0.0 so the bot can reach it on the
# private network. Never overwrites saved providers — only ensures hostname/port.
set -eu

PORT="${PORT:-10100}"
export HOME="${HOME:-/app}"
CONFIG_DIR="${HOME}/.opencodex"
export CONFIG_FILE="${CONFIG_DIR}/config.json"
export PORT

if [ -z "${OPENCODEX_API_AUTH_TOKEN:-}" ]; then
  echo "OPENCODEX_API_AUTH_TOKEN is required. OpenCodex refuses 0.0.0.0 without it." >&2
  exit 1
fi

mkdir -p "${CONFIG_DIR}"

bun -e '
  const fs = require("fs");
  const path = process.env.CONFIG_FILE;
  const port = Number(process.env.PORT || 10100);
  let cfg = {};
  try { cfg = JSON.parse(fs.readFileSync(path, "utf8")); } catch {}
  if (cfg === null || typeof cfg !== "object" || Array.isArray(cfg)) cfg = {};
  cfg.hostname = "0.0.0.0";
  cfg.port = port;
  fs.writeFileSync(path, JSON.stringify(cfg, null, 2));
  console.log("OpenCodex config ready at", path, "port", port);
'

echo "Starting OpenCodex on 0.0.0.0:${PORT}"
if bun x ocx start --help >/dev/null 2>&1; then
  exec bun x ocx start --port "${PORT}"
fi
exec bun x opencodex --port "${PORT}"
