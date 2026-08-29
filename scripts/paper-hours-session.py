#!/usr/bin/env python3
"""Replay the last 6 hours of public 1m candles across PAXG/BTC/ETH/SOL on a $100 paper book."""
from __future__ import annotations

import json
import math
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("/workspace/artifacts/paper-hours-session.json")
HERMES = "http://127.0.0.1:8642/v1/chat/completions"
VISION = "https://data-api.binance.vision/api/v3/klines"

UNIVERSE = [
    {"id": "PAXGUSDT", "product": "SPOT", "step": 0.0001},
    {"id": "BTCUSDT", "product": "FUTURES", "step": 0.00001},
    {"id": "ETHUSDT", "product": "FUTURES", "step": 0.0001},
    {"id": "SOLUSDT", "product": "FUTURES", "step": 0.01},
]
HOURS = 6
LIMIT = HOURS * 60
STARTING = 100.0
FEE = 0.0005
SLIP = 0.0002
RISK = 0.01
MAX_EXP = 0.2
MIN_NOTIONAL = 5.0
ATR_STOP = 1.6
ATR_TP = 2.4
MIN_STOP = 0.0015
MAX_LEV = 5
MAINT = 0.004


def klines(symbol: str) -> list[dict]:
    url = f"{VISION}?symbol={symbol}&interval=1m&limit={LIMIT}"
    with urllib.request.urlopen(url, timeout=12) as res:
        raw = json.loads(res.read().decode())
    return [
        {"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]), "v": float(r[5])}
        for r in raw
    ]


def ema(xs: list[float], p: int) -> list[float]:
    k = 2 / (p + 1)
    e = xs[0]
    out = []
    for x in xs:
        e = x * k + e * (1 - k)
        out.append(e)
    return out


def rsi(xs: list[float], p: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    ag = al = None
    for i in range(1, len(xs)):
        d = xs[i] - xs[i - 1]
        g, l = max(d, 0.0), max(-d, 0.0)
        if i < p:
            continue
        if i == p:
            gs = sum(max(xs[j] - xs[j - 1], 0.0) for j in range(1, p + 1))
            ls = sum(max(xs[j - 1] - xs[j], 0.0) for j in range(1, p + 1))
            ag, al = gs / p, ls / p
        else:
            ag = (ag * (p - 1) + g) / p
            al = (al * (p - 1) + l) / p
        rs = ag / al if al else 99
        out[i] = 100 - 100 / (1 + rs)
    return out


def atr(cs: list[dict], p: int = 14) -> list[float]:
    trs = []
    for i, c in enumerate(cs):
        if i == 0:
            trs.append(c["h"] - c["l"])
        else:
            trs.append(max(c["h"] - c["l"], abs(c["h"] - cs[i - 1]["c"]), abs(c["l"] - cs[i - 1]["c"])))
    return ema(trs, p)


def floor_qty(q: float, step: float) -> float:
    if q <= 0 or step <= 0:
        return 0.0
    return math.floor((q + 1e-12) / step) * step


def choose_lev(product: str, a: float, px: float) -> int:
    if product != "FUTURES":
        return 1
    pct = a / px
    if pct < 0.003:
        picked = 4
    elif pct < 0.006:
        picked = 3
    elif pct < 0.012:
        picked = 2
    else:
        picked = 1
    return min(picked, MAX_LEV)


def liq_px(side: str, entry: float, lev: int) -> float:
    room = max(0.05, 1 / lev - MAINT * 1.2)
    return entry * (1 - room) if side == "LONG" else entry * (1 + room)


def features(cs: list[dict]) -> dict:
    closes = [c["c"] for c in cs]
    return {"fast": ema(closes, 12), "slow": ema(closes, 26), "rsi": rsi(closes), "atr": atr(cs)}


def setup(product: str, c: dict, i: int, f: dict) -> str | None:
    fast, slow, r, a = f["fast"][i], f["slow"][i], f["rsi"][i], f["atr"][i]
    if r is None or a <= 0:
        return None
    if fast > slow and 36 < r < 74 and c["c"] <= fast * 1.006 and c["c"] >= slow * 0.997:
        return "LONG"
    if product == "FUTURES" and fast < slow and 26 < r < 64 and c["c"] >= fast * 0.994 and c["c"] <= slow * 1.003:
        return "SHORT"
    return None


def run() -> dict:
    books = {}
    for u in UNIVERSE:
        cs = klines(u["id"])
        books[u["id"]] = {**u, "candles": cs, "feat": features(cs)}
    cash = STARTING
    pos = None
    trades = []
    holds = 0
    entries = 0
    peak = STARTING
    equity = STARTING
    # Align on overlapping timestamps
    times = sorted(set.intersection(*[set(c["t"] for c in b["candles"]) for b in books.values()]))
    times = times[-LIMIT:]
    for ts in times:
        # manage
        if pos:
            b = books[pos["symbol"]]
            c = next((x for x in b["candles"] if x["t"] == ts), None)
            if c:
                exit_px = None
                reason = None
                if pos["side"] == "SHORT":
                    if c["h"] >= pos["stop"]:
                        exit_px, reason = pos["stop"], "STOP_LOSS"
                    elif c["l"] <= pos["take"]:
                        exit_px, reason = pos["take"], "TAKE_PROFIT"
                else:
                    if c["l"] <= pos["stop"]:
                        exit_px, reason = pos["stop"], "STOP_LOSS"
                    elif c["h"] >= pos["take"]:
                        exit_px, reason = pos["take"], "TAKE_PROFIT"
                if exit_px is not None:
                    px = exit_px * (1 - SLIP if pos["side"] == "LONG" else 1 + SLIP)
                    fee = pos["qty"] * px * FEE
                    gross = (px - pos["entry"]) * pos["qty"] if pos["side"] == "LONG" else (pos["entry"] - px) * pos["qty"]
                    net = gross - fee - pos["fee"]
                    cash += pos["margin"] + gross - fee
                    trades.append({
                        "symbol": pos["symbol"], "product": pos["product"], "side": pos["side"],
                        "qty": pos["qty"], "entry": pos["entry"], "exit": px, "leverage": pos["lev"],
                        "margin": pos["margin"], "net": round(net, 4), "reason": reason,
                        "bars": max(1, int((ts - pos["opened"]) / 60000)),
                    })
                    pos = None
        if pos:
            b = books[pos["symbol"]]
            c = next((x for x in b["candles"] if x["t"] == ts), None)
            if c:
                u = (c["c"] - pos["entry"]) * pos["qty"] if pos["side"] == "LONG" else (pos["entry"] - c["c"]) * pos["qty"]
                equity = cash + pos["margin"] + u
                peak = max(peak, equity)
            continue
        # scan pairs; first qualified setup wins (no trade quota)
        taken = False
        for u in UNIVERSE:
            b = books[u["id"]]
            idx = next((i for i, x in enumerate(b["candles"]) if x["t"] == ts), None)
            if idx is None or idx < 40:
                continue
            c = b["candles"][idx]
            side = setup(u["product"], c, idx, b["feat"])
            if not side:
                holds += 1
                continue
            a = b["feat"]["atr"][idx]
            px = c["c"] * (1 + SLIP if side == "LONG" else 1 - SLIP)
            lev = choose_lev(u["product"], a, px)
            stop_dist = max(a * ATR_STOP, c["c"] * MIN_STOP)
            liq = liq_px(side, px, lev)
            stop = px - stop_dist if side == "LONG" else px + stop_dist
            take_dist = max(a * ATR_TP, stop_dist * (ATR_TP / ATR_STOP))
            take = px + take_dist if side == "LONG" else px - take_dist
            if side == "LONG" and stop <= liq:
                stop = (px + liq) / 2
            if side == "SHORT" and stop >= liq:
                stop = (px + liq) / 2
            qty = floor_qty(min((cash * RISK) / abs(px - stop), (cash * MAX_EXP * lev) / px), u["step"])
            if qty <= 0:
                continue
            notional = qty * px
            margin = notional / lev if u["product"] == "FUTURES" else notional
            fee = notional * FEE
            if margin + fee > cash:
                continue
            pos = {
                "symbol": u["id"], "product": u["product"], "side": side, "qty": qty,
                "entry": px, "stop": stop, "take": take, "lev": lev, "margin": margin,
                "liq": liq, "fee": fee, "opened": ts,
            }
            cash -= margin + fee
            entries += 1
            taken = True
            break
        if not taken and not pos:
            equity = cash
            peak = max(peak, equity)
    if pos:
        b = books[pos["symbol"]]
        last = b["candles"][-1]["c"]
        u = (last - pos["entry"]) * pos["qty"] if pos["side"] == "LONG" else (pos["entry"] - last) * pos["qty"]
        equity = cash + pos["margin"] + u
    else:
        equity = cash
    wins = [t for t in trades if t["net"] > 0]
    losses = [t for t in trades if t["net"] <= 0]
    report = {
        "hours": HOURS,
        "starting_usdt": STARTING,
        "ending_equity": round(equity, 4),
        "realized_net": round(sum(t["net"] for t in trades), 4),
        "open_position": None if not pos else {
            "symbol": pos["symbol"], "side": pos["side"], "leverage": pos["lev"],
            "margin": round(pos["margin"], 4), "qty": pos["qty"], "entry": pos["entry"],
        },
        "trades": len(trades),
        "entries": entries,
        "holds_evaluated": holds,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0,
        "expectancy": round(sum(t["net"] for t in trades) / len(trades), 4) if trades else 0,
        "drawdown_pct": round(max(0.0, (peak - equity) / peak * 100), 4) if peak else 0,
        "leverage_used": sorted({t["leverage"] for t in trades} | ({pos["lev"]} if pos else set())),
        "pairs_traded": sorted({t["symbol"] for t in trades}),
        "closed": trades[-20:],
        "from": datetime.fromtimestamp(times[0] / 1000, tz=timezone.utc).isoformat() if times else None,
        "to": datetime.fromtimestamp(times[-1] / 1000, tz=timezone.utc).isoformat() if times else None,
        "live_armed": False,
        "note": "Paper replay of public Binance Vision 1m candles. Live stays disarmed. No fabricated fills.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    return report


def hermes_lesson(report: dict) -> str:
    packet = {
        "role": "postmortem",
        "capital_usdt": 100,
        "hours": report["hours"],
        "equity": report["ending_equity"],
        "trades": report["closed"],
        "expectancy": report["expectancy"],
        "instruction": "Return JSON {proposal_id, lesson, change, keep_hold_when, leverage_rule}. Paper only. No orders.",
    }
    body = {
        "model": "google-antigravity/gemini-3.7-flash",
        "temperature": 0,
        "max_tokens": 700,
        "messages": [{"role": "user", "content": json.dumps(packet)}],
    }
    req = urllib.request.Request(
        HERMES, data=json.dumps(body).encode(), headers={"content-type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as res:
            d = json.loads(res.read().decode())
        return ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except Exception as err:  # noqa: BLE001
        return f"HERMES_HOLD {err}"


if __name__ == "__main__":
    t0 = time.time()
    report = run()
    lesson = hermes_lesson(report)
    report["hermes_lesson"] = lesson
    report["elapsed_sec"] = round(time.time() - t0, 2)
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in report if k not in {"closed", "hermes_lesson"}}, indent=2))
    print("--- HERMES LESSON ---")
    print(lesson[:2000])
