export type Product = "SPOT" | "FUTURES";
export type Side = "LONG" | "SHORT";
export type Mode = "PAPER";
export type Interval = "1m" | "5m" | "15m" | "1h" | "4h";
export type ChartMode = "lite" | "advanced";
export type Tab =
  | "home"
  | "agent"
  | "news"
  | "learning"
  | "providers"
  | "market"
  | "trades"
  | "cockpit"
  | "qualify";

export const INTERVALS: Interval[] = ["1m", "5m", "15m", "1h", "4h"];

export type Candle = {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
};

export type Quote = {
  bid: number;
  ask: number;
  last: number;
  spread: number;
  ts: number;
  source: "binance-public" | "synthetic";
};

export type Position = {
  id: string;
  symbol: string;
  product: Product;
  side: Side;
  qty: number;
  entry: number;
  stop: number;
  take: number;
  leverage: number;
  openedAt: number;
  feesPaid: number;
};

export type Order = {
  id: string;
  clientId: string;
  symbol: string;
  product: Product;
  side: Side;
  type: "MARKET" | "STOP" | "TAKE";
  qty: number;
  price: number;
  status: "FILLED" | "CANCELLED";
  createdAt: number;
};

export type ClosedTrade = {
  id: string;
  symbol: string;
  product: Product;
  side: Side;
  qty: number;
  entry: number;
  exit: number;
  gross: number;
  fees: number;
  slippage: number;
  net: number;
  reason: "TAKE_PROFIT" | "STOP_LOSS" | "SIGNAL" | "EMERGENCY";
  openedAt: number;
  closedAt: number;
};

export type RiskGate = {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
};

export type AgentEvent = {
  id: string;
  ts: number;
  kind: "market" | "risk" | "entry" | "exit" | "hermes" | "system";
  title: string;
  detail: string;
};

export type EvidenceItem = {
  id: string;
  source: string;
  title: string;
  when: string;
  score: number;
  disposition: "ALLOW" | "REDUCE" | "HOLD";
  url: string;
};

export type Genome = {
  id: string;
  name: string;
  status: "active" | "candidate" | "quarantine";
  sharpe: string;
  trades: number;
  maxDd: string;
  note: string;
};

export type EngineState = {
  running: boolean;
  paused: boolean;
  halted: boolean;
  breakerTripped: boolean;
  mode: Mode;
  symbol: string;
  product: Product;
  interval: Interval;
  candles: Candle[];
  quote: Quote | NoneQuote;
  position: Position | null;
  orders: Order[];
  trades: ClosedTrade[];
  equity: number;
  cash: number;
  peakEquity: number;
  dailyPnl: number;
  realizedPnl: number;
  fees: number;
  funding: number;
  events: AgentEvent[];
  evidence: EvidenceItem[];
  genomes: Genome[];
  feedSource: Quote["source"];
  lastTickAt: number | null;
  error: string | null;
};

export type NoneQuote = null;

export const STARTING_CASH = 10_000;
export const FEE_RATE = 0.0005;
export const SLIPPAGE_RATE = 0.0002;
export const RISK_PER_TRADE = 0.01;
export const DAILY_LOSS_LIMIT = 0.05;
export const MAX_DRAWDOWN = 0.12;
export const BREAKER_LOSS = 500;
export const ATR_STOP_MULT = 1.6;
export const ATR_TP_MULT = 2.4;
