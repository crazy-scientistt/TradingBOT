import { atr, ema, last, rsi } from "./indicators";
import {
  ATR_STOP_MULT,
  ATR_TP_MULT,
  BREAKER_LOSS,
  DAILY_LOSS_LIMIT,
  FEE_RATE,
  MAX_DRAWDOWN,
  RISK_PER_TRADE,
  SLIPPAGE_RATE,
  STARTING_CASH,
  type AgentEvent,
  type Candle,
  type ClosedTrade,
  type EngineState,
  type EvidenceItem,
  type Genome,
  type Order,
  type Position,
  type Quote,
  type RiskGate,
} from "./types";

let seq = 1;
const nid = (p: string) => `${p}-${seq++}`;

export function emptyState(): EngineState {
  return {
    running: false,
    paused: false,
    halted: false,
    breakerTripped: false,
    mode: "PAPER",
    symbol: "PAXGUSDT",
    product: "SPOT",
    interval: "1m" as const,
    candles: [],
    quote: null,
    position: null,
    orders: [],
    trades: [],
    equity: STARTING_CASH,
    cash: STARTING_CASH,
    peakEquity: STARTING_CASH,
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
        detail: "Live execution is disarmed. New entries require a fresh feed and open risk gates.",
      },
    ],
    evidence: seedEvidence(),
    genomes: seedGenomes(),
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
      note: "Deterministic EMA pullback. Promotion requires paper qualification, not this preview.",
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
      feedSource: source,
      equity,
      peakEquity: Math.max(state.peakEquity, equity),
      lastTickAt: lastC.t,
      error: null,
    },
    "market",
    source === "binance-public" ? "Public Binance feed attached" : "Synthetic gold path attached",
    source === "binance-public"
      ? `${candles.length} PAXGUSDT candles from the public kline API. No API key used.`
      : "Public klines were unreachable, so the desk is replaying a labelled synthetic path. Not exchange truth.",
  );
}

