#!/usr/bin/env python3
"""200 paper trades on live public SPOT klines: PAXG, ETH, SOL. No live orders."""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from goldguard.domain.defaults import SAFE_DEFAULT_V1
from goldguard.domain.enums import CandidateAction
from goldguard.strategy.engine import StrategyEngine, StrategyFeatures
from goldguard.strategy.indicators import atr_wilder, ema_series, median_volume_ratio, rsi_wilder

VISION = "https://data-api.binance.vision/api/v3/klines"
PAIRS = ("PAXGUSDT", "ETHUSDT", "SOLUSDT")
STARTING = 100.0
FEE, SLIP = 0.001, 0.0002
RISK = 0.005
OUT = Path("/workspace/artifacts/paper-spot-200.json")
TARGET = 200


def fetch_klines(symbol: str, interval: str, pages: int) -> list[dict]:
    rows: list[list] = []
    end = None
    for _ in range(pages):
        url = f"{VISION}?symbol={symbol}&interval={interval}&limit=1000"
        if end is not None:
            url += f"&endTime={end}"
        with urllib.request.urlopen(url, timeout=20) as res:
            batch = json.loads(res.read().decode())
        if not batch:
            break
        rows = batch + rows
        first_open = int(batch[0][0])
        if first_open <= 0:
            break
        end = first_open - 1
        if len(batch) < 1000:
            break
        time.sleep(0.05)
    seen = set()
    out = []
    for r in rows:
        t = int(r[0])
        if t in seen:
            continue
        seen.add(t)
        out.append(
            {
                "t": t,
                "ct": int(r[6]),
                "o": float(r[1]),
                "h": float(r[2]),
                "l": float(r[3]),
                "c": float(r[4]),
                "v": float(r[5]),
            }
        )
    out.sort(key=lambda x: x["t"])
    return out


def features_at(i: int, c15: list[dict], pack: dict) -> StrategyFeatures | None:
    if i < 50:
        return None
    hour = pack["hour_index"][i]
    if hour is None or hour < 49:
        return None
    c = c15[i]
    prev = c15[i - 1]
    atr14 = pack["atr14"][i]
    rsi14 = pack["rsi14"][i]
    prev_rsi = pack["rsi14"][i - 1]
    if atr14 is None or rsi14 is None:
        return None
    try:
        vol_ratio = median_volume_ratio(pack["volumes"][i - 19 : i + 1], 20) if i >= 19 else 0.0
    except ValueError:
        vol_ratio = 0.0
    ema50_1h = pack["ema50_1h"][hour]
    prior = pack["ema50_1h"][hour - 5] if hour >= 5 else ema50_1h
    return StrategyFeatures(
        previous_close=prev["c"],
        latest_close=c["c"],
        ema20_15m=pack["ema20"][i],
        ema50_15m=pack["ema50"][i],
        previous_rsi14=prev_rsi if prev_rsi is not None else 50.0,
        rsi14=rsi14,
        atr14=atr14,
        atr_rate=atr14 / c["c"] if c["c"] else 0.0,
        volume_ratio=vol_ratio,
        spread_rate=0.0004,
        latest_close_1h=pack["closes_1h"][hour],
        ema50_1h=ema50_1h,
        ema200_1h=pack["ema200_1h"][hour],
        ema50_slope_1h=(ema50_1h - prior) / 5,
        consecutive_closes_below_ema50=pack["below"][i],
        sufficient_history=True,
        contiguous=True,
        quote_fresh=True,
    )


def pack_pair(c15: list[dict], c1h: list[dict]) -> dict:
    closes = [x["c"] for x in c15]
    highs = [x["h"] for x in c15]
    lows = [x["l"] for x in c15]
    volumes = [x["v"] for x in c15]
    ema50 = ema_series(closes, 50)
    below = []
    streak = 0
    for close, avg in zip(closes, ema50):
        streak = streak + 1 if close < avg else 0
        below.append(streak)
    closes_1h = [x["c"] for x in c1h]
    hour_ct = [x["ct"] for x in c1h]
    hour_index: list[int | None] = []
    h = -1
    for bar in c15:
        while h + 1 < len(c1h) and hour_ct[h + 1] <= bar["ct"]:
            h += 1
        hour_index.append(h if h >= 0 else None)
    return {
        "ema20": ema_series(closes, 20),
        "ema50": ema50,
        "rsi14": rsi_wilder(closes, 14),
        "atr14": atr_wilder(highs, lows, closes, 14),
        "volumes": volumes,
        "below": below,
        "closes_1h": closes_1h,
        "ema50_1h": ema_series(closes_1h, 50),
        "ema200_1h": ema_series(closes_1h, 200),
        "hour_index": hour_index,
        "by_t": {x["t"]: x for x in c15},
        "idx": {x["t"]: i for i, x in enumerate(c15)},
        "candles": c15,
    }


