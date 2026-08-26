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
  ProviderRoute,
  ResearchQuota,
  TradeReflection,
  BotStateStatus,
} from '../types';

const API_BASE = '/api';

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
  return res.json();
}

export const api = {
  // System Health & Status
  async getHealth(): Promise<{ status: string; database?: string; quota?: any; bot_running?: boolean }> {
    return fetchJson(`${API_BASE}/health`);
  },

  async getStatus(): Promise<{
    environment: string;
    mode: string;
    symbol: string;
    bot_running: boolean;
    full_autonomy: boolean;
    active_genome_id: string;
    paper_balance: string;
    live_enabled: boolean;
  }> {
    return fetchJson(`${API_BASE}/status`);
  },

  // KPI Metrics
  async getKpi(): Promise<KpiMetrics> {
    return fetchJson(`${API_BASE}/kpi`);
  },

  // Market Candles & Quotes
  async getMarketCandles(symbol = 'PAXGUSDT', interval = '15m', limit = 50): Promise<Candle[]> {
    return fetchJson(`${API_BASE}/market/candles?symbol=${symbol}&interval=${interval}&limit=${limit}`);
  },

  async getMarketQuote(symbol = 'PAXGUSDT'): Promise<{
    symbol: string;
    bid: number;
    ask: number;
    spread: number;
    spread_rate: number;
    observed_at: string;
  }> {
    return fetchJson(`${API_BASE}/market/quote?symbol=${symbol}`);
  },

  // Open Position & 5-Step Pipeline
  async getPosition(): Promise<{
    hasPosition: boolean;
    position: PositionDetails;
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
  async getQuota(): Promise<ResearchQuota> {
    return fetchJson(`${API_BASE}/quota`);
  },

  async triggerHermesStep(): Promise<{
    status: string;
    candidate: StrategyGenome;
    quota: ResearchQuota;
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

  async getRoutes(): Promise<ProviderRoute[]> {
    return fetchJson(`${API_BASE}/routes`);
  },

  async setRoute(role: string, provider: string, model = 'google-antigravity/gemini-3.7-flash', pinned = true): Promise<any> {
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
  async getBotState(): Promise<BotStateStatus> {
    return fetchJson(`${API_BASE}/bot/state`);
  },

  async startBot(): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/bot/start`, { method: 'POST' });
  },

  async stopBot(): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/bot/stop`, { method: 'POST' });
  },

  async getBotStatus(): Promise<{ running: boolean }> {
    return fetchJson(`${API_BASE}/bot/status`);
  },

  async triggerKillSwitch(): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/bot/kill-switch`, { method: 'POST' });
  },

  async revokeAutonomy(): Promise<{ status: string }> {
    return fetchJson(`${API_BASE}/bot/revoke-autonomy`, { method: 'POST' });
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

  async getSettings(): Promise<any> {
    return fetchJson(`${API_BASE}/settings`);
  },
};
