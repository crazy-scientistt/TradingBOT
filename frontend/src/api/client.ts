import {
  KpiMetrics,
  Candle,
  PositionDetails,
  PipelineStep,
  EquityDataPoint,
  NewsItem,
  HealthStatusItem,
} from '../types/dashboard';
import {
  StrategyGenome,
  BacktestPerformance,
  AIProvider,
  OpenCodexModel,
  ProviderRoute,
  ResearchQuota,
  TradeReflection,
  BotStateStatus,
} from '../types';

const API_BASE = '/api';

export type Availability = 'available' | 'degraded' | 'unavailable';

/**
 * Every read endpoint except health/preflight carries this provenance envelope.
 * Keeping it in one place prevents callers from accidentally rendering metadata
 * as if it were the payload itself.
 */
export interface ApiEnvelope<T> {
  availability: Availability;
  source: string;
  observed_at: string;
  stale: boolean;
  detail: string | null;
  data: T;
}

export interface HealthResponse {
  status: string;
  database?: string;
  quota?: { backtests_today?: number; web_calls_today?: number };
  bot_running?: boolean;
  market?: Availability;
  timestamp?: string;
}

export interface StatusResponse {
  environment: string;
  mode: string;
  symbol: string;
  bot_running: boolean;
  bot_state?: string | null;
  full_autonomy: boolean;
  active_genome_id: string | null;
  paper_balance: string | null;
  live_enabled: boolean;
  market_source?: string;
  market_verified?: boolean;
  degraded_reasons?: string[];
  canary?: Record<string, unknown>;
}

export interface Quote {
  symbol: string;
  bid: number;
  ask: number;
  spread: number;
  spread_rate: number;
  observed_at: string;
}

export interface PositionResponse {
  hasPosition: boolean;
  position: PositionDetails | null;
  pipelineSteps: PipelineStep[];
}

export interface PreflightCheck {
  id: string;
  label: string;
  status: 'pass' | 'warn' | 'fail';
  detail: string;
}

export interface PreflightResponse {
  ready: boolean;
  checks: PreflightCheck[];
  blocking: string[];
  observed_at: string;
}

export interface AgentEvent {
  event_id: string;
  action: string;
  reason: string;
  reason_codes: string[];
  payload: Record<string, unknown>;
  occurred_at: string;
  audit_worthy: boolean;
}

export interface EffectiveSettings {
  environment: string;
  mode: string;
  symbol: string;
  entry_timeframe: string;
  regime_timeframe: string;
  paper_starting_balance: string;
  paper_risk_per_trade: string;
  taker_fee_rate: string;
  slippage_rate: string;
  max_spread_rate: string;
  daily_loss_halt: string;
  emergency_drawdown_halt: string;
  research_backtest_max_per_day: number;
  research_web_calls_max_per_day: number;
  market_ingestion_enabled: boolean;
  live_capability_enabled: boolean;
  mutable: false;
  detail?: string | null;
}

export interface DashboardSnapshot {
  generated_at: string;
  health: HealthResponse;
  status: ApiEnvelope<StatusResponse>;
  kpi: ApiEnvelope<KpiMetrics | null>;
  quote: ApiEnvelope<Quote | null>;
  candles: ApiEnvelope<Candle[]>;
  position: ApiEnvelope<PositionResponse>;
  equity: ApiEnvelope<EquityDataPoint[]>;
  context: ApiEnvelope<NewsItem[]>;
  genomes: ApiEnvelope<StrategyGenome[]>;
  providers: ApiEnvelope<AIProvider[]>;
  catalog?: ApiEnvelope<OpenCodexModel[]>;
  routes: ApiEnvelope<ProviderRoute[]>;
  quota: ApiEnvelope<ResearchQuota | null>;
  reflections: ApiEnvelope<TradeReflection[]>;
  botState: ApiEnvelope<BotStateStatus | null>;
  agentEvents: ApiEnvelope<AgentEvent[]>;
  preflight: PreflightResponse;
  promotionCanary: ApiEnvelope<Record<string, unknown> | null>;
}

