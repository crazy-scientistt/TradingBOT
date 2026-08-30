export interface Candle {
  time: string; // e.g. "18:00", "21:00", "20", "03:00", etc.
  fullTime?: string;
  openTime?: string;
  closeTime?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema20: number | null;
  ema50: number | null;
  rsi14: number | null;
  atr14: number | null;
  volumeRatio: number | null;
  closed?: boolean;
  interval?: string;
}

export interface Quote {
  symbol?: string;
  bid: number;
  ask: number;
  spread: number;
  spread_rate: number;
  observed_at: string;
}

export interface KpiMetrics {
  equity: number;
  equityCurrency: string;
  equityChangePercent: number | null;
  equityChangePeriod: string;
  cash: number;
  cashCurrency: string;
  cashChangeNote: string;
  totalPnl: number | null;
  totalPnlCurrency: string;
  totalPnlChangePercent: number | null;
  totalPnlChangePeriod: string;
  maxDrawdown: number | null;
  maxDrawdownPeriod: string;
  liveSpread: number | null;
  liveSpreadCurrency: string;
}

export interface PositionDetails {
  direction: 'LONG' | 'SHORT' | string;
  isLive: boolean;
  entry: number;
  stop?: number | null;
  target?: number | null;
  quantity: string;
  riskPercent?: number | null;
  unrealizedPnl?: number | null;
  symbol?: string;
}

export type PipelineStepStatus = 'completed' | 'active' | 'pending';

export interface PipelineStep {
  stepNumber: number;
  label: string;
  status: PipelineStepStatus;
  detail?: string;
}

export interface EquityDataPoint {
  date: string;
  value: number;
  benchmark?: number;
}

export interface NewsItem {
  id: string;
  category: 'fed' | 'yields' | 'exchange' | 'macro' | 'agent' | 'search' | string;
  title: string;
  source: string;
  time: string;
  direction?: string;
  severity?: string;
}

export interface HealthStatusItem {
  id: string;
  label: string;
  status: 'OK' | 'INFO' | 'WARNING' | 'ERROR';
  icon: 'database' | 'lease' | 'gemini' | 'hermes';
}
