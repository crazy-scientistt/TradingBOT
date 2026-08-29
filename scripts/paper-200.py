#!/usr/bin/env python3
"""Fill 200 paper cycles from public Binance Vision 1m history. No invented fills."""
from __future__ import annotations

import json
import math
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("/workspace/artifacts/paper-200.json")
VISION = "https://data-api.binance.vision/api/v3/klines"
HERMES = "http://127.0.0.1:8642/v1/chat/completions"
UNIVERSE = [
    {"id": "PAXGUSDT", "product": "SPOT", "step": 0.0001},
    {"id": "BTCUSDT", "product": "FUTURES", "step": 0.00001},
    {"id": "ETHUSDT", "product": "FUTURES", "step": 0.0001},
    {"id": "SOLUSDT", "product": "FUTURES", "step": 0.01},
]
TARGET = 200
DAYS = 14
STARTING = 100.0
FEE = 0.0005
SLIP = 0.0002
RISK = 0.01
MAX_EXP = 0.2
ATR_STOP = 1.6
ATR_TP = 2.4
MIN_STOP = 0.0015
MAX_LEV = 5
MAINT = 0.004
MIN_RR = 1.5


CACHE = Path("/tmp/gg-klines-cache")


def fetch_symbol(symbol: str, days: int) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{symbol}-1m-{days}d.json"
    if path.exists() and time.time() - path.stat().st_mtime < 3600:
        return json.loads(path.read_text())
    need = days * 1440
    end = None
    rows: list[list] = []
    while len(rows) < need:
        url = f"{VISION}?symbol={symbol}&interval=1m&limit=1000"
        if end is not None:
            url += f"&endTime={end}"
        with urllib.request.urlopen(url, timeout=15) as res:
            batch = json.loads(res.read().decode())
        if not batch:
            break
        rows = batch + rows
        first = int(batch[0][0])
        if first == end:
            break
        end = first - 1
        if len(batch) < 1000:
            break
        time.sleep(0.12)
    # unique by open time
    seen = {}
    for r in rows:
        seen[int(r[0])] = r
    ordered = [seen[k] for k in sorted(seen)]
    out = [
        {"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]), "v": float(r[5])}
        for r in ordered[-need:]
    ]
    path.write_text(json.dumps(out))
    return out


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
        g, lss = max(d, 0.0), max(-d, 0.0)
        if i < p:
            continue
        if i == p:
            gs = sum(max(xs[j] - xs[j - 1], 0.0) for j in range(1, p + 1))
            ls = sum(max(xs[j - 1] - xs[j], 0.0) for j in range(1, p + 1))
            ag, al = gs / p, ls / p
        else:
            ag = (ag * (p - 1) + g) / p
            al = (al * (p - 1) + lss) / p
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
    picked = min(picked, 2)  # 1m micro: Hermes lesson LEVCAP — 4x on 1m was noise
    return min(picked, MAX_LEV)


def liq_px(side: str, entry: float, lev: int) -> float:
    room = max(0.05, 1 / lev - MAINT * 1.2)
    return entry * (1 - room) if side == "LONG" else entry * (1 + room)


def feat(cs: list[dict]) -> dict:
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


def simulate(books: dict, starting: float = STARTING) -> dict:
    cash = starting
    pos = None
    trades = []
    peak = starting
    equity = starting
    holds = 0
    times = sorted(set.intersection(*[set(c["t"] for c in b["candles"]) for b in books.values()]))
    for ts in times:
        if len(trades) >= TARGET:
            break
        if pos:
            b = books[pos["symbol"]]
            c = b["by_t"].get(ts)
            if c:
                exit_px = reason = None
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
                        "qty": pos["qty"], "entry": round(pos["entry"], 6), "exit": round(px, 6),
                        "leverage": pos["lev"], "margin": round(pos["margin"], 4),
                        "net": round(net, 4), "reason": reason,
                        "bars": max(1, int((ts - pos["opened"]) / 60000)),
                    })
                    pos = None
                    equity = cash
                    peak = max(peak, equity)
                    continue
                u = (c["c"] - pos["entry"]) * pos["qty"] if pos["side"] == "LONG" else (pos["entry"] - c["c"]) * pos["qty"]
                equity = cash + pos["margin"] + u
                peak = max(peak, equity)
            continue
        candidates = []
        for u in UNIVERSE:
            b = books[u["id"]]
            idx = b["idx"].get(ts)
            if idx is None or idx < 40:
                continue
            c = b["candles"][idx]
            side = setup(u["product"], c, idx, b["feat"])
            if not side:
                holds += 1
                continue
            a = b["feat"]["atr"][idx]
            fast, slow = b["feat"]["fast"][idx], b["feat"]["slow"][idx]
            score = abs(fast - slow) / max(a, 1e-9)
            candidates.append((score, u, c, idx, side, a))
        if not candidates:
            equity = cash
            peak = max(peak, equity)
            continue
        candidates.sort(reverse=True)
        _score, u, c, idx, side, a = candidates[0]
        px = c["c"] * (1 + SLIP if side == "LONG" else 1 - SLIP)
        lev = choose_lev(u["product"], a, px)
        stop_dist = max(a * ATR_STOP, c["c"] * MIN_STOP)
        take_dist = max(stop_dist * MIN_RR, a * ATR_TP)
        liq = liq_px(side, px, lev)
        stop = px - stop_dist if side == "LONG" else px + stop_dist
        take = px + take_dist if side == "LONG" else px - take_dist
        if side == "LONG" and stop <= liq:
            stop = (px + liq) / 2
        if side == "SHORT" and stop >= liq:
            stop = (px + liq) / 2
        qty = floor_qty(min((cash * RISK) / max(1e-9, abs(px - stop)), (cash * MAX_EXP * lev) / px), u["step"])
        if qty <= 0:
            equity = cash
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
        continue
    if pos:
        last = books[pos["symbol"]]["candles"][-1]["c"]
        u = (last - pos["entry"]) * pos["qty"] if pos["side"] == "LONG" else (pos["entry"] - last) * pos["qty"]
        equity = cash + pos["margin"] + u
    wins = [t for t in trades if t["net"] > 0]
    losses = [t for t in trades if t["net"] <= 0]
    by_pair = {}
    for t in trades:
        by_pair.setdefault(t["symbol"], {"n": 0, "net": 0.0, "lev": []})
        by_pair[t["symbol"]]["n"] += 1
        by_pair[t["symbol"]]["net"] += t["net"]
        by_pair[t["symbol"]]["lev"].append(t["leverage"])
    for v in by_pair.values():
        v["net"] = round(v["net"], 4)
        v["avg_lev"] = round(sum(v["lev"]) / len(v["lev"]), 2)
        del v["lev"]
    return {
        "starting_usdt": starting,
        "ending_equity": round(equity, 4),
        "realized_net": round(sum(t["net"] for t in trades), 4),
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0,
        "expectancy": round(sum(t["net"] for t in trades) / len(trades), 4) if trades else 0,
        "drawdown_pct": round(max(0.0, (peak - equity) / peak * 100), 4) if peak else 0,
        "holds_evaluated": holds,
        "leverage_hist": dict(Counter(t["leverage"] for t in trades)),
        "reasons": dict(Counter(t["reason"] for t in trades)),
        "by_pair": by_pair,
        "avg_hold_bars": round(sum(t["bars"] for t in trades) / len(trades), 1) if trades else 0,
        "open": None if not pos else {"symbol": pos["symbol"], "side": pos["side"], "leverage": pos["lev"], "margin": round(pos["margin"], 4)},
        "sample": trades[:5] + trades[-5:] if len(trades) > 10 else trades,
        "ready_for_live": False,
    }