def simulate(books: dict[str, dict], times: list[int]) -> dict:
    engine = StrategyEngine(SAFE_DEFAULT_V1)
    cash = STARTING
    pos = None
    trades = []
    peak = STARTING
    equity = STARTING
    settings = SAFE_DEFAULT_V1
    for ts in times:
        if pos:
            b = books[pos["symbol"]]
            c = b["by_t"].get(ts)
            if not c:
                continue
            i = b["idx"][ts]
            feat = features_at(i, b["candles"], b)
            exit_px = reason = None
            if c["l"] <= pos["stop"]:
                exit_px, reason = pos["stop"], "STOP_LOSS"
            elif c["h"] >= pos["take"]:
                exit_px, reason = pos["take"], "TAKE_PROFIT"
            elif feat is not None:
                ev = engine.evaluate(feat, has_position=True)
                if ev.action is CandidateAction.EXIT_CANDIDATE:
                    exit_px, reason = c["c"], ev.reason_codes[0]
            if exit_px is not None:
                px = exit_px * (1 - SLIP)
                fee = pos["qty"] * px * FEE
                gross = (px - pos["entry"]) * pos["qty"]
                net = gross - fee - pos["fee"]
                cash += pos["notional"] + gross - fee
                trades.append(
                    {
                        "symbol": pos["symbol"],
                        "net": round(net, 4),
                        "reason": reason,
                        "t": ts,
                    }
                )
                pos = None
                equity = cash
                peak = max(peak, equity)
                if len(trades) >= TARGET:
                    break
                continue
            u = (c["c"] - pos["entry"]) * pos["qty"]
            equity = cash + pos["notional"] + u
            peak = max(peak, equity)
            continue
        for sym in PAIRS:
            b = books[sym]
            i = b["idx"].get(ts)
            if i is None:
                continue
            feat = features_at(i, b["candles"], b)
            if feat is None:
                continue
            ev = engine.evaluate(feat, has_position=False)
            if ev.action is not CandidateAction.ENTRY_CANDIDATE:
                continue
            c = b["candles"][i]
            stop_rate = max(feat.atr_rate * float(settings.stop_atr_multiple), float(settings.minimum_stop_rate))
            stop_rate = min(stop_rate, float(settings.maximum_stop_rate))
            take_rate = stop_rate * float(settings.reward_r_multiple)
            px = c["c"] * (1 + SLIP)
            stop = px * (1 - stop_rate)
            take = px * (1 + take_rate)
            risk_cash = cash * RISK
            qty = risk_cash / max(px - stop, 1e-9)
            notional = qty * px
            if notional > cash * 0.95:
                qty = (cash * 0.95) / px
                notional = qty * px
            if notional < 5:
                continue
            fee = notional * FEE
            if notional + fee > cash:
                continue
            pos = {
                "symbol": sym,
                "qty": qty,
                "entry": px,
                "stop": stop,
                "take": take,
                "notional": notional,
                "fee": fee,
            }
            cash -= notional + fee
            break
        else:
            equity = cash
            peak = max(peak, equity)
    if pos:
        last = books[pos["symbol"]]["candles"][-1]["c"]
        u = (last - pos["entry"]) * pos["qty"]
        equity = cash + pos["notional"] + u
    wins = sum(1 for t in trades if t["net"] > 0)
    by = {}
    for t in trades:
        by[t["symbol"]] = round(by.get(t["symbol"], 0.0) + t["net"], 4)
    return {
        "trades": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate": round(wins / len(trades), 3) if trades else 0,
        "equity": round(equity, 2),
        "net": round(sum(t["net"] for t in trades), 4),
        "exp": round(sum(t["net"] for t in trades) / len(trades), 4) if trades else 0,
        "dd_pct": round(max(0.0, (peak - equity) / peak * 100), 2) if peak else 0,
        "by_pair": by,
        "reasons": dict(Counter(t["reason"] for t in trades)),
        "live_orders": False,
    }


