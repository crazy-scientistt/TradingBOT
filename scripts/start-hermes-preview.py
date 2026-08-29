#!/usr/bin/env python3
"""Preview Hermes bridge: /health plus OpenAI-compatible chat via OpenCodex Antigravity."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OCX = os.environ.get("OPENCODEX_BASE_URL", "http://127.0.0.1:10100").rstrip("/")
MODEL = os.environ.get("HERMES_MODEL", "google-antigravity/gemini-3.7-flash")
HOST = os.environ.get("HERMES_HOST", "0.0.0.0")
PORT = int(os.environ.get("HERMES_PORT", "8642"))
SOUL = "/workspace/TradingBOT/hermes/SOUL.md"
TOKEN_FILE = "/workspace/.opencodex-runtime/token"


def data_token() -> str:
    try:
        return open(TOKEN_FILE, encoding="utf-8").read().strip()
    except OSError:
        return (os.environ.get("OPENCODEX_API_AUTH_TOKEN") or "").strip()


def soul() -> str:
    try:
        return open(SOUL, encoding="utf-8").read()
    except OSError:
        return "You are an isolated trading-research analyst. Return strict JSON proposals only."


def ocx_chat(payload: dict) -> tuple[int, dict]:
    token = data_token()
    if not token:
        return 503, {"error": {"message": "OpenCodex data token missing", "type": "unavailable"}}
    messages = list(payload.get("messages") or [])
    if not any(isinstance(m, dict) and m.get("role") == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": soul()})
    body = {
        "model": payload.get("model") or MODEL,
        "messages": messages,
        "temperature": payload.get("temperature", 0),
        "max_tokens": payload.get("max_tokens", 512),
        "reasoning_effort": payload.get("reasoning_effort", "high"),
    }
    req = urllib.request.Request(
        f"{OCX}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "authorization": f"Bearer {token}",
            "x-opencodex-api-key": token,
            "content-type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as err:
        raw = err.read().decode()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"error": {"message": raw[:400], "type": "upstream"}}
        return err.code, parsed
    except Exception as err:  # noqa: BLE001 — preview bridge fail-closed
        return 503, {"error": {"message": str(err), "type": "unavailable"}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _send(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.send_header("access-control-allow-origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-headers", "authorization, content-type, x-opencodex-api-key")
        self.send_header("access-control-allow-methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] in {"/health", "/v1/health", "/healthz"}:
            self._send(
                200,
                {
                    "status": "ok",
                    "service": "hermes-preview",
                    "model": MODEL,
                    "route": "google-antigravity",
                },
            )
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/v1/chat/completions":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("content-length") or "0")
        if length > 64_000:
            self._send(413, {"error": {"message": "payload too large"}})
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode())
            if not isinstance(payload, dict):
                raise ValueError("body")
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            self._send(400, {"error": {"message": "invalid json"}})
            return
        code, body = ocx_chat(payload)
        self._send(code, body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
