import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, AgentEvent, PreflightResponse, StatusResponse } from '../api/client';
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
  AIProvider,
  OpenCodexModel,
  ProviderRoute,
  ResearchQuota,
  TradeReflection,
  BotStateStatus,
} from '../types';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  title: string;
  message?: string;
  timestamp: string;
}

export interface DataStatus {
  loading: boolean;
  error: string | null;
  degraded: boolean;
  lastUpdatedAt: string | null;
}

export interface RuntimeStatus {
  state: string | null;
  running: boolean;
  paused: boolean;
  halted: boolean;
  marketVerified: boolean;
  marketSource: string | null;
  degradedReasons: string[];
  executionOwner: string | null;
  datasetStatus: string | null;
  reflectionCount: number;
  hermesStatus: string | null;
  latestLesson: string | null;
  lastGate: string | null;
}

export interface BotContextType {
  botRunning: boolean;
  isPaperMode: boolean;
  selectedPair: string;
  activeGenomeId: string;
  systemHealthy: boolean;
  runtimeStatus: RuntimeStatus | null;
  preflight: PreflightResponse | null;
  agentEvents: AgentEvent[];
  dataStatus: DataStatus;
  loading: boolean;
  error: string | null;
  degraded: boolean;

  // Values remain null/empty until the API observes them; no mock values are seeded.
  kpi: KpiMetrics;
  candles: Candle[];
  quote: { bid: number; ask: number; spread: number; spread_rate: number; observed_at: string };
  position: PositionDetails;
  pipelineSteps: PipelineStep[];
  pnlBySymbol: Array<{ symbol: string; unrealized?: string; quantity?: string; side?: string }>;
  liveContext: NewsItem[];
  riskHealth: HealthStatusItem[];
  equityHistory: EquityDataPoint[];
  genomes: StrategyGenome[];
  providers: AIProvider[];
  catalog: OpenCodexModel[];
  routes: ProviderRoute[];
  quota: ResearchQuota;
  reflections: TradeReflection[];
  botState: BotStateStatus;

  toasts: ToastMessage[];
  addToast: (type: ToastMessage['type'], title: string, message?: string) => void;
  removeToast: (id: string) => void;

  // Paper-first actions
  startPaperTrading: () => Promise<void>;
  pauseTrading: () => Promise<void>;
  emergencyStop: () => Promise<void>;

  // Existing advanced actions
  setSelectedPair: (pair: string) => void;
  refreshAll: () => Promise<void>;
  promoteGenome: (genomeId: string) => Promise<void>;
  triggerHermesStep: () => Promise<{ status?: string; candidate_genome_id?: string | null; gate_results?: Record<string, unknown> } | null>;
  updateRoute: (role: 'decision' | 'context' | 'hermes', provider: string, model?: string) => Promise<void>;
  probeLatencies: () => Promise<void>;
  triggerKillSwitch: () => Promise<void>;
  revokeAutonomy: () => Promise<void>;
  revertBaseline: () => Promise<void>;
}

const BotContext = createContext<BotContextType | null>(null);

const sectionData = <T,>(section: { data: T; availability?: string } | T | null | undefined): T | null => {
  if (section === null || section === undefined) return null;
  if (typeof section === 'object' && section !== null && 'data' in section) {
    return (section as { data: T }).data ?? null;
  }
  return section as T;
};

const sectionIsDegraded = (section: unknown): boolean => {
  if (!section || typeof section !== 'object' || !('availability' in section)) return false;
  return (section as { availability?: string }).availability !== 'available';
};

