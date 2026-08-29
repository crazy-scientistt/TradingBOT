#!/usr/bin/env python3
"""Probe the local OpenCodex / Hermes / GoldGuard stack.

Never prints tokens, cookies, or authorization headers. Exit 0 only when
GoldGuard is live+ready and OpenCodex answers /healthz. Hermes is reported
but does not fail the process: paper trading still runs without the researcher.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


def _get(url: str, headers: dict[str, str] | None = None, timeout: float = 5.0) -> tuple[int, str]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return int(response.status), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return int(exc.code), body
    except Exception as exc:
        return 0, type(exc).__name__


def _json(body: str) -> dict[str, Any]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify local GoldGuard / OpenCodex / Hermes")
    parser.add_argument("--goldguard-url", default=os.environ.get("GOLDGUARD_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--opencodex-url", default=os.environ.get("OPENCODEX_URL", "http://127.0.0.1:10100"))
    parser.add_argument("--hermes-url", default=os.environ.get("HERMES_URL", "http://127.0.0.1:8642"))
    args = parser.parse_args()

    token = (os.environ.get("OPENCODEX_API_AUTH_TOKEN") or "").strip()
    opencodex_headers = {}
    if token:
        opencodex_headers["x-opencodex-api-key"] = token
        opencodex_headers["authorization"] = f"Bearer {token}"

    results: list[tuple[str, bool, str]] = []

    live_code, live_body = _get(f"{args.goldguard_url.rstrip('/')}/api/health/live")
    live_ok = live_code == 200 and _json(live_body).get("status") == "alive"
    results.append(("goldguard_live", live_ok, f"HTTP_{live_code or 'UNREACHABLE'}"))

    ready_code, ready_body = _get(f"{args.goldguard_url.rstrip('/')}/api/health/ready")
    ready_ok = ready_code == 200 and _json(ready_body).get("status") == "ready"
    results.append(("goldguard_ready", ready_ok, f"HTTP_{ready_code or 'UNREACHABLE'}"))

    ocx_code, _ocx_body = _get(
        f"{args.opencodex_url.rstrip('/')}/healthz", headers=opencodex_headers
    )
    ocx_ok = ocx_code == 200
    results.append(("opencodex_healthz", ocx_ok, f"HTTP_{ocx_code or 'UNREACHABLE'}"))

    hermes_ok = False
    hermes_detail = "UNREACHABLE"
    for path in ("/health", "/v1/health", "/healthz"):
        code, _body = _get(f"{args.hermes_url.rstrip('/')}{path}")
        if code == 200:
            hermes_ok = True
            hermes_detail = f"HTTP_{code}"
            break
        hermes_detail = f"HTTP_{code or 'UNREACHABLE'}"
    results.append(("hermes_health", hermes_ok, hermes_detail))

    diag_code, diag_body = _get(f"{args.goldguard_url.rstrip('/')}/api/diagnostics")
    diag = _json(diag_body).get("data") if diag_code == 200 else {}
    blockers = diag.get("blockers") if isinstance(diag, dict) else None
    results.append(
        (
            "goldguard_diagnostics",
            diag_code == 200,
            f"HTTP_{diag_code or 'UNREACHABLE'} blockers={blockers}",
        )
    )

    catalog_code, catalog_body = _get(f"{args.goldguard_url.rstrip('/')}/api/providers/catalog")
    catalog = _json(catalog_body)
    models = catalog.get("data") if catalog_code == 200 else None
    model_count = len(models) if isinstance(models, list) else 0
    results.append(
        (
            "opencodex_catalog",
            catalog_code == 200,
            f"HTTP_{catalog_code or 'UNREACHABLE'} models={model_count}",
        )
    )

    print("=== GoldGuard local stack ===")
    failed = False
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        if name == "hermes_health" and not ok:
            mark = "WARN"
        print(f"  [{mark}] {name}: {detail}")
        if mark == "FAIL":
            failed = True

    if model_count == 0 and ocx_ok:
        print("  [INFO] OpenCodex is up but listed no models. Add Gemini in http://localhost:10100")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
