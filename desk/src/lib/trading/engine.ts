import { atr, ema, last, rsi } from "./indicators";
import { patternAllows, scanPatterns } from "./patterns";
import {
  ATR_STOP_MULT,
  ATR_TP_MULT,
  COST_EDGE_RATIO,
  DAILY_LOSS_LIMIT,
  ENGINE_INTERVAL,
  FEE_RATE,
  MAINT_MARGIN_RATE,
  MAX_DRAWDOWN,
  MAX_EXPOSURE,
  MAX_FUTURES_LEVERAGE,
  MIN_NOTIONAL,
  MIN_STOP_PCT,
  QTY_STEP,
  RISK_PER_TRADE,
  SLIPPAGE_RATE,
  STARTING_CASH,
  TRADE_LEVERAGE_CAP,
  UNIVERSE,
  type AgentEvent,
  type Candle,
  type ClosedTrade,
  type EngineState,
  type EvidenceItem,
  type Genome,
  type Order,
  type Position,
  type Product,
  type Quote,
  type RiskGate,
  type Side,
} from "./types";

let seq = 1;
const nid = (p: string) => `${p}-${seq++}`;

export function emptyState(startingCash = STARTING_CASH): EngineState {
  return {
    running: false,
    paused: false,
    halted: false,
    breakerTripped: false,
    mode: "PAPER",
    symbol: "PAXGUSDT",
    product: "SPOT",
    interval: ENGINE_INTERVAL,
    candles: [],
    quote: null,
    position: null,
    orders: [],
    trades: [],
    equity: startingCash,
    cash: startingCash,
    startingCash,
    maxLeverage: MAX_FUTURES_LEVERAGE,
    peakEquity: startingCash,
    dailyPnl: 0,
    realizedPnl: 0,
    fees: 0,
    funding: 0,
    events: [
      {
        id: nid("evt"),
        ts: Date.now(),
        kind: "system",
        title: "Desk armed in paper",
        detail: `Paper canary ${startingCash.toFixed(0)} USDT. Live execution is disarmed.`,
      },
    ],
    evidence: seedEvidence(),
    genomes: seedGenomes(),
    patterns: [],
    feedSource: "synthetic",
    lastTickAt: null,
    error: null,
  };
}

function seedEvidence(): EvidenceItem[] {
  return [
    {
      id: "ev-1",
      source: "Binance Announcements",
      title: "PAXGUSDT spot remains TRADING",
      when: "Policy sample — labelled, not a live scrape",
      score: 0.92,
      disposition: "ALLOW",
      url: "https://www.binance.com/en/support/announcement",
    },
    {
      id: "ev-2",
      source: "Forex Factory calendar",
      title: "High-impact USD print inside the next 4 hours",
      when: "Policy sample — reduces size, does not invent a calendar event",
      score: 0.61,
      disposition: "REDUCE",
      url: "https://www.forexfactory.com/calendar",
    },
    {
      id: "ev-3",
      source: "Forum commentary",
      title: "Retail gold thread — non-authoritative",
      when: "Forum posts cannot satisfy the independent-source gate and cannot HOLD the book alone",
      score: 0.18,
      disposition: "HOLD",
      url: "https://www.forexfactory.com/thread",
    },
  ];
}

function seedGenomes(): Genome[] {
  return [
    {
      id: "trend-pullback-v1",
      name: "Trend pullback v1",
      status: "active",
      sharpe: "unqualified",
      trades: 0,
      maxDd: "n/a",
      note: "15m EMA pullback, cost gate, 2x futures cap. ETH entries parked. Promotion needs walk-forward, not this preview.",
    },
    {
      id: "hermes-candidate-04",
      name: "Hermes candidate 04",
      status: "candidate",
      sharpe: "sealed holdout",
      trades: 0,
      maxDd: "n/a",
      note: "Proposal only. Hermes cannot size, submit, or mutate live state.",
    },
  ];
}

export function mark(state: EngineState, kind: AgentEvent["kind"], title: string, detail: string): EngineState {
  const evt: AgentEvent = { id: nid("evt"), ts: Date.now(), kind, title, detail };
  return { ...state, events: [evt, ...state.events].slice(0, 80) };
}

