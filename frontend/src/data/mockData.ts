import { Candle, KpiMetrics, PositionDetails, PipelineStep, EquityDataPoint, NewsItem, HealthStatusItem } from '../types/dashboard';
import { StrategyGenome, AIProvider, ProviderRoute, ResearchQuota, TradeReflection, BotStateStatus } from '../types';

export const mockKpiData: KpiMetrics = {
  equity: 104.28,
  equityCurrency: 'USDT',
  equityChangePercent: 2.41,
  equityChangePeriod: '24H',
  cash: 53.91,
  cashCurrency: 'USDT',
  cashChangeNote: 'No change',
  totalPnl: 4.28,
  totalPnlCurrency: 'USDT',
  totalPnlChangePercent: 0.86,
  totalPnlChangePeriod: '24H',
  maxDrawdown: 1.7,
  maxDrawdownPeriod: 'All time',
  liveSpread: 0.08,
  liveSpreadCurrency: 'USDT'
};

export const mockPosition: PositionDetails = {
  direction: 'LONG',
  isLive: true,
  entry: 2500.50,
  stop: 2487.50,
  target: 2525.00,
  quantity: '0.020 PAXG',
  riskPercent: 0.50
};

export const mockPipelineSteps: PipelineStep[] = [
  {
    stepNumber: 1,
    label: 'Strategy Passed',
    status: 'completed'
  },
  {
    stepNumber: 2,
    label: 'Context Clear',
    status: 'completed'
  },
  {
    stepNumber: 3,
    label: 'AI Approved 72%',
    status: 'active'
  },
  {
    stepNumber: 4,
    label: 'Risk Approved',
    status: 'pending'
  },
  {
    stepNumber: 5,
    label: 'Paper Fill',
    status: 'pending'
  }
];

export const mockLiveContext: NewsItem[] = [
  {
    id: '1',
    category: 'fed',
    title: 'FOMC Statement released - Rates maintained as expected, inflation trajectory monitored closely.',
    source: 'federalreserve.gov',
    time: '14:02'
  },
  {
    id: '2',
    category: 'yields',
    title: '10Y Real Yield holds steady at 1.82% following Treasury auction data release.',
    source: 'treasury.gov',
    time: '13:45'
  },
  {
    id: '3',
    category: 'exchange',
    title: 'Paxos Gold on-chain mint/burn audits confirmed 1:1 allocated London Good Delivery gold.',
    source: 'paxos.com',
    time: '12:10'
  }
];

export const mockRiskHealth: HealthStatusItem[] = [
  {
    id: '1',
    label: 'Database Ledger Lock',
    status: 'OK',
    icon: 'database'
  },
  {
    id: '2',
    label: 'Single Execution Lease',
    status: 'OK',
    icon: 'lease'
  },
  {
    id: '3',
    label: 'OpenCodex Gateway (Gemini 3.7)',
    status: 'OK',
    icon: 'gemini'
  },
  {
    id: '4',
    label: 'Hermes Research Agent',
    status: 'OK',
    icon: 'hermes'
  }
];

export const mockEquityHistory: EquityDataPoint[] = [
  { date: 'Aug 1', value: 100.0, benchmark: 100.0 },
  { date: 'Aug 5', value: 100.8, benchmark: 99.8 },
  { date: 'Aug 10', value: 101.4, benchmark: 100.5 },
  { date: 'Aug 15', value: 102.1, benchmark: 101.2 },
  { date: 'Aug 20', value: 103.2, benchmark: 101.8 },
  { date: 'Aug 25', value: 104.28, benchmark: 102.4 }
];

export const mockGenomes: StrategyGenome[] = [
  {
    genome_id: 'trend-pullback-v1',
    title: 'Hourly Trend 15m Pullback Recovery',
    hypothesis: 'Trading in the direction of the 1h EMA50 slope during pullbacks produces positive expectancy.',
    evidence_refs: ['doc-trend-pullback-v1', 'report-dev-baseline'],
    regime: ['trend', 'normal-volatility'],
    guard: {
      min_atr_rate: '0.0005',
      max_atr_rate: '0.0150',
      max_spread_rate: '0.0015',
    },
    entry: [
      {
        left: { indicator: 'rsi', timeframe: '15m', period: 14 },
        op: '>',
        right: '45',
      },
      {
        left: { indicator: 'volume_ratio', timeframe: '15m', period: 20 },
        op: '>=',
        right: '0.80',
      },
    ],
    exit: {
      take_profit_r_multiple: '2.0',
      stop_loss_atr_multiple: '1.5',
      invalidation: [
        {
          left: 'consecutive_closes_below_ema50',
          op: '>=',
          right: 2,
        },
      ],
    },
    status: 'active',
  },
  {
    genome_id: 'hermes-refinement-01',
    parent_id: 'trend-pullback-v1',
    title: 'Hermes Volume Filter Refinement',
    hypothesis: 'Increasing volume ratio requirement reduces low-liquidity whipsaws during session overlaps.',
    evidence_refs: ['ref-trade-chop-01', 'wfe-report-dev-val'],
    regime: ['trend', 'low-volatility'],
    guard: {
      min_atr_rate: '0.0005',
      max_atr_rate: '0.0120',
      max_spread_rate: '0.0012',
    },
    entry: [
      {
        left: { indicator: 'rsi', timeframe: '15m', period: 14 },
        op: '>',
        right: '48',
      },
      {
        left: { indicator: 'volume_ratio', timeframe: '15m', period: 20 },
        op: '>=',
        right: '1.10',
      },
    ],
    exit: {
      take_profit_r_multiple: '2.2',
      stop_loss_atr_multiple: '1.4',
      invalidation: [
        {
          left: 'consecutive_closes_below_ema50',
          op: '>=',
          right: 2,
        },
      ],
    },
    status: 'candidate',
  },
];