function isApiEnvelope(value: unknown): value is ApiEnvelope<unknown> {
  return (
    typeof value === 'object' &&
    value !== null &&
    'availability' in value &&
    'data' in value &&
    'source' in value
  );
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...options,
  });
  if (!res.ok) {
    let errorMsg = `HTTP ${res.status}: ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) errorMsg = body.detail;
    } catch {
      // ignore
    }
    throw new Error(errorMsg);
  }
  const payload: unknown = await res.json();
  // Read helpers return the payload, while dashboard keeps section envelopes
  // so the context can expose stale/degraded provenance to the UI.
  return (isApiEnvelope(payload) ? payload.data : payload) as T;
}

export const api = {
  // System Health & Status
  async getHealth(): Promise<HealthResponse> {
    return fetchJson(`${API_BASE}/health`);
  },

  async getStatus(): Promise<StatusResponse> {
    return fetchJson(`${API_BASE}/status`);
  },

  async getDashboard(): Promise<DashboardSnapshot> {
    return fetchJson(`${API_BASE}/dashboard`);
  },

  async preflight(): Promise<PreflightResponse> {
    return fetchJson(`${API_BASE}/preflight`);
  },

  // KPI Metrics
  async getKpi(): Promise<KpiMetrics | null> {
    return fetchJson(`${API_BASE}/kpi`);
  },

  // Market Candles & Quotes
  async getMarketCandles(symbol = 'PAXGUSDT', interval = '15m', limit = 50): Promise<Candle[]> {
    return fetchJson(`${API_BASE}/market/candles?symbol=${symbol}&interval=${interval}&limit=${limit}`);
  },

  async getMarketQuote(symbol = 'PAXGUSDT'): Promise<Quote | null> {
    return fetchJson(`${API_BASE}/market/quote?symbol=${symbol}`);
  },

  // Open Position & 5-Step Pipeline
  async getPosition(): Promise<{
    hasPosition: boolean;
    position: PositionDetails | null;
    pipelineSteps: PipelineStep[];
  }> {
    return fetchJson(`${API_BASE}/position`);
  },

  // Equity History
  async getEquityCurve(): Promise<EquityDataPoint[]> {
    return fetchJson(`${API_BASE}/equity`);
  },

  // Live Macro Context & News
  async getLiveContext(): Promise<NewsItem[]> {
    return fetchJson(`${API_BASE}/context`);
  },

  // Strategy Genomes & Studio
  async getGenomes(): Promise<StrategyGenome[]> {
    return fetchJson(`${API_BASE}/genomes`);
  },

  async getGenome(genomeId: string): Promise<StrategyGenome> {
    return fetchJson(`${API_BASE}/genomes/${genomeId}`);
  },

  async saveGenome(genome: StrategyGenome): Promise<{ status: string; genome_id: string; genome_hash: string }> {
    return fetchJson(`${API_BASE}/genomes/save`, {
      method: 'POST',
      body: JSON.stringify(genome),
    });
  },

  async promoteGenome(genomeId: string): Promise<{ status: string; genome_id: string; new_status: string }> {
    return fetchJson(`${API_BASE}/genomes/promote`, {
      method: 'POST',
      body: JSON.stringify({ genome_id: genomeId }),
    });
  },

  async runBacktest(genome: StrategyGenome): Promise<BacktestPerformance & { trades?: any[] }> {
    return fetchJson(`${API_BASE}/backtest/run`, {
      method: 'POST',
      body: JSON.stringify({ genome }),
    });
  },

  // Hermes Autonomous Research
  async getQuota(): Promise<ResearchQuota | null> {
    return fetchJson(`${API_BASE}/quota`);
  },

  async triggerHermesStep(): Promise<{
    status: string;
    candidate?: StrategyGenome;
    candidate_genome_id?: string | null;
    quota_used?: [number, number];
    gate_results?: Record<string, unknown>;
  }> {
    return fetchJson(`${API_BASE}/hermes/step`, {
      method: 'POST',
    });
  },

  async getReflections(namespace?: string, limit = 100): Promise<TradeReflection[]> {
    const q = namespace ? `?namespace=${namespace}&limit=${limit}` : `?limit=${limit}`;
    return fetchJson(`${API_BASE}/reflections${q}`);
  },

  // Providers & Routing Matrix
  async getProviders(): Promise<AIProvider[]> {
    return fetchJson(`${API_BASE}/providers`);
  },

  async getCatalog(): Promise<OpenCodexModel[]> {
    return fetchJson(`${API_BASE}/providers/catalog`);
  },

  async getRoutes(): Promise<ProviderRoute[]> {
    return fetchJson(`${API_BASE}/routes`);
  },

  async setRoute(role: string, provider: string, model: string, pinned = true): Promise<any> {
    return fetchJson(`${API_BASE}/routes/${role}`, {
      method: 'POST',
      body: JSON.stringify({ provider, model, pinned }),
    });
  },

  async probeProviders(): Promise<AIProvider[]> {
    return fetchJson(`${API_BASE}/providers/probe`, {
      method: 'POST',
    });
  },

  // Emergency Cockpit & Bot Controls
  async getBotState(): Promise<BotStateStatus | null> {
    return fetchJson(`${API_BASE}/bot/state`);
  },

  async startBot(): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/bot/start`, { method: 'POST' });
  },

  async stopBot(): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/bot/stop`, { method: 'POST' });
  },

  async pauseBot(): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/bot/pause`, { method: 'POST' });
  },

  async getBotStatus(): Promise<{ running: boolean }> {
    return fetchJson(`${API_BASE}/bot/status`);
  },

  async triggerKillSwitch(): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/bot/kill-switch`, { method: 'POST' });
  },

  async revokeAutonomy(reason = 'operator requested pause'): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/bot/revoke-autonomy`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },

  async revertBaseline(): Promise<{ status: string; active_genome_id: string }> {
    return fetchJson(`${API_BASE}/bot/revert-baseline`, { method: 'POST' });
  },

  // Feeds: Decisions & Trades
  async getDecisions(limit = 50): Promise<any[]> {
    return fetchJson(`${API_BASE}/decisions?limit=${limit}`);
  },

  async getTrades(): Promise<any[]> {
    return fetchJson(`${API_BASE}/trades`);
  },

  async getSettings(): Promise<EffectiveSettings> {
    return fetchJson(`${API_BASE}/settings`);
  },

  async getAgentEvents(limit = 30): Promise<AgentEvent[]> {
    return fetchJson(`${API_BASE}/agent/events?limit=${limit}`);
  },

  /**
   * Subscribe to the bounded event stream. EventSource is deliberately kept
   * behind the client boundary so the provider can report reconnect/degraded
   * state without knowing browser transport details.
   */
  streamAgentEvents(handlers: {
    onSnapshot?: (events: AgentEvent[]) => void;
    onEvent?: (event: AgentEvent) => void;
    onOpen?: () => void;
    onError?: (error: Error) => void;
  } = {}): () => void {
    if (typeof EventSource === 'undefined') {
      handlers.onError?.(new Error('Live event streaming is unavailable in this browser'));
      return () => undefined;
    }

    const source = new EventSource(`${API_BASE}/agent/events/stream`);
    const parse = (event: MessageEvent<string>): unknown => {
      try {
        return JSON.parse(event.data);
      } catch {
        handlers.onError?.(new Error('The agent event stream returned invalid JSON'));
        return undefined;
      }
    };
    source.onopen = () => handlers.onOpen?.();
    source.onerror = () => handlers.onError?.(new Error('Disconnected from the agent event stream'));
    source.addEventListener('snapshot', (event) => {
      const payload = parse(event as MessageEvent<string>) as { events?: AgentEvent[] } | undefined;
      if (payload?.events) handlers.onSnapshot?.(payload.events);
    });
    source.addEventListener('agent_event', (event) => {
      const payload = parse(event as MessageEvent<string>);
      if (payload && typeof payload === 'object') handlers.onEvent?.(payload as AgentEvent);
    });
    return () => source.close();
  },
};