export function hydrate(state: EngineState, candles: Candle[], source: Quote["source"]): EngineState {
  const lastC = last(candles);
  if (!lastC) return { ...state, error: "No candles returned." };
  const quote = quoteFrom(lastC, source);
  const equity = markToMarket({ ...state, candles, quote }, lastC.c);
  return mark(
    {
      ...state,
      candles,
      quote,
      patterns: scanPatterns(candles),
      feedSource: source,
      equity,
      peakEquity: Math.max(state.peakEquity, equity),
      lastTickAt: Date.now(),
      error: null,
    },
    "market",
    source === "binance-public" ? "Public Binance feed attached" : "Synthetic gold path attached",
    source === "binance-public"
      ? `${candles.length} ${state.symbol} ${state.interval} candles from the public kline API. No API key used.`
      : "Public klines were unreachable, so the desk is replaying a labelled synthetic path. Not exchange truth.",
  );
}

export function tick(state: EngineState, now = Date.now(), incoming?: Candle, mode: "intra" | "close" = "intra"): EngineState {
  if (!state.running || state.paused || state.halted || state.candles.length < 40) return state;
  const prev = last(state.candles);
  if (!prev) return state;
  const next = incoming ?? nextCandle(prev, now, state.feedSource);

  if (mode === "intra" || next.t <= prev.t) {
    const merged: Candle = {
      ...prev,
      h: Math.max(prev.h, next.h, next.c),
      l: Math.min(prev.l, next.l, next.c),
      c: next.c,
    };
    const candles = [...state.candles.slice(0, -1), merged];
    const quote = quoteFrom(merged, state.feedSource);
    let nextState: EngineState = {
      ...state,
      candles,
      quote,
      lastTickAt: now,
      equity: markToMarket({ ...state, candles, quote }, merged.c),
    };
    nextState = applyBreaker(nextState);
    if (nextState.position) nextState = managePosition(nextState, next);
    nextState.peakEquity = Math.max(nextState.peakEquity, nextState.equity);
    return nextState;
  }

  const candles = [...state.candles.slice(-399), next];
  const quote = quoteFrom(next, state.feedSource);
  const patterns = scanPatterns(candles);
  let nextState: EngineState = {
    ...state,
    candles,
    quote,
    patterns,
    lastTickAt: now,
    equity: markToMarket({ ...state, candles, quote }, next.c),
  };
  nextState = applyBreaker(nextState);
  if (nextState.position) {
    nextState = managePosition(nextState, next);
  } else if (newEntriesAllowed(nextState)) {
    nextState = maybeEnter(nextState, next);
  }
  nextState.peakEquity = Math.max(nextState.peakEquity, nextState.equity);
  return nextState;
}

export function newEntriesAllowed(state: EngineState): boolean {
  return riskGates(state).every((g) => g.ok);
}

export function riskGates(state: EngineState): RiskGate[] {
  const bank = state.startingCash > 0 ? state.startingCash : STARTING_CASH;
  const dd = state.peakEquity > 0 ? (state.peakEquity - state.equity) / state.peakEquity : 0;
  const authoritative = state.evidence.filter((e) => e.source !== "Forum commentary");
  const authoritativeHold = authoritative.some((e) => e.disposition === "HOLD");
  const hasAllow = authoritative.some((e) => e.disposition === "ALLOW" && e.score >= 0.7);
  const stale = !state.lastTickAt || Date.now() - state.lastTickAt > 15_000;
  const lossCeiling = bank * DAILY_LOSS_LIMIT;
  return [
    { id: "running", label: "Runtime running", ok: state.running && !state.paused && !state.halted, detail: state.halted ? "Emergency halt" : state.paused ? "Paused" : state.running ? "Paper loop on" : "Idle" },
    { id: "mode", label: "Paper-only entries", ok: state.mode === "PAPER", detail: "Live arming is not exposed in this desk" },
    { id: "feed", label: "Fresh market feed", ok: !stale && state.candles.length >= 40, detail: stale ? "Feed stale — new entries HOLD" : `${state.candles.length} candles · ${state.feedSource}` },
    { id: "breaker", label: "Rolling-loss breaker", ok: !state.breakerTripped && Math.abs(Math.min(0, state.dailyPnl)) < lossCeiling, detail: state.breakerTripped ? "Tripped" : `Limit ${fmt(lossCeiling)} USDT` },
    { id: "daily", label: "Daily loss ceiling", ok: state.dailyPnl > -lossCeiling, detail: `${fmt(state.dailyPnl)} / ${fmt(-lossCeiling)} USDT` },
    { id: "drawdown", label: "Max drawdown", ok: dd < MAX_DRAWDOWN, detail: `${(dd * 100).toFixed(2)}% of peak` },
    { id: "slot", label: "Open slot", ok: !state.position, detail: state.position ? `${state.position.side} ${state.position.symbol} already on` : "Ready for a new paper entry" },
    { id: "evidence", label: "Evidence not HOLD", ok: hasAllow && !authoritativeHold, detail: authoritativeHold ? "Authoritative evidence HOLDs new entries" : hasAllow ? "Forum commentary ignored; authoritative sources allow reduced size" : "No independent ALLOW" },
    { id: "cycles", label: "Micro-trade ceiling", ok: state.trades.length < 1000, detail: `${state.trades.length} / 1000 completed cycles` },
  ];
}