export function tick(state: EngineState, now = Date.now(), incoming?: Candle): EngineState {
  if (!state.running || state.paused || state.halted || state.candles.length < 40) return state;
  const prev = last(state.candles);
  if (!prev) return state;
  const next = incoming ?? nextCandle(prev, now, state.feedSource);
  const candles = [...state.candles.slice(-399), next];
  const quote = quoteFrom(next, state.feedSource);
  let nextState: EngineState = {
    ...state,
    candles,
    quote,
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
  const dd = state.peakEquity > 0 ? (state.peakEquity - state.equity) / state.peakEquity : 0;
  const authoritative = state.evidence.filter((e) => e.source !== "Forum commentary");
  const authoritativeHold = authoritative.some((e) => e.disposition === "HOLD");
  const hasAllow = authoritative.some((e) => e.disposition === "ALLOW" && e.score >= 0.7);
  const stale = !state.lastTickAt || Date.now() - state.lastTickAt > 15_000;
  return [
    { id: "running", label: "Runtime running", ok: state.running && !state.paused && !state.halted, detail: state.halted ? "Emergency halt" : state.paused ? "Paused" : state.running ? "Paper loop on" : "Idle" },
    { id: "mode", label: "Paper-only entries", ok: state.mode === "PAPER", detail: "Live arming is not exposed in this desk" },
    { id: "feed", label: "Fresh market feed", ok: !stale && state.candles.length >= 40, detail: stale ? "Feed stale — new entries HOLD" : `${state.candles.length} candles · ${state.feedSource}` },
    { id: "breaker", label: "Rolling-loss breaker", ok: !state.breakerTripped && Math.abs(Math.min(0, state.dailyPnl)) < BREAKER_LOSS, detail: state.breakerTripped ? "Tripped" : `Limit ${fmt(BREAKER_LOSS)} USDT` },
    { id: "daily", label: "Daily loss ceiling", ok: state.dailyPnl > -STARTING_CASH * DAILY_LOSS_LIMIT, detail: `${fmt(state.dailyPnl)} / ${fmt(-STARTING_CASH * DAILY_LOSS_LIMIT)} USDT` },
    { id: "drawdown", label: "Max drawdown", ok: dd < MAX_DRAWDOWN, detail: `${(dd * 100).toFixed(2)}% of peak` },
    { id: "spot", label: "Spot cash-only", ok: state.product === "SPOT" && !state.position, detail: state.position ? "Already in a position" : "No leverage, no shorts" },
    { id: "evidence", label: "Evidence not HOLD", ok: hasAllow && !authoritativeHold, detail: authoritativeHold ? "Authoritative evidence HOLDs new entries" : hasAllow ? "Forum commentary ignored; authoritative sources allow reduced size" : "No independent ALLOW" },
    { id: "cycles", label: "Micro-trade ceiling", ok: state.trades.length < 1000, detail: `${state.trades.length} / 1000 completed cycles` },
  ];
}

function applyBreaker(state: EngineState): EngineState {
  const loss = Math.max(0, -state.dailyPnl);
  if (loss >= BREAKER_LOSS && !state.breakerTripped) {
    return mark({ ...state, breakerTripped: true }, "risk", "Circuit breaker tripped", `Rolling loss ${fmt(loss)} USDT reached the ${fmt(BREAKER_LOSS)} USDT paper ceiling. New entries blocked; protection stays on.`);
  }
  return state;
}

function maybeEnter(state: EngineState, candle: Candle): EngineState {
  const closes = state.candles.map((c) => c.c);
  const fast = last(ema(closes, 12));
  const slow = last(ema(closes, 26));
  const r = last(rsi(closes, 14));
  const a = last(atr(state.candles, 14));
  if (!fast || !slow || r === undefined || !a || a <= 0) return state;
  const pulled = candle.c <= fast * 1.006 && candle.c >= slow * 0.997;
  const trend = fast > slow && r > 36 && r < 74;
  if (!(trend && pulled)) {
    if (state.candles.length % 8 === 0) {
      return mark(state, "market", "No entry", "Waiting for an EMA pullback inside the risk envelope. Forum commentary cannot HOLD the book.");
    }
    return state;
  }
  const reduce = state.evidence.some((e) => e.disposition === "REDUCE" && e.source !== "Forum commentary");
  const stopDist = a * ATR_STOP_MULT;
  const riskBudget = state.cash * RISK_PER_TRADE * (reduce ? 0.5 : 1);
  const qty = floorQty(riskBudget / stopDist);
  if (qty <= 0) return state;
  const px = candle.c * (1 + SLIPPAGE_RATE);
  const notional = qty * px;
  const fee = notional * FEE_RATE;
  if (notional + fee > state.cash) return state;
  const pos: Position = {
    id: nid("pos"),
    symbol: state.symbol,
    product: "SPOT",
    side: "LONG",
    qty,
    entry: px,
    stop: px - stopDist,
    take: px + a * ATR_TP_MULT,
    leverage: 1,
    openedAt: candle.t,
    feesPaid: fee,
  };
  const order: Order = {
    id: nid("ord"),
    clientId: `gg-paper-${pos.id}`,
    symbol: state.symbol,
    product: "SPOT",
    side: "LONG",
    type: "MARKET",
    qty,
    price: px,
    status: "FILLED",
    createdAt: candle.t,
  };
  return mark(
    {
      ...state,
      position: pos,
      cash: state.cash - notional - fee,
      fees: state.fees + fee,
      orders: [order, ...state.orders].slice(0, 80),
    },
    "entry",
    `Paper long ${state.symbol}`,
    `Qty ${qty.toFixed(4)} @ ${fmt(px)} · stop ${fmt(pos.stop)} · take ${fmt(pos.take)} · fee ${fmt(fee)}`,
  );
}

function managePosition(state: EngineState, candle: Candle): EngineState {
  const pos = state.position;
  if (!pos) return state;
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
  const px = rawPx * (1 - SLIPPAGE_RATE);
  const proceeds = pos.qty * px;
  const fee = proceeds * FEE_RATE;
  const gross = (px - pos.entry) * pos.qty;
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
    side: "LONG",
    type: reason === "STOP_LOSS" ? "STOP" : reason === "TAKE_PROFIT" ? "TAKE" : "MARKET",
    qty: pos.qty,
    price: px,
    status: "FILLED",
    createdAt: ts,
  };
  const cash = state.cash + proceeds - fee;
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
  return (state.quote.last - state.position.entry) * state.position.qty;
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

function floorQty(q: number): number {
  return Math.floor(q * 10_000) / 10_000;
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