const runtimeFromSnapshot = (status: StatusResponse | null, botState: BotStateStatus | null): RuntimeStatus | null => {
  if (!status && !botState) return null;
  const state = botState?.state ?? status?.bot_state ?? null;
  const degradedReasons = [
    ...(status?.degraded_reasons ?? []),
    ...(botState && 'degraded_reasons' in botState && Array.isArray(botState.degraded_reasons)
      ? botState.degraded_reasons
      : []),
  ];
  return {
    state,
    running: status?.bot_running ?? false,
    paused: Boolean(botState && 'paused' in botState && botState.paused),
    halted: Boolean(botState?.circuit_breaker_tripped),
    marketVerified: Boolean(status?.market_verified),
    marketSource: status?.market_source ?? null,
    degradedReasons: [...new Set(degradedReasons.map(String))],
    executionOwner: status?.execution_owner ?? null,
    datasetStatus: status?.dataset_status ?? null,
    reflectionCount: status?.reflection_count ?? 0,
    hermesStatus: status?.hermes_status ?? null,
    latestLesson: status?.latest_lesson ?? null,
    lastGate: status?.last_gate ?? null,
  };
};

const isRenderableKpi = (value: KpiMetrics | null): value is KpiMetrics => {
  if (!value) return false;
  return [
    value.equity,
    value.equityChangePercent,
    value.cash,
    value.totalPnl,
    value.totalPnlChangePercent,
    value.maxDrawdown,
    value.liveSpread,
  ].every((item) => typeof item === 'number' && Number.isFinite(item));
};

const isRenderablePosition = (value: PositionDetails | null): value is PositionDetails => {
  if (!value) return false;
  return [value.entry, value.stop, value.target, value.riskPercent].every(
    (item) => typeof item === 'number' && Number.isFinite(item),
  );
};

const isRenderableQuote = (
  value: { bid: number; ask: number; spread: number; spread_rate: number; observed_at: string } | null,
): value is { bid: number; ask: number; spread: number; spread_rate: number; observed_at: string } => {
  if (!value) return false;
  return [value.bid, value.ask, value.spread, value.spread_rate].every(
    (item) => typeof item === 'number' && Number.isFinite(item),
  );
};