function applyBreaker(state: EngineState): EngineState {
  const loss = Math.max(0, -state.dailyPnl);
  const ceiling = state.startingCash * DAILY_LOSS_LIMIT;
  if (loss >= ceiling && !state.breakerTripped) {
    return mark({ ...state, breakerTripped: true }, "risk", "Circuit breaker tripped", `Rolling loss ${fmt(loss)} USDT reached the ${fmt(ceiling)} USDT paper ceiling. New entries blocked; protection stays on.`);
  }
  return state;
}

function chooseLeverage(product: Product, atr: number, price: number, ceiling: number, interval = ENGINE_INTERVAL): number {
  if (product !== "FUTURES") return 1;
  const cap = Math.max(1, Math.min(TRADE_LEVERAGE_CAP, Math.floor(ceiling || 1), MAX_FUTURES_LEVERAGE));
  const atrPct = atr / price;
  let picked = 1;
  if (atrPct < 0.003) picked = 2;
  else if (atrPct < 0.008) picked = 2;
  else picked = 1;
  if (interval === "1m" || interval === "5m") picked = 1;
  return Math.min(picked, cap);
}

function liquidationPrice(side: Side, entry: number, leverage: number): number {
  const room = Math.max(0.05, 1 / leverage - MAINT_MARGIN_RATE * 1.2);
  return side === "LONG" ? entry * (1 - room) : entry * (1 + room);
}

