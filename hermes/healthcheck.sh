#!/bin/sh
# Hermes API server health is /health (and /v1/health). Do not probe /healthz.
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8642/health', timeout=3)"
