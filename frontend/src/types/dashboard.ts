export interface Candle {
  time: string; // e.g. "18:00", "21:00", "20", "03:00", etc.
  fullTime?: string;
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
}

export interface KpiMetrics {
  equity: number;
  equityCurrency: string;
  equityChangePercent: number;
  equityChangePeriod: string;
  cash: number;
  cashCurrency: string;
  cashChangeNote: string;
  totalPnl: number;
  totalPnlCurrency: string;
  totalPnlChangePercent: number;
  totalPnlChangePeriod: string;
  maxDrawdown: number;
  maxDrawdownPeriod: string;
  liveSpread: number;
  liveSpreadCurrency: string;
}

export interface PositionDetails {
  direction: 'LONG' | 'SHORT';
  isLive: boolean;
  entry: number;
  stop: number;
  target: number;
  quantity: string;
  riskPercent: number;
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
  category: 'fed' | 'yields' | 'exchange';
  title: string;
  source: string;
  time: string;
}

export interface HealthStatusItem {
  id: string;
  label: string;
  status: 'OK' | 'INFO' | 'WARNING' | 'ERROR';
  icon: 'database' | 'lease' | 'gemini' | 'hermes';
}