function maybeEnter(state: EngineState, candle: Candle): EngineState {
  const spec = UNIVERSE.find((u) => u.id === state.symbol);
  if (spec && spec.entries === false) {
    if (state.candles.length % 8 === 0) {
      return mark(state, "market", "HOLD", `${state.symbol} new entries are parked after the paper sample. Chart stays live.`);
    }
    return state;
  }
  const closes = state.candles.map((c) => c.c);
  const fast = last(ema(closes, 12));
  const slow = last(ema(closes, 26));
  const r = last(rsi(closes, 14));
  const a = last(atr(state.candles, 14));
  if (!fast || !slow || r === undefined || !a || a <= 0) return state;
  const longSetup = fast > slow && r > 36 && r < 74 && candle.c <= fast * 1.006 && candle.c >= slow * 0.997;
  const shortSetup =
    state.product === "FUTURES" &&
    fast < slow &&
    r > 26 &&
    r < 64 &&
    candle.c >= fast * 0.994 &&
    candle.c <= slow * 1.003;
  let side: Side | null = longSetup ? "LONG" : shortSetup ? "SHORT" : null;
  const hits = state.patterns.length ? state.patterns : scanPatterns(state.candles);
  if (side) {
    const gate = patternAllows(hits, side);
    if (!gate.ok) {
      if (state.candles.length % 8 === 0) {
        return mark({ ...state, patterns: hits }, "market", "HOLD", gate.reason);
      }
      return { ...state, patterns: hits };
    }
  }
  if (!side) {
    if (state.candles.length % 8 === 0) {
      return mark({ ...state, patterns: hits }, "market", "HOLD", `No qualified ${state.symbol} setup. Autonomous default is HOLD.`);
    }
    return { ...state, patterns: hits };
  }
  const reduce = state.evidence.some((e) => e.disposition === "REDUCE" && e.source !== "Forum commentary");
  const stopDist = Math.max(a * ATR_STOP_MULT, candle.c * MIN_STOP_PCT);
  const px = side === "LONG" ? candle.c * (1 + SLIPPAGE_RATE) : candle.c * (1 - SLIPPAGE_RATE);
  const lev = chooseLeverage(state.product, a, px, state.maxLeverage, state.interval);
  const liq = liquidationPrice(side, px, lev);
  let stop = side === "LONG" ? px - stopDist : px + stopDist;
  const takeDist = Math.max(a * ATR_TP_MULT, stopDist * (ATR_TP_MULT / ATR_STOP_MULT));
  let take = side === "LONG" ? px + takeDist : px - takeDist;
  if (side === "LONG" && stop <= liq) stop = (px + liq) / 2;
  if (side === "SHORT" && stop >= liq) stop = (px + liq) / 2;
  const riskBudget = state.cash * RISK_PER_TRADE * (reduce ? 0.5 : 1);
  const maxMargin = state.cash * MAX_EXPOSURE * (reduce ? 0.5 : 1);
  const qtyRisk = riskBudget / Math.abs(px - stop);
  const qtyMargin = (maxMargin * lev) / px;
  const qty = floorQty(Math.min(qtyRisk, qtyMargin), QTY_STEP[state.symbol] ?? 0.0001);
  if (qty <= 0) return state;
  const notional = qty * px;
  const margin = state.product === "FUTURES" ? notional / lev : notional;
  const fee = notional * FEE_RATE;
  if (margin + fee > state.cash) return state;
  if (notional < MIN_NOTIONAL && state.startingCash >= 10) return state;
  const stopRisk = Math.abs(px - stop) * qty;
  const roundTrip = 2 * FEE_RATE * notional + 2 * SLIPPAGE_RATE * notional;
  if (stopRisk <= 0 || roundTrip > COST_EDGE_RATIO * stopRisk) {
    if (state.candles.length % 8 === 0) {
      return mark(state, "risk", "HOLD", `Costs ${fmt(roundTrip)} vs stop risk ${fmt(stopRisk)} — edge does not clear the fee buffer.`);
    }
    return state;
  }
  const pos: Position = {
    id: nid("pos"),
    symbol: state.symbol,
    product: state.product,
    side,
    qty,
    entry: px,
    stop,
    take,
    leverage: lev,
    margin,
    liquidation: liq,
    openedAt: candle.t,
    feesPaid: fee,
  };
  const order: Order = {
    id: nid("ord"),
    clientId: `gg-paper-${pos.id}`,
    symbol: state.symbol,
    product: state.product,
    side,
    type: "MARKET",
    qty,
    price: px,
    status: "FILLED",
    createdAt: candle.t,
  };
  return mark(
    {
      ...state,
      patterns: hits,
      position: pos,
      cash: state.cash - margin - fee,
      fees: state.fees + fee,
      orders: [order, ...state.orders].slice(0, 80),
    },
    "entry",
    `Paper ${side.toLowerCase()} ${state.symbol} ${lev}x`,
    `Qty ${qty} @ ${fmt(px)} · margin ${fmt(margin)} · lev ${lev}x · stop ${fmt(stop)} · liq ${fmt(liq)} · fee ${fmt(fee)}`,
  );
}

function managePosition(state: EngineState, candle: Candle): EngineState {
  const pos = state.position;
  if (!pos) return state;
  if (pos.side === "SHORT") {
    if (candle.h >= pos.stop) return close(state, pos.stop, "STOP_LOSS", candle.t);
    if (candle.l <= pos.take) return close(state, pos.take, "TAKE_PROFIT", candle.t);
    return state;
  }
  if (candle.l <= pos.stop) return close(state, pos.stop, "STOP_LOSS", candle.t);
  if (candle.h >= pos.take) return close(state, pos.take, "TAKE_PROFIT", candle.t);
  return state;
}