def hermes(summary: dict) -> str:
    body = {
        "model": "google-antigravity/gemini-3.7-flash",
        "temperature": 0,
        "max_tokens": 700,
        "messages": [{
            "role": "user",
            "content": json.dumps({
                "role": "postmortem",
                "instruction": "JSON {proposal_id, lesson, change, keep_doing, still_not_live_because}. Paper only.",
                "summary": {k: summary[k] for k in summary if k != "sample"},
            }),
        }],
    }
    req = urllib.request.Request(HERMES, data=json.dumps(body).encode(), headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as res:
            d = json.loads(res.read().decode())
        return ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except Exception as err:  # noqa: BLE001
        return f"HERMES_HOLD {err}"


def main() -> None:
    t0 = time.time()
    books = {}
    meta = {}
    for u in UNIVERSE:
        print(f"download {u['id']} ...", flush=True)
        cs = fetch_symbol(u["id"], DAYS)
        f = feat(cs)
        books[u["id"]] = {
            **u,
            "candles": cs,
            "feat": f,
            "by_t": {c["t"]: c for c in cs},
            "idx": {c["t"]: i for i, c in enumerate(cs)},
        }
        meta[u["id"]] = {
            "bars": len(cs),
            "from": datetime.fromtimestamp(cs[0]["t"] / 1000, tz=timezone.utc).isoformat(),
            "to": datetime.fromtimestamp(cs[-1]["t"] / 1000, tz=timezone.utc).isoformat(),
        }
        print(f"  {len(cs)} bars {meta[u['id']]['from']} -> {meta[u['id']]['to']}", flush=True)
    result = simulate(books)
    result["window"] = meta
    result["elapsed_sec"] = round(time.time() - t0, 2)
    result["live_armed"] = False
    result["target"] = TARGET
    result["note"] = "Paper replay of public 1m klines. Costs applied. Live disarmed. HOLD is valid."
    print("sim done", result["trades"], "trades equity", result["ending_equity"], flush=True)
    result["hermes_lesson"] = hermes(result)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in result if k not in {"sample", "hermes_lesson", "window"}}, indent=2))
    print("--- HERMES ---")
    print(result["hermes_lesson"][:1800])


if __name__ == "__main__":
    main()