export const mockProviders: AIProvider[] = [
  {
    name: 'opencodex',
    kind: 'proxy',
    base_url: 'http://localhost:10100',
    key_fingerprint: 'sk-mock-****9999',
    status: 'active',
    latency_ms: 48,
  },
  {
    name: 'google-antigravity',
    kind: 'native',
    base_url: 'https://generativelanguage.googleapis.com',
    key_fingerprint: 'sk-mock-****8888',
    status: 'active',
    latency_ms: 115,
  },
];

export const mockRoutes: ProviderRoute[] = [
  {
    id: 'r-1',
    role: 'decision',
    provider: 'opencodex',
    model: 'google-antigravity/gemini-3.7-flash',
    pinned: true,
    version: 1,
    status: 'active',
  },
  {
    id: 'r-2',
    role: 'context',
    provider: 'opencodex',
    model: 'google-antigravity/gemini-3.7-flash',
    pinned: true,
    version: 1,
    status: 'active',
  },
  {
    id: 'r-3',
    role: 'hermes',
    provider: 'opencodex',
    model: 'google-antigravity/gemini-3.7-flash',
    pinned: true,
    version: 1,
    status: 'active',
  },
];

export const mockQuota: ResearchQuota = {
  date: '2026-08-26',
  backtests_used: 14,
  backtests_limit: 50,
  web_calls_used: 8,
  web_calls_limit: 20,
};

export const mockReflections: TradeReflection[] = [
  {
    id: 'ref-1',
    trade_id: 't-101',
    namespace: 'forward',
    lesson_code: 'CHOP_WHIPSAW',
    lesson: 'Achieved positive excursion then reversed into stop; volume requirement adjusted.',
    regime_tags: ['trend', 'low-volatility'],
    net_pnl: '-1.45',
    fee_drag: '0.25',
    exit_reason: 'STOP_LOSS',
    created_at: '2026-08-26T14:30:00Z',
  },
  {
    id: 'ref-2',
    trade_id: 't-102',
    namespace: 'forward',
    lesson_code: 'TP_CLEAN',
    lesson: 'Target reached cleanly with hourly trend momentum.',
    regime_tags: ['trend', 'normal-volatility'],
    net_pnl: '+2.80',
    fee_drag: '0.22',
    exit_reason: 'TAKE_PROFIT',
    created_at: '2026-08-26T16:00:00Z',
  },
];

export const mockBotState: BotStateStatus = {
  state: 'NORMAL',
  full_autonomy: true,
  daily_loss_percent: 0.65,
  daily_loss_limit: 3.00,
  circuit_breaker_tripped: false,
  active_genome_id: 'trend-pullback-v1',
};

const chartDataRaw = [
  { time: '18:00', open: 2490.50, high: 2494.20, low: 2489.10, close: 2493.40, volume: 1.120 },
  { time: '21:00', open: 2493.40, high: 2498.00, low: 2492.00, close: 2497.50, volume: 1.450 },
  { time: '00:00', open: 2497.50, high: 2504.10, low: 2496.80, close: 2501.20, volume: 1.890 },
  { time: '03:00', open: 2501.20, high: 2508.40, low: 2500.00, close: 2506.70, volume: 2.100 },
  { time: '06:00', open: 2506.70, high: 2512.00, low: 2505.30, close: 2510.80, volume: 1.760 },
  { time: '09:00', open: 2510.80, high: 2518.50, low: 2509.00, close: 2516.20, volume: 2.450 },
  { time: '12:00', open: 2516.20, high: 2522.00, low: 2514.80, close: 2520.77, volume: 3.120 },
  { time: '15:00', open: 2520.77, high: 2525.80, low: 2519.40, close: 2524.60, volume: 1.245 }
];

export const mockCandles: Candle[] = (() => {
  const N = chartDataRaw.length;
  let rawEma20 = 2498.0;
  let rawEma50 = 2496.0;
  const ema20Arr: number[] = [];
  const ema50Arr: number[] = [];

  for (let i = 0; i < N; i++) {
    const c = chartDataRaw[i];
    rawEma20 = c.close * 0.14 + rawEma20 * 0.86;
    rawEma50 = c.close * 0.065 + rawEma50 * 0.935;
    ema20Arr.push(rawEma20);
    ema50Arr.push(rawEma50);
  }

  const targetEma20 = 2520.77;
  const targetEma50 = 2515.35;
  const diff20 = targetEma20 - ema20Arr[N - 1];
  const diff50 = targetEma50 - ema50Arr[N - 1];

  return chartDataRaw.map((c, i) => {
    const t = i / (N - 1);
    const smoothT = t * t * (3 - 2 * t);
    const finalEma20 = ema20Arr[i] + diff20 * smoothT;
    const finalEma50 = ema50Arr[i] + diff50 * smoothT;

    return {
      ...c,
      ema20: Number(finalEma20.toFixed(2)),
      ema50: Number(finalEma50.toFixed(2))
    };
  });
})();