export function close(
  state: EngineState,
  rawPx: number,
  reason: ClosedTrade["reason"],
  ts: number,
): EngineState {
  const pos = state.position;
  if (!pos) return state;
  const px = pos.side === "LONG" ? rawPx * (1 - SLIPPAGE_RATE) : rawPx * (1 + SLIPPAGE_RATE);
  const proceeds = pos.qty * px;
  const fee = proceeds * FEE_RATE;
  const gross = pos.side === "LONG" ? (px - pos.entry) * pos.qty : (pos.entry - px) * pos.qty;
  const slippage = Math.abs(rawPx - px) * pos.qty;
  const net = gross - fee - pos.feesPaid - slippage;
  const trade: ClosedTrade = {
    id: nid("tr"),
    symbol: pos.symbol,
    product: pos.product,
    side: pos.side,
    qty: pos.qty,
    entry: pos.entry,
    exit: px,
    leverage: pos.leverage,
    margin: pos.margin,
    gross,
    fees: fee + pos.feesPaid,
    slippage,
    net,
    reason,
    openedAt: pos.openedAt,
    closedAt: ts,
  };
  const order: Order = {
    id: nid("ord"),
    clientId: `gg-paper-x-${pos.id}`,
    symbol: pos.symbol,
    product: pos.product,
    side: pos.side,
    type: reason === "STOP_LOSS" ? "STOP" : reason === "TAKE_PROFIT" ? "TAKE" : "MARKET",
    qty: pos.qty,
    price: px,
    status: "FILLED",
    createdAt: ts,
  };
  const cash = state.cash + pos.margin + gross - fee;
  const next: EngineState = {
    ...state,
    position: null,
    cash,
    fees: state.fees + fee,
    realizedPnl: state.realizedPnl + net,
    dailyPnl: state.dailyPnl + net,
    trades: [trade, ...state.trades].slice(0, 80),
    orders: [order, ...state.orders].slice(0, 80),
  };
  next.equity = cash;
  return mark(next, "exit", `Closed ${pos.symbol} · ${reason.replace("_", " ").toLowerCase()}`, `Net ${fmt(net)} USDT after fees and slippage. Paper ledger only.`);
}

export function emergencyFlatten(state: EngineState): EngineState {
  const ts = Date.now();
  const lastC = last(state.candles);
  let next = { ...state, halted: true, running: false, paused: false };
  if (state.position && lastC) {
    next = close(next, lastC.c, "EMERGENCY", ts);
  }
  return mark(next, "system", "Emergency stop", "New entries blocked. Open paper inventory flattened at last observed price.");
}

export function markToMarket(state: EngineState, lastPx: number): number {
  if (!state.position) return state.cash;
  return state.cash + state.position.qty * lastPx;
}

export function unrealized(state: EngineState): number {
  if (!state.position || !state.quote) return 0;
  const pos = state.position;
  return pos.side === "LONG"
    ? (state.quote.last - pos.entry) * pos.qty
    : (pos.entry - state.quote.last) * pos.qty;
}

function quoteFrom(c: Candle, source: Quote["source"]): Quote {
  const spread = Math.max(c.c * 0.00008, 0.02);
  return { bid: c.c - spread / 2, ask: c.c + spread / 2, last: c.c, spread, ts: c.t, source };
}

function nextCandle(prev: Candle, now: number, source: Quote["source"]): Candle {
  const vol = source === "binance-public" ? Math.max(0.12, (prev.h - prev.l) * 0.18) : 0.55;
  const noise = Math.sin(now / 4000) * vol * 0.35 + (Math.random() - 0.5) * vol;
  const o = prev.c;
  const c = Math.max(0.01, o + noise);
  return {
    t: now,
    o,
    h: Math.max(o, c) + Math.abs(noise) * 0.35,
    l: Math.min(o, c) - Math.abs(noise) * 0.35,
    c,
    v: prev.v * (0.85 + Math.random() * 0.3),
  };
}

function floorQty(q: number, step = 0.0001): number {
  if (step <= 0 || q <= 0) return 0;
  return Math.floor((q + 1e-12) / step) * step;
}

export function fmt(n: number): string {
  const abs = Math.abs(n);
  const digits = abs >= 1000 ? 2 : abs >= 10 ? 2 : 4;
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function signed(n: number): string {
  const s = fmt(n);
  return n > 0 ? `+${s}` : s;
}

export function replayPaper(state: EngineState, series: Candle[]): EngineState {
  let next: EngineState = {
    ...state,
    running: true,
    paused: false,
    lastTickAt: Date.now(),
  };
  const body = series.slice(-120);
  for (const candle of body) {
    const candles = [...next.candles.filter((c) => c.t < candle.t), candle].slice(-400);
    const quote = quoteFrom(candle, next.feedSource);
    next = { ...next, candles, quote, lastTickAt: Date.now() };
    next.equity = markToMarket(next, candle.c);
    next = applyBreaker(next);
    if (next.position) next = managePosition(next, candle);
    else if (newEntriesAllowed(next)) next = maybeEnter(next, candle);
    next.peakEquity = Math.max(next.peakEquity, next.equity);
  }
  return mark(
    next,
    "system",
    "Paper replay attached",
    `${next.trades.length} closed cycle(s), ${next.position ? "open long" : "flat"} on the public PAXG series. Live stays disarmed.`,
  );
}
