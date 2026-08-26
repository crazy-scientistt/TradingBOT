import sys
import urllib.request

endpoints = [
    "/api/health",
    "/api/status",
    "/api/kpi",
    "/api/market/quote",
    "/api/market/candles?limit=5",
    "/api/position",
    "/api/equity",
    "/api/context",
    "/api/genomes",
    "/api/quota",
    "/api/providers",
    "/api/routes",
    "/api/bot/state",
    "/",
]

failed = 0
for ep in endpoints:
    url = f"http://localhost:8000{ep}"
    try:
        req = urllib.request.urlopen(url, timeout=5)
        status = req.status
        content_type = req.headers.get("Content-Type", "")
        data = req.read()
        print(f"[PASS] {ep:30} -> {status} ({len(data)} bytes, {content_type.split(';')[0]})")
    except Exception as e:
        print(f"[FAIL] {ep:30} -> {e}")
        failed += 1

if failed > 0:
    print(f"\n{failed} endpoints failed!")
    sys.exit(1)
else:
    print("\nALL 14 ENDPOINTS & STATIC SPA ROOT VERIFIED 100% OPERATIONAL!")