def main() -> None:
    books = {}
    windows = {}
    for sym in PAIRS:
        c15 = fetch_klines(sym, "15m", 18)
        c1h = fetch_klines(sym, "1h", 6)
        books[sym] = pack_pair(c15, c1h)
        windows[sym] = {
            "bars_15m": len(c15),
            "from": datetime.fromtimestamp(c15[0]["t"] / 1000, tz=timezone.utc).isoformat(),
            "to": datetime.fromtimestamp(c15[-1]["t"] / 1000, tz=timezone.utc).isoformat(),
        }
        print(f"{sym} 15m={len(c15)} 1h={len(c1h)}", flush=True)
    times = sorted(set.intersection(*[set(b["candles"][i]["t"] for i in range(len(b["candles"]))) for b in books.values()]))
    combined = simulate(books, times)
    per_pair = {}
    for sym in PAIRS:
        solo = {sym: books[sym]}
        solo_times = [c["t"] for c in books[sym]["candles"]]
        # reuse simulator with one pair by temporarily wrapping
        saved = list(PAIRS)
        globals_pairs = list(PAIRS)
        per_pair[sym] = simulate({sym: books[sym]}, solo_times) if False else None
    # independent books: run each pair on its own 100 USDT to see pair quality
    independent = {}
    for sym in PAIRS:
        one = {k: v for k, v in books.items() if k == sym}

        def _run(symbol: str, book: dict) -> dict:
            engine = StrategyEngine(SAFE_DEFAULT_V1)
            cash = STARTING
            pos = None
            trades = []
            peak = STARTING
            equity = STARTING
            settings = SAFE_DEFAULT_V1
            cs = book["candles"]
            for i, c in enumerate(cs):
                if pos:
                    exit_px = reason = None
                    if c["l"] <= pos["stop"]:
                        exit_px, reason = pos["stop"], "STOP_LOSS"
                    elif c["h"] >= pos["take"]:
                        exit_px, reason = pos["take"], "TAKE_PROFIT"
                    else:
                        feat = features_at(i, cs, book)
                        if feat is not None:
                            ev = engine.evaluate(feat, has_position=True)
                            if ev.action is CandidateAction.EXIT_CANDIDATE:
                                exit_px, reason = c["c"], ev.reason_codes[0]
                    if exit_px is not None:
                        px = exit_px * (1 - SLIP)
                        fee = pos["qty"] * px * FEE
                        gross = (px - pos["entry"]) * pos["qty"]
                        net = gross - fee - pos["fee"]
                        cash += pos["notional"] + gross - fee
                        trades.append({"net": round(net, 4), "reason": reason})
                        pos = None
                        equity = cash
                        peak = max(peak, equity)
                    else:
                        u = (c["c"] - pos["entry"]) * pos["qty"]
                        equity = cash + pos["notional"] + u
                        peak = max(peak, equity)
                    continue
                feat = features_at(i, cs, book)
                if feat is None:
                    continue
                ev = engine.evaluate(feat, has_position=False)
                if ev.action is not CandidateAction.ENTRY_CANDIDATE:
                    continue
                stop_rate = max(feat.atr_rate * float(settings.stop_atr_multiple), float(settings.minimum_stop_rate))
                stop_rate = min(stop_rate, float(settings.maximum_stop_rate))
                take_rate = stop_rate * float(settings.reward_r_multiple)
                px = c["c"] * (1 + SLIP)
                stop = px * (1 - stop_rate)
                take = px * (1 + take_rate)
                qty = (cash * RISK) / max(px - stop, 1e-9)
                notional = qty * px
                if notional > cash * 0.95:
                    qty = (cash * 0.95) / px
                    notional = qty * px
                if notional < 5:
                    continue
                fee = notional * FEE
                if notional + fee > cash:
                    continue
                pos = {"qty": qty, "entry": px, "stop": stop, "take": take, "notional": notional, "fee": fee}
                cash -= notional + fee
            wins = sum(1 for t in trades if t["net"] > 0)
            return {
                "trades": len(trades),
                "wins": wins,
                "win_rate": round(wins / len(trades), 3) if trades else 0,
                "net": round(sum(t["net"] for t in trades), 4),
                "equity": round(cash if not pos else equity, 2),
                "reasons": dict(Counter(t["reason"] for t in trades)),
            }

        independent[sym] = _run(sym, books[sym])
    report = {
        "mode": "PAPER on live public spot klines — no live orders",
        "engine": "strategy-v1 15m pullback + 1h regime + COST_EDGE",
        "pairs": list(PAIRS),
        "product": "SPOT 1x",
        "starting": STARTING,
        "target_trades": TARGET,
        "window": windows,
        "combined_book": combined,
        "independent_books": independent,
        "vs_old_1m_futures": {
            "old": "BTC −2.80 · ETH −3.10 · SOL −2.24 · PAXG −0.83 (1m micro, ~200 trades)",
            "note": "This run is the Python 15m/1h spot genome, not that 1m book.",
        },
        "ready_for_live": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