export const BotProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [botRunning, setBotRunning] = useState(false);
  const [isPaperMode, setIsPaperMode] = useState(true);
  const [selectedPair, setSelectedPair] = useState('PAXG / USDT');
  const [activeGenomeId, setActiveGenomeId] = useState<string>(null as unknown as string);
  const [systemHealthy, setSystemHealthy] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null);
  const [preflight, setPreflight] = useState<PreflightResponse | null>(null);
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);

  const [kpi, setKpi] = useState<KpiMetrics>(null as unknown as KpiMetrics);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [quote, setQuote] = useState<{
    bid: number;
    ask: number;
    spread: number;
    spread_rate: number;
    observed_at: string;
  }>(null as unknown as { bid: number; ask: number; spread: number; spread_rate: number; observed_at: string });
  const [position, setPosition] = useState<PositionDetails>(null as unknown as PositionDetails);
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([]);
  const [pnlBySymbol, setPnlBySymbol] = useState<Array<{ symbol: string; unrealized?: string; quantity?: string; side?: string }>>([]);
  const [liveContext, setLiveContext] = useState<NewsItem[]>([]);
  const [riskHealth, setRiskHealth] = useState<HealthStatusItem[]>([]);
  const [equityHistory, setEquityHistory] = useState<EquityDataPoint[]>([]);
  const [genomes, setGenomes] = useState<StrategyGenome[]>([]);
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [catalog, setCatalog] = useState<OpenCodexModel[]>([]);
  const [routes, setRoutes] = useState<ProviderRoute[]>([]);
  const [quota, setQuota] = useState<ResearchQuota>(null as unknown as ResearchQuota);
  const [reflections, setReflections] = useState<TradeReflection[]>([]);
  const [botState, setBotState] = useState<BotStateStatus>(null as unknown as BotStateStatus);
  const [dataStatus, setDataStatus] = useState<DataStatus>({
    loading: true,
    error: null,
    degraded: false,
    lastUpdatedAt: null,
  });
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = useCallback((type: ToastMessage['type'], title: string, message?: string) => {
    const newToast: ToastMessage = {
      id: `${Date.now()}-${Math.random()}`,
      type,
      title,
      message,
      timestamp: new Date().toLocaleTimeString(),
    };
    setToasts((prev) => [newToast, ...prev.slice(0, 4)]);
    window.setTimeout(() => setToasts((prev) => prev.filter((toast) => toast.id !== newToast.id)), 5000);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const refreshAll = useCallback(async () => {
    setDataStatus((previous) => ({ ...previous, loading: true, error: null }));
    try {
      const snapshot = await api.getDashboard();
      const status = sectionData(snapshot.status);
      const kpiData = sectionData(snapshot.kpi);
      const quoteData = sectionData(snapshot.quote);
      const positionData = sectionData(snapshot.position);
      const botStateData = sectionData(snapshot.botState);
      const allSections = [
        snapshot.status,
        snapshot.kpi,
        snapshot.quote,
        snapshot.candles,
        snapshot.position,
        snapshot.equity,
        snapshot.context,
        snapshot.genomes,
        snapshot.providers,
        snapshot.catalog,
        snapshot.routes,
        snapshot.quota,
        snapshot.reflections,
        snapshot.botState,
        snapshot.agentEvents,
        snapshot.promotionCanary,
        snapshot.diagnostics,
      ];

      setSystemHealthy(snapshot.health?.status === 'ok');
      setBotRunning(Boolean(status?.bot_running));
      setIsPaperMode(status?.mode !== 'live');
      setActiveGenomeId((status?.active_genome_id ?? botStateData?.active_genome_id) as string);
      setRuntimeStatus(runtimeFromSnapshot(status, botStateData));
      setPreflight(snapshot.preflight ?? null);
      setKpi((isRenderableKpi(kpiData) ? kpiData : null) as unknown as KpiMetrics);
      setQuote((isRenderableQuote(quoteData) ? quoteData : null) as { bid: number; ask: number; spread: number; spread_rate: number; observed_at: string });
      setCandles(sectionData(snapshot.candles) ?? []);
      setPosition((isRenderablePosition(positionData?.position ?? null) ? positionData?.position : null) as unknown as PositionDetails);
      setPipelineSteps(positionData?.pipelineSteps ?? []);
      setPnlBySymbol(positionData?.pnlBySymbol ?? []);
      setEquityHistory(sectionData(snapshot.equity) ?? []);
      setLiveContext(sectionData(snapshot.context) ?? []);
      setGenomes(sectionData(snapshot.genomes) ?? []);
      setProviders(sectionData(snapshot.providers) ?? []);
      setCatalog(sectionData(snapshot.catalog) ?? []);
      setRoutes(sectionData(snapshot.routes) ?? []);
      setQuota(sectionData(snapshot.quota) as ResearchQuota);
      setReflections(sectionData(snapshot.reflections) ?? []);
      setBotState((botStateData && typeof botStateData.state === 'string' ? botStateData : null) as unknown as BotStateStatus);
      setAgentEvents((sectionData(snapshot.agentEvents) ?? []).slice(0, 30));

      const runtime = runtimeFromSnapshot(status, botStateData);
      const diagnostics = sectionData(snapshot.diagnostics);
      const opencodexCheck = diagnostics?.checks?.find((item) => item.name === 'opencodex_model');
      const hermesCheck = diagnostics?.checks?.find((item) => item.name === 'hermes_memory_restart');
      setRiskHealth([
        {
          id: 'database',
          label: `Database: ${snapshot.health?.database ?? 'unknown'}`,
          status: snapshot.health?.database === 'ok' ? 'OK' : 'ERROR',
          icon: 'database',
        },
        {
          id: 'market',
          label: status?.market_verified ? 'Verified market data' : 'Market data unavailable',
          status: status?.market_verified ? 'OK' : 'WARNING',
          icon: 'lease',
        },
        {
          id: 'runtime',
          label: runtime?.state ? `Runtime: ${runtime.state}` : 'Runtime unavailable',
          status: runtime?.state ? 'OK' : 'ERROR',
          icon: 'gemini',
        },
        {
          id: 'opencodex',
          label: opencodexCheck
            ? `OpenCodex: ${opencodexCheck.status}`
            : 'OpenCodex: not probed',
          status: opencodexCheck?.status === 'pass' ? 'OK' : 'WARNING',
          icon: 'gemini',
        },
        {
          id: 'hermes',
          label: hermesCheck ? `Hermes: ${hermesCheck.status}` : 'Hermes: not probed',
          status: hermesCheck?.status === 'pass' ? 'OK' : 'WARNING',
          icon: 'gemini',
        },
      ]);
      setDataStatus({
        loading: false,
        error: null,
        degraded: allSections.some(sectionIsDegraded) || !snapshot.preflight?.ready,
        lastUpdatedAt: snapshot.generated_at ?? new Date().toISOString(),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to reach the trading service';
      setDataStatus((previous) => ({ ...previous, loading: false, error: message, degraded: true }));
    }
  }, []);

  useEffect(() => {
    void refreshAll();
    const interval = window.setInterval(() => void refreshAll(), 4000);
    const disposeStream =
      typeof EventSource === 'undefined'
        ? () => undefined
        : api.streamAgentEvents({
            onSnapshot: (events) => setAgentEvents(events.slice(0, 30)),
            onEvent: (event) => setAgentEvents((previous) => [event, ...previous.filter((item) => item.event_id !== event.event_id)].slice(0, 30)),
            onOpen: () => setDataStatus((previous) => ({
              ...previous,
              error: previous.error?.startsWith('Disconnected from the agent event stream') ? null : previous.error,
            })),
            onError: (error) => setDataStatus((previous) => ({ ...previous, degraded: true, error: error.message })),
          });
    return () => {
      window.clearInterval(interval);
      disposeStream();
    };
  }, [refreshAll]);

  const startPaperTrading = useCallback(async () => {
    if (!preflight) {
      addToast('info', 'Preflight still loading', 'Wait for the server checks before starting paper trading.');
      return;
    }
    if (!preflight.ready) {
      const details = preflight.checks.filter((check) => check.status === 'fail').map((check) => `${check.label}: ${check.detail}`).join(' ');
      addToast('error', 'Paper trading blocked by preflight', details || 'Resolve the blocking checks before starting.');
      return;
    }
    try {
      await api.startBot();
      addToast('success', 'Paper trading started', 'New entries will be evaluated from verified closed candles.');
      await refreshAll();
    } catch (error) {
      addToast('error', 'Paper trading could not start', error instanceof Error ? error.message : 'The server rejected the start request.');
      await refreshAll();
    }
  }, [addToast, preflight, refreshAll]);

  const pauseTrading = useCallback(async () => {
    try {
      await api.pauseBot();
      addToast('info', 'New entries paused', 'Protective monitoring continues for any open paper position.');
      await refreshAll();
    } catch (error) {
      addToast('error', 'Pause request failed', error instanceof Error ? error.message : 'The server rejected the pause request.');
    }
  }, [addToast, refreshAll]);

  const emergencyStop = useCallback(async () => {
    try {
      await api.stopBot();
      addToast('warning', 'Emergency stop engaged', 'Paper positions are closed and the runtime remains halted until reset.');
      await refreshAll();
    } catch (error) {
      addToast('error', 'Emergency stop failed', error instanceof Error ? error.message : 'The server rejected the emergency stop.');
    }
  }, [addToast, refreshAll]);

  const promoteGenome = useCallback(async (genomeId: string) => {
    try {
      await api.promoteGenome(genomeId);
      addToast('success', 'Strategy promoted', `Genome ${genomeId} is now the active strategy.`);
      await refreshAll();
    } catch (error) {
      addToast('error', 'Promotion failed', error instanceof Error ? error.message : 'The server rejected the promotion.');
    }
  }, [addToast, refreshAll]);

  const triggerHermesStep = useCallback(async () => {
    try {
      const result = await api.triggerHermesStep();
      const status = result.status || 'complete';
      addToast(
        status.includes('reject') || status.includes('fail') || status.includes('quota') ? 'warning' : 'success',
        `Hermes: ${status.replace(/_/g, ' ')}`,
        result.candidate_genome_id ? `Candidate ${result.candidate_genome_id}` : undefined,
      );
      await refreshAll();
      return result;
    } catch (error) {
      addToast('error', 'Hermes step failed', error instanceof Error ? error.message : 'The server rejected the research request.');
      return null;
    }
  }, [addToast, refreshAll]);

  const updateRoute = useCallback(async (role: 'decision' | 'context' | 'hermes', provider: string, model?: string) => {
    try {
      await api.setRoute(role, provider, model || 'google-antigravity/gemini-3.7-flash');
      addToast('success', 'Saved', `Using ${model || provider} for ${role}.`);
      await refreshAll();
    } catch (error) {
      addToast('error', 'Could not save model', error instanceof Error ? error.message : 'The server rejected the route update.');
    }
  }, [addToast, refreshAll]);

  const probeLatencies = useCallback(async () => {
    try {
      setProviders(await api.probeProviders());
      addToast('info', 'Provider probes complete', 'Latency results reflect the latest server probes.');
    } catch (error) {
      addToast('error', 'Provider probe failed', error instanceof Error ? error.message : 'The server rejected the probe request.');
    }
  }, [addToast]);

  const revokeAutonomy = useCallback(async () => {
    try {
      await api.revokeAutonomy();
      addToast('warning', 'Autonomy suspended', 'Human approval is required for mutations.');
      await refreshAll();
    } catch (error) {
      addToast('error', 'Autonomy action failed', error instanceof Error ? error.message : 'The server rejected the request.');
    }
  }, [addToast, refreshAll]);

  const revertBaseline = useCallback(async () => {
    try {
      await api.revertBaseline();
      addToast('success', 'Reverted to baseline', 'The verified baseline strategy is active.');
      await refreshAll();
    } catch (error) {
      addToast('error', 'Baseline revert failed', error instanceof Error ? error.message : 'The server rejected the request.');
    }
  }, [addToast, refreshAll]);

  const value = useMemo<BotContextType>(() => ({
    botRunning,
    isPaperMode,
    selectedPair,
    activeGenomeId,
    systemHealthy,
    runtimeStatus,
    preflight,
    agentEvents,
    dataStatus,
    loading: dataStatus.loading,
    error: dataStatus.error,
    degraded: dataStatus.degraded,
    kpi,
    candles,
    quote,
    position,
    pipelineSteps,
    pnlBySymbol,
    liveContext,
    riskHealth,
    equityHistory,
    genomes,
    providers,
    catalog,
    routes,
    quota,
    reflections,
    botState,
    toasts,
    addToast,
    removeToast,
    startPaperTrading,
    pauseTrading,
    emergencyStop,
    setSelectedPair,
    refreshAll,
    promoteGenome,
    triggerHermesStep,
    updateRoute,
    probeLatencies,
    triggerKillSwitch: emergencyStop,
    revokeAutonomy,
    revertBaseline,
  }), [
    activeGenomeId,
    addToast,
    agentEvents,
    botRunning,
    botState,
    candles,
    catalog,
    dataStatus,
    emergencyStop,
    equityHistory,
    genomes,
    isPaperMode,
    kpi,
    liveContext,
    pauseTrading,
    pipelineSteps,
    position,
    pnlBySymbol,
    preflight,
    probeLatencies,
    promoteGenome,
    providers,
    quote,
    reflections,
    refreshAll,
    removeToast,
    revertBaseline,
    riskHealth,
    routes,
    runtimeStatus,
    selectedPair,
    startPaperTrading,
    systemHealthy,
    toasts,
    triggerHermesStep,
    updateRoute,
    quota,
    revokeAutonomy,
  ]);

  return <BotContext.Provider value={value}>{children}</BotContext.Provider>;
};

export const useBot = () => {
  const context = useContext(BotContext);
  if (!context) throw new Error('useBot must be used within a BotProvider');
  return context;
};
