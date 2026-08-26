export * from './dashboard';

export type GenomeStage =
  | 'candidate'
  | 'dev_passed'
  | 'val_passed'
  | 'holdout_passed'
  | 'shadow'
  | 'active'
  | 'quarantined'
  | 'retired'
  | 'archived';

export interface IndicatorSpec {
  indicator: 'rsi' | 'ema_slope' | 'volume_ratio' | 'atr_ratio';
  timeframe: '15m' | '1h';
  period: number;
}

export interface Condition {
  left: IndicatorSpec | string;
  op: '>' | '<' | '>=' | '<=' | '==' | 'crosses_above' | 'crosses_below';
  right: number | string;
}

export interface GuardBounds {
  min_atr_rate: string;
  max_atr_rate: string;
  max_spread_rate: string;
}

export interface ExitRules {
  take_profit_r_multiple: string;
  stop_loss_atr_multiple: string;
  invalidation: Condition[];
}

export interface StrategyGenome {
  genome_id: string;
  parent_id?: string | null;
  title: string;
  hypothesis: string;
  evidence_refs: string[];
  regime: string[];
  guard: GuardBounds;
  entry: Condition[];
  exit: ExitRules;
  genome_hash?: string;
  status?: GenomeStage;
  created_at?: string;
}

export interface BacktestPerformance {
  net_pnl: string;
  gross_pnl: string;
  fee_drag: string;
  net_return: string;
  annualized_return?: string;
  trade_count: number;
  win_rate: string;
  profit_factor?: string;
  maximum_drawdown: string;
  sharpe_ratio?: string;
  sortino_ratio?: string;
  calmar_ratio?: string;
}

export interface ProviderRoute {
  id: string;
  role: 'decision' | 'context' | 'hermes';
  provider: string;
  model: string;
  pinned: boolean;
  version: number;
  latency_ms?: number;
  status?: 'active' | 'degraded' | 'offline';
}

export interface AIProvider {
  name: string;
  kind: string;
  base_url: string;
  key_fingerprint: string;
  status: 'active' | 'degraded' | 'offline';
  latency_ms: number;
}

export interface ResearchQuota {
  date: string;
  backtests_used: number;
  backtests_limit: number;
  web_calls_used: number;
  web_calls_limit: number;
}

export interface TradeReflection {
  id: string;
  trade_id: string;
  namespace: 'historical' | 'forward';
  lesson_code: string;
  lesson: string;
  regime_tags: string[];
  net_pnl: string;
  fee_drag: string;
  exit_reason: string;
  created_at: string;
}

export interface BotStateStatus {
  state: 'NORMAL' | 'RESEARCH_ACTIVE' | 'AUTONOMY_SUSPENDED' | 'QUARANTINE' | 'KILL_SWITCH_ACTIVE';
  full_autonomy: boolean;
  daily_loss_percent: number;
  daily_loss_limit: number;
  circuit_breaker_tripped: boolean;
  active_genome_id: string;
}
