#!/bin/sh
# Railway entrypoint. Bind 0.0.0.0, keep the process in the foreground, and
# never probe `ocx start --help` (that can swallow the healthcheck window).
set -eu

PORT="${PORT:-10100}"
export PORT
export HOME="${HOME:-/app}"
export CI=1
export OPENCODEX_HOME="${OPENCODEX_HOME:-${HOME}/.opencodex}"
mkdir -p "${OPENCODEX_HOME}"
export CONFIG_FILE="${OPENCODEX_HOME}/config.json"

if [ -z "${OPENCODEX_API_AUTH_TOKEN:-}" ]; then
  echo "==============================================" >&2
  echo "FATAL: OPENCODEX_API_AUTH_TOKEN is not set." >&2
  echo "Add it on the opencodex service Variables tab." >&2
  echo "OpenCodex will not bind 0.0.0.0 without it." >&2
  echo "==============================================" >&2
  sleep 8
  exit 1
fi

bun -e '
  const fs = require("fs");
  const path = process.env.CONFIG_FILE;
  const port = Number(process.env.PORT || 10100);
  let cfg = {};
  try { cfg = JSON.parse(fs.readFileSync(path, "utf8")); } catch {}
  if (cfg === null || typeof cfg !== "object" || Array.isArray(cfg)) cfg = {};
  cfg.hostname = "0.0.0.0";
  cfg.port = port;

  const origins = new Set(Array.isArray(cfg.corsAllowOrigins) ? cfg.corsAllowOrigins : []);
  const publicUrl = (process.env.RAILWAY_PUBLIC_DOMAIN || "").trim();
  const staticUrl = (process.env.RAILWAY_STATIC_URL || "").trim();
  const extra = (process.env.OPENCODEX_PUBLIC_ORIGIN || "").trim();
  if (publicUrl) origins.add("https://" + publicUrl.replace(/^https?:\/\//, ""));
  if (staticUrl) origins.add(staticUrl.replace(/\/$/, ""));
  if (extra) origins.add(extra.replace(/\/$/, ""));
  cfg.corsAllowOrigins = [...origins];

  const gemini = (process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || "").trim();
  if (gemini) {
    if (!cfg.providers || typeof cfg.providers !== "object" || Array.isArray(cfg.providers)) cfg.providers = {};
    const existing = cfg.providers.google && typeof cfg.providers.google === "object" ? cfg.providers.google : {};
    cfg.providers.google = {
      ...existing,
      apiKey: existing.apiKey || gemini,
      googleMode: existing.googleMode || "ai-studio",
    };
    if (!cfg.defaultProvider) cfg.defaultProvider = "google";
  }

  fs.writeFileSync(path, JSON.stringify(cfg, null, 2));
  console.log(
    "OpenCodex config",
    path,
    "hostname=0.0.0.0 port=" + port,
    "cors=",
    cfg.corsAllowOrigins.join(","),
    "gemini=",
    gemini ? "set" : "absent",
  );
'

OCX="/app/node_modules/.bin/ocx"
if [ ! -x "${OCX}" ]; then
  echo "FATAL: ${OCX} is missing. bun install did not produce the ocx binary." >&2
  sleep 8
  exit 1
fi

echo "Starting OpenCodex on 0.0.0.0:${PORT}"
exec "${OCX}" start --port "${PORT}"
