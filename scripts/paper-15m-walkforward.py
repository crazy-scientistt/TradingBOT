#!/usr/bin/env python3
"""Walk-forward 15m paper: ETH off, 2x cap, cost gate. Tune on first half, test on second."""
from __future__ import annotations

import json, math, time, urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("/workspace/artifacts/paper-15m-walkforward.json")
VISION = "https://data-api.binance.vision/api/v3/klines"
PAIRS = [
    {"id": "PAXGUSDT", "product": "SPOT", "step": 0.0001, "entries": True},
    {"id": "BTCUSDT", "product": "FUTURES", "step": 0.00001, "entries": True},
    {"id": "SOLUSDT", "product": "FUTURES", "step": 0.01, "entries": True},
]
FEE, SLIP, RISK, MAX_EXP = 0.0005, 0.0002, 0.01, 0.2
ATR_STOP, ATR_TP, MIN_STOP, MIN_RR, COST = 1.6, 2.4, 0.0015, 1.5, 0.35
MAINT, STARTING = 0.004, 100.0


def fetch(symbol: str) -> list[dict]:
    url = f"{VISION}?symbol={symbol}&interval=15m&limit=1000"
    with urllib.request.urlopen(url, timeout=15) as res:
        raw = json.loads(res.read().decode())
    return [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]), "v": float(r[5])} for r in raw]


def ema(xs, p):
    k = 2 / (p + 1)
    e = xs[0]
    out = []
    for x in xs:
        e = x * k + e * (1 - k)
        out.append(e)
    return out


def rsi(xs, p=14):
    out = [None] * len(xs)
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


def atr(cs, p=14):
    trs = []
    for i, c in enumerate(cs):
        trs.append(c["h"] - c["l"] if i == 0 else max(c["h"] - c["l"], abs(c["h"] - cs[i - 1]["c"]), abs(c["l"] - cs[i - 1]["c"])))
    return ema(trs, p)


def floor_qty(q, step):
    if q <= 0 or step <= 0:
        return 0.0
    return math.floor((q + 1e-12) / step) * step


def feat(cs):
    closes = [c["c"] for c in cs]
    return {"fast": ema(closes, 12), "slow": ema(closes, 26), "rsi": rsi(closes), "atr": atr(cs)}


def setup(product, c, i, f):
    fast, slow, r, a = f["fast"][i], f["slow"][i], f["rsi"][i], f["atr"][i]
    if r is None or a <= 0:
        return None
    if fast > slow and 36 < r < 74 and c["c"] <= fast * 1.006 and c["c"] >= slow * 0.997:
        return "LONG"
    if product == "FUTURES" and fast < slow and 26 < r < 64 and c["c"] >= fast * 0.994 and c["c"] <= slow * 1.003:
        return "SHORT"
    return None


def simulate(books, times):
    cash = STARTING
    pos = None
    trades = []
    peak = STARTING
    equity = STARTING
    skipped = 0
    for ts in times:
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
                    trades.append({"symbol": pos["symbol"], "side": pos["side"], "lev": pos["lev"], "net": round(net, 4), "reason": reason})
                    pos = None
                    equity = cash
                    peak = max(peak, equity)
                    continue
                u = (c["c"] - pos["entry"]) * pos["qty"] if pos["side"] == "LONG" else (pos["entry"] - c["c"]) * pos["qty"]
                equity = cash + pos["margin"] + u
                peak = max(peak, equity)
            continue
        cands = []
        for u in PAIRS:
            if not u["entries"]:
                continue
            b = books[u["id"]]
            idx = b["idx"].get(ts)
            if idx is None or idx < 40:
                continue
            c = b["candles"][idx]
            side = setup(u["product"], c, idx, b["feat"])
            if not side:
                continue
            a = b["feat"]["atr"][idx]
            score = abs(b["feat"]["fast"][idx] - b["feat"]["slow"][idx]) / max(a, 1e-9)
            cands.append((score, u, c, side, a))
        if not cands:
            equity = cash
            peak = max(peak, equity)
            continue
        cands.sort(reverse=True)
        _, u, c, side, a = cands[0]
        px = c["c"] * (1 + SLIP if side == "LONG" else 1 - SLIP)
        lev = 1 if u["product"] != "FUTURES" else (2 if a / px < 0.008 else 1)
        stop_dist = max(a * ATR_STOP, c["c"] * MIN_STOP)
        take_dist = max(stop_dist * MIN_RR, a * ATR_TP)
        stop = px - stop_dist if side == "LONG" else px + stop_dist
        take = px + take_dist if side == "LONG" else px - take_dist
        qty = floor_qty(min((cash * RISK) / max(1e-9, abs(px - stop)), (cash * MAX_EXP * lev) / px), u["step"])
        if qty <= 0:
            continue
        notional = qty * px
        margin = notional / lev if u["product"] == "FUTURES" else notional
        fee = notional * FEE
        if margin + fee > cash:
            continue
        stop_risk = abs(px - stop) * qty
        round_trip = 2 * FEE * notional + 2 * SLIP * notional
        if stop_risk <= 0 or round_trip > COST * stop_risk:
            skipped += 1
            continue
        pos = {"symbol": u["id"], "product": u["product"], "side": side, "qty": qty, "entry": px, "stop": stop, "take": take, "lev": lev, "margin": margin, "fee": fee}
        cash -= margin + fee
    if pos:
        last = books[pos["symbol"]]["candles"][-1]["c"]
        u = (last - pos["entry"]) * pos["qty"] if pos["side"] == "LONG" else (pos["entry"] - last) * pos["qty"]
        equity = cash + pos["margin"] + u
    wins = sum(1 for t in trades if t["net"] > 0)
    by = {}
    for t in trades:
        by.setdefault(t["symbol"], 0.0)
        by[t["symbol"]] += t["net"]
    return {
        "trades": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate": round(wins / len(trades), 3) if trades else 0,
        "equity": round(equity, 2),
        "net": round(sum(t["net"] for t in trades), 4),
        "exp": round(sum(t["net"] for t in trades) / len(trades), 4) if trades else 0,
        "dd": round(max(0.0, (peak - equity) / peak * 100), 2) if peak else 0,
        "skipped_cost": skipped,
        "by_pair": {k: round(v, 4) for k, v in by.items()},
        "reasons": dict(Counter(t["reason"] for t in trades)),
    }


def main():
    books = {}
    for u in PAIRS:
        cs = fetch(u["id"])
        books[u["id"]] = {**u, "candles": cs, "feat": feat(cs), "by_t": {c["t"]: c for c in cs}, "idx": {c["t"]: i for i, c in enumerate(cs)}}
        time.sleep(0.08)
    times = sorted(set.intersection(*[set(c["t"] for c in b["candles"]) for b in books.values()]))
    mid = len(times) // 2
    train_t, test_t = times[:mid], times[mid:]
    train = simulate(books, train_t)
    test = simulate(books, test_t)
    report = {
        "engine": "15m EMA pullback + cost gate + 2x cap + ETH off",
        "live_armed": False,
        "walkforward_pass": bool(test["net"] > 0 and test["trades"] >= 20 and test["dd"] < 12),
        "ready_for_live": False,
        "window": {
            "from": datetime.fromtimestamp(times[0] / 1000, tz=timezone.utc).isoformat(),
            "split": datetime.fromtimestamp(times[mid] / 1000, tz=timezone.utc).isoformat(),
            "to": datetime.fromtimestamp(times[-1] / 1000, tz=timezone.utc).isoformat(),
            "bars": len(times),
        },
        "train": train,
        "test": test,
        "note": "Positive test net is still one window. Live stays disarmed until sealed holdout + operator gates.",
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
